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

    # ── Embeddings ─────────────────────────────────────────────────────────
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384

    # ── LLM ────────────────────────────────────────────────────────────────
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_synthesis_model: str = "claude-sonnet-4-6"

    # ── Multi-tenancy (future) ─────────────────────────────────────────────
    wiki_id: str = "default"

    # ── CORS ───────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ── MCP ────────────────────────────────────────────────────────────────
    mcp_port: int = 8001


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
