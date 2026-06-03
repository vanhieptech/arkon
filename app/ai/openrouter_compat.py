"""OpenRouter routing helpers — base URL + optional attribution headers."""

from __future__ import annotations

import os

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def is_openrouter_route(
    *,
    spec_id: str | None = None,
    model_id: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> bool:
    if base_url and "openrouter.ai" in base_url:
        return True
    if spec_id and spec_id.startswith("openrouter/"):
        return True
    if model_id and (
        model_id.startswith("openrouter/")
        or model_id.startswith("qwen/")
    ):
        return True
    if api_key and api_key.startswith("sk-or-v1"):
        return True
    return False


def resolve_base_url(
    *,
    spec_id: str | None,
    model_id: str,
    base_url: str | None,
    api_key: str,
) -> str | None:
    """Use OpenRouter when catalog/key imply it and admin left base_url empty."""
    if base_url and base_url.strip():
        return base_url.strip()
    if is_openrouter_route(spec_id=spec_id, model_id=model_id, api_key=api_key):
        return OPENROUTER_BASE_URL
    return None


def default_headers() -> dict[str, str]:
    """OpenRouter optional attribution headers (from env or Settings)."""
    headers: dict[str, str] = {}
    referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
    title = os.environ.get("OPENROUTER_APP_TITLE", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers
