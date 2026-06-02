"""Unit tests for Bedrock message/tool conversion (no AWS calls)."""

from app.ai.agent_protocol import ToolCall
from app.ai.providers.bedrock_provider import (
    _neutral_to_bedrock_messages,
    _openai_tools_to_bedrock,
)


def test_openai_tools_to_bedrock():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_wiki",
                "description": "Search the wiki",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]
    out = _openai_tools_to_bedrock(tools)
    assert len(out) == 1
    assert out[0]["toolSpec"]["name"] == "search_wiki"
    assert "query" in out[0]["toolSpec"]["inputSchema"]["json"]["properties"]


def test_neutral_to_bedrock_messages_tool_roundtrip():
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "checking",
            "tool_calls": [ToolCall(id="t1", name="search_wiki", arguments={"query": "x"})],
        },
        {
            "role": "user",
            "tool_results": [{"id": "t1", "name": "search_wiki", "content": "[]"}],
        },
    ]
    bedrock = _neutral_to_bedrock_messages(messages)
    assert bedrock[0]["content"][0]["text"] == "hello"
    assert bedrock[1]["content"][1]["toolUse"]["name"] == "search_wiki"
    assert bedrock[2]["content"][0]["toolResult"]["toolUseId"] == "t1"
