from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

import httpx

from archivum.config import Settings
from archivum.observability import span

logger = logging.getLogger(__name__)


def _is_azure_openai_base_url(base_url: str) -> bool:
    return "openai.azure.com" in (base_url or "").lower()


_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "groq": "https://api.groq.com/openai/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}


def _derive_base_url(settings: Settings) -> str:
    # Allow explicit override for custom/azure/power users
    if settings.openai_compat_base_url:
        return settings.openai_compat_base_url.rstrip("/")
    provider = (settings.openai_compat_provider or "openai").strip().lower()
    return _PROVIDER_BASE_URLS.get(provider, _PROVIDER_BASE_URLS["openai"])


def _resolve_llm_endpoint(settings: Settings, provider: str) -> tuple[str, str, dict[str, str], dict[str, Any] | None]:
    """
    Return (base_url, api_key, headers, params) for OpenAI-compatible chat.
    """
    p = (provider or "").strip().lower()
    if p == "ollama":
        base_url = f"{settings.ollama_base_url.rstrip('/')}/v1"
        return (base_url, "", {"Accept": "application/json"}, None)

    # openai_compat
    base_url = _derive_base_url(settings)
    api_key = settings.openai_compat_api_key
    headers: dict[str, str] = {"Accept": "application/json"}
    params: dict[str, Any] | None = None

    if _is_azure_openai_base_url(base_url):
        # Azure OpenAI uses api-key header + api-version query param
        if api_key:
            headers["api-key"] = api_key
        params = {"api-version": settings.openai_compat_azure_api_version}
        api_key = ""  # prevent Authorization header

    return (base_url, api_key, headers, params)


async def openai_compat_chat_completion(
    *,
    settings: Settings,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float = 0.2,
) -> str:
    """
    One-shot OpenAI-compatible chat completion against OPENAI_COMPAT_BASE_URL
    or local Ollama when provider=ollama.
    """
    base_url, api_key, headers, params = _resolve_llm_endpoint(settings, provider)
    if not base_url:
        raise RuntimeError("OpenAI-compatible base URL could not be derived/configured")

    url = f"{base_url}/chat/completions"
    if api_key:
        headers = {**headers, "Authorization": f"Bearer {api_key}"}

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    with span("openai_compat.chat_completion", provider=provider, model=model, max_tokens=max_tokens) as sp:
        logger.info("OpenAI-compatible request start", extra={**sp, "base_url": base_url})
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
        logger.info("OpenAI-compatible request done", extra={**sp, "status_code": resp.status_code})

    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(data, dict)
        else None
    )
    return (content or "").strip()


async def openai_compat_stream_tokens(
    *,
    settings: Settings,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float = 0.2,
) -> AsyncGenerator[str, None]:
    """
    Stream `delta.content` tokens from an OpenAI-compatible SSE stream.
    """
    base_url, api_key, headers, params = _resolve_llm_endpoint(settings, provider)
    if not base_url:
        raise RuntimeError("OPENAI_COMPAT_BASE_URL not configured")

    url = f"{base_url}/chat/completions"
    if api_key:
        headers = {**headers, "Authorization": f"Bearer {api_key}"}

    headers = {**headers, "Accept": "text/event-stream"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    with span("openai_compat.stream", provider=provider, model=model, max_tokens=max_tokens) as sp:
        logger.info("OpenAI-compatible stream start", extra={**sp, "base_url": base_url})
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, headers=headers, params=params, json=payload) as resp:
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    payload_str = line[len("data:") :].strip()
                    if payload_str == "[DONE]":
                        break
                    if not payload_str:
                        continue

                    try:
                        event = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue

                    delta = ((event.get("choices") or [{}])[0].get("delta") or {})
                    token = delta.get("content") or delta.get("text") or ""
                    if token:
                        yield token

        logger.info("OpenAI-compatible stream finished", extra={**sp})

