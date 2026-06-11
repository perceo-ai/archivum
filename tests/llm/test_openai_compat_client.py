from types import SimpleNamespace

import pytest

from archivum.llm import openai_compat_client as client


def _settings(**overrides):
    data = {
        "openai_compat_base_url": "",
        "openai_compat_provider": "openai",
        "openai_compat_api_key": "test-key",
        "openai_compat_azure_api_version": "2024-02-15-preview",
        "ollama_base_url": "http://localhost:11434",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_derive_base_url_uses_known_provider_default():
    assert client._derive_base_url(_settings(openai_compat_provider="groq")) == "https://api.groq.com/openai/v1"


def test_resolve_llm_endpoint_uses_ollama_without_auth_header():
    base_url, api_key, headers, params = client._resolve_llm_endpoint(_settings(), "ollama")

    assert base_url == "http://localhost:11434/v1"
    assert api_key == ""
    assert headers == {"Accept": "application/json"}
    assert params is None


def test_resolve_llm_endpoint_uses_azure_api_key_header_and_version_param():
    settings = _settings(
        openai_compat_base_url="https://example.openai.azure.com/openai/deployments/chat",
        openai_compat_api_key="azure-key",
    )

    base_url, api_key, headers, params = client._resolve_llm_endpoint(settings, "openai_compat")

    assert base_url == "https://example.openai.azure.com/openai/deployments/chat"
    assert api_key == ""
    assert headers["api-key"] == "azure-key"
    assert params == {"api-version": "2024-02-15-preview"}


@pytest.mark.asyncio
async def test_chat_completion_posts_openai_compatible_payload(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            calls["raised"] = True

        def json(self):
            return {"choices": [{"message": {"content": "  Answer text  "}}]}

    class FakeAsyncClient:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, params, json):
            calls.update({"url": url, "headers": headers, "params": params, "json": json})
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)

    result = await client.openai_compat_chat_completion(
        settings=_settings(openai_compat_provider="deepinfra"),
        provider="openai_compat",
        model="model-a",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=12,
        temperature=0.4,
    )

    assert result == "Answer text"
    assert calls["url"] == "https://api.deepinfra.com/v1/openai/chat/completions"
    assert calls["headers"]["Authorization"] == "Bearer test-key"
    assert calls["json"]["stream"] is False
    assert calls["json"]["max_tokens"] == 12
