from types import SimpleNamespace

import pytest

from archivum.llm import openrouter_client as client


def _settings(**overrides):
    data = {
        "openrouter_api_key": "router-key",
        "openrouter_base_url": "https://openrouter.ai/api/v1/",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_chat_completion_requires_api_key():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await client.openrouter_chat_completion(
            settings=_settings(openrouter_api_key=""),
            model="model-a",
            messages=[],
            max_tokens=10,
        )


@pytest.mark.asyncio
async def test_chat_completion_posts_non_stream_payload(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            calls["raised"] = True

        def json(self):
            return {"choices": [{"message": {"content": "  Done  "}}]}

    class FakeAsyncClient:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, json):
            calls.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)

    result = await client.openrouter_chat_completion(
        settings=_settings(),
        model="openrouter/auto",
        messages=[{"role": "user", "content": "Summarize"}],
        max_tokens=32,
        temperature=0.1,
    )

    assert result == "Done"
    assert calls["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls["headers"] == {"Authorization": "Bearer router-key"}
    assert calls["json"]["stream"] is False
    assert calls["json"]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_stream_tokens_yields_delta_content_and_text(monkeypatch):
    class FakeStreamResponse:
        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield ""
            yield "event: ping"
            yield 'data: {"choices":[{"delta":{"content":"Hel"}}]}'
            yield "data: not-json"
            yield 'data: {"choices":[{"delta":{"text":"lo"}}]}'
            yield "data: [DONE]"
            yield 'data: {"choices":[{"delta":{"content":"ignored"}}]}'

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeStreamResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, *, headers, json):
            assert method == "POST"
            assert url == "https://openrouter.ai/api/v1/chat/completions"
            assert headers["Accept"] == "text/event-stream"
            assert json["stream"] is True
            return FakeStreamContext()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)

    tokens = [
        token
        async for token in client.openrouter_stream_tokens(
            settings=_settings(),
            model="openrouter/auto",
            messages=[],
            max_tokens=10,
        )
    ]

    assert tokens == ["Hel", "lo"]
