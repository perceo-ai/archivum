from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

import httpx

from archivum.config import Settings
from archivum.observability import span

logger = logging.getLogger(__name__)


async def openrouter_chat_completion(
    *,
    settings: Settings,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float = 0.2,
) -> str:
    """One-shot OpenAI-compatible chat completion."""
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    with span("openrouter.chat_completion", model=model, max_tokens=max_tokens, temperature=temperature) as sp:
        logger.info("OpenRouter request start", extra={**sp})
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        logger.info("OpenRouter request done", extra={"status_code": resp.status_code, **sp})

    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(data, dict)
        else None
    )
    return (content or "").strip()


async def openrouter_stream_tokens(
    *,
    settings: Settings,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float = 0.2,
) -> AsyncGenerator[str, None]:
    """Stream `delta.content` tokens from OpenRouter SSE."""
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        # OpenRouter/OpenAI-compatible streams are SSE-like.
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    with span("openrouter.stream", model=model, max_tokens=max_tokens, temperature=temperature) as sp:
        logger.info("OpenRouter stream start", extra={**sp})
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    # Typical form: "data: {json}\n\n"
                    if not line:
                        continue
                    if not line.startswith("data:"):
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

        logger.info("OpenRouter stream finished", extra={**sp})

