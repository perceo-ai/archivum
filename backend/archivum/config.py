"""Application configuration via pydantic-settings (reads from .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ── Security ───────────────────────────────────────────────────────────
    jwt_secret: str = "changeme-replace-in-production"
    # Plaintext on first boot; bcrypt hash stored in DB afterwards.
    owner_password: str = "changeme"
    owner_username: str = "admin"

    # ── Token lifetimes ────────────────────────────────────────────────────
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Data paths ─────────────────────────────────────────────────────────
    wiki_dir: Path = Path("/data/wiki")
    raw_dir: Path = Path("/data/raw")
    db_path: Path = Path("/data/archivum.db")
    kuzu_path: Path = Path("/data/kuzu")

    # ── Qdrant ─────────────────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "archivum"
    qdrant_recreate_collection_on_dim_mismatch: bool = False

    # ── Embeddings ─────────────────────────────────────────────────────────
    # Embeddings can be either local (fastembed) or any OpenAI-compatible provider.
    # Supported: local|openai_compat|openrouter|ollama
    embed_provider: str = "local"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    # Vector size in Qdrant. Set to 0 to auto-detect from the embedding provider/model.
    embed_dim: int = 0

    # OpenAI-compatible embeddings provider selection (used when embed_provider=openai_compat).
    # We derive a base URL from this for common providers.
    # Supported: openai|together|fireworks|groq|deepinfra|custom|azure
    embed_openai_compat_provider: str = "openai"
    # Optional override (mostly for custom/azure). If empty, we derive from provider.
    embed_base_url: str = ""
    embed_api_key: str = ""
    # Azure OpenAI embeddings support (when embed_provider=openai_compat and base URL is an Azure endpoint).
    embed_azure_api_version: str = "2024-02-15-preview"

    # Ollama base URL (when embed_provider=ollama or llm_*_provider=ollama)
    # Ollama's OpenAI-compat endpoints are typically at `${OLLAMA_BASE_URL}/v1`.
    ollama_base_url: str = "http://localhost:11434"

    # ── LLM ────────────────────────────────────────────────────────────────
    # LLM provider + model selection is split by pipeline stage so you can,
    # for example, run paid extraction but free/cheaper synthesis (or vice versa).
    #
    # Extraction (entities + relationships):
    # Supported: anthropic|openrouter|openai_compat|ollama
    llm_extraction_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"

    # Query synthesis (answers with citations):
    # Supported: anthropic|openrouter|openai_compat|ollama
    llm_synthesis_provider: str = "anthropic"
    llm_synthesis_model: str = "claude-sonnet-4-6"

    # OpenRouter (OpenAI-compatible endpoint)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Generic OpenAI-compatible endpoint (covers OpenAI, Together, Fireworks, etc.)
    # Set LLM_*_PROVIDER=openai_compat and provide these values.
    openai_compat_api_key: str = ""
    # Prefer provider-based selection; only set base_url for custom/azure.
    # Supported: openai|together|fireworks|groq|deepinfra|custom|azure
    openai_compat_provider: str = "openai"
    openai_compat_base_url: str = ""
    openai_compat_azure_api_version: str = "2024-02-15-preview"

    # ── Multi-tenancy (future) ─────────────────────────────────────────────
    wiki_id: str = "default"

    # ── CORS ───────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ── Rate limiting (cap API costs) ─────────────────────────────────────
    # Defaults are conservative; tune via env vars.
    rate_limit_login_requests: int = 10
    rate_limit_login_window_seconds: int = 600  # 10 minutes
    rate_limit_api_requests: int = 120
    rate_limit_api_window_seconds: int = 60

    # ── MCP ────────────────────────────────────────────────────────────────
    mcp_port: int = 8001
    mcp_api_key: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
