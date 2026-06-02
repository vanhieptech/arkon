"""
Amazon Bedrock — LLM (Converse API) and embeddings (InvokeModel).

Uses the default AWS credential chain (env keys, ~/.aws/credentials, ECS task role).
`ProviderConfig.api_key` is optional and unused for Bedrock.

Configure via Settings catalog:
  - bedrock/claude-3-5-sonnet
  - bedrock/titan-embed-v2
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from loguru import logger

from app.ai.agent_protocol import AssistantTurn, ToolCall
from app.ai.providers.base import EmbeddingProvider, LLMProvider, ProviderConfig


def _bedrock_runtime_client(config: ProviderConfig):
    import boto3

    region = config.extra.get("aws_region") or "us-east-1"
    kwargs: dict[str, Any] = {"region_name": region}
    endpoint = config.extra.get("aws_endpoint_url")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("bedrock-runtime", **kwargs)


def _openai_tools_to_bedrock(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-style tool defs to Bedrock Converse toolSpec entries."""
    specs: list[dict] = []
    for tool in tools:
        fn = tool.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        specs.append(
            {
                "toolSpec": {
                    "name": name,
                    "description": fn.get("description") or name,
                    "inputSchema": {"json": params},
                }
            }
        )
    return specs


def _neutral_to_bedrock_messages(messages: list[dict]) -> list[dict]:
    """Convert neutral agent messages to Bedrock Converse message format."""
    result: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            if "tool_results" in msg:
                blocks = [
                    {
                        "toolResult": {
                            "toolUseId": r["id"],
                            "content": [{"text": r["content"]}],
                        }
                    }
                    for r in msg["tool_results"]
                ]
                result.append({"role": "user", "content": blocks})
            else:
                text = msg.get("content") or ""
                result.append({"role": "user", "content": [{"text": text}]})
        elif role == "assistant":
            blocks: list[dict] = []
            if msg.get("content"):
                blocks.append({"text": msg["content"]})
            for tc in msg.get("tool_calls", []):
                tid = tc.id if hasattr(tc, "id") else tc.get("id")
                tname = tc.name if hasattr(tc, "name") else tc.get("name")
                targs = tc.arguments if hasattr(tc, "arguments") else tc.get("arguments", {})
                blocks.append(
                    {
                        "toolUse": {
                            "toolUseId": tid,
                            "name": tname,
                            "input": targs if isinstance(targs, dict) else {},
                        }
                    }
                )
            result.append(
                {"role": "assistant", "content": blocks or [{"text": ""}]}
            )
    return result


class BedrockEmbedding(EmbeddingProvider):
    """Bedrock Titan Text Embeddings V2 (and compatible invoke_model embeddings)."""

    async def embed(self, text: str) -> list[float]:
        results = await self.embed_batch([text], concurrency=1)
        return results[0]

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        sem = asyncio.Semaphore(concurrency)
        client = _bedrock_runtime_client(self.config)
        dim = self.dimensions

        async def _one(text: str) -> list[float]:
            async with sem:
                body: dict[str, Any] = {"inputText": text, "normalize": True}
                if dim:
                    body["dimensions"] = dim
                return await asyncio.to_thread(
                    _invoke_embedding,
                    client,
                    self.config.model_id,
                    body,
                )

        return await asyncio.gather(*[_one(t) for t in texts])

    async def test_connection(self) -> tuple[bool, str]:
        try:
            vec = await self.embed("connection test")
            return True, f"OK — model={self.config.model_id}, dimensions={len(vec)}"
        except Exception as e:
            return False, f"Bedrock embedding error: {e}"


def _invoke_embedding(client, model_id: str, body: dict) -> list[float]:
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    embedding = payload.get("embedding")
    if not embedding:
        raise ValueError(f"Bedrock embedding response missing 'embedding': {payload}")
    return embedding


class BedrockLLM(LLMProvider):
    """Bedrock Converse API — Claude and other chat models on Bedrock."""

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        kwargs: dict[str, Any] = {
            "modelId": self.config.model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens or 4096,
                "temperature": temperature,
            },
        }
        if system:
            kwargs["system"] = [{"text": system}]
        client = _bedrock_runtime_client(self.config)
        response = await asyncio.to_thread(client.converse, **kwargs)
        return _extract_converse_text(response)

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> AssistantTurn:
        bedrock_messages = _neutral_to_bedrock_messages(messages)
        tool_specs = _openai_tools_to_bedrock(tools)
        kwargs: dict[str, Any] = {
            "modelId": self.config.model_id,
            "messages": bedrock_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens or 8192,
                "temperature": temperature,
            },
        }
        if system:
            kwargs["system"] = [{"text": system}]
        if tool_specs:
            kwargs["toolConfig"] = {"tools": tool_specs}
        client = _bedrock_runtime_client(self.config)
        response = await asyncio.to_thread(client.converse, **kwargs)
        return _parse_converse_turn(response)

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.generate("Reply with exactly: OK", max_tokens=16, temperature=0)
            snippet = (result or "")[:80]
            return True, f"OK — model={self.config.model_id}, response={snippet!r}"
        except Exception as e:
            return False, f"Bedrock LLM error: {e}"


def _extract_converse_text(response: dict) -> str:
    output = response.get("output") or {}
    message = output.get("message") or {}
    parts: list[str] = []
    for block in message.get("content") or []:
        if "text" in block:
            parts.append(block["text"])
    return "\n".join(parts)


def _parse_converse_turn(response: dict) -> AssistantTurn:
    output = response.get("output") or {}
    message = output.get("message") or {}
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in message.get("content") or []:
        if "text" in block:
            text_parts.append(block["text"])
        elif "toolUse" in block:
            tu = block["toolUse"]
            tool_calls.append(
                ToolCall(
                    id=tu.get("toolUseId", ""),
                    name=tu.get("name", ""),
                    arguments=tu.get("input") if isinstance(tu.get("input"), dict) else {},
                )
            )
    stop = response.get("stopReason") or "end_turn"
    reason_map = {
        "end_turn": "end_turn",
        "tool_use": "tool_use",
        "max_tokens": "max_tokens",
    }
    finish_reason = reason_map.get(stop, "end_turn")
    if tool_calls and finish_reason == "end_turn":
        finish_reason = "tool_use"
    return AssistantTurn(
        text="\n".join(text_parts) or None,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        raw_provider_content=message,
    )
