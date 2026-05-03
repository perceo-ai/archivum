from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from archivum.logging_config import setup_logging


DEFAULTS: dict[str, str] = {
    "EMBED_PROVIDER": "local",
    "EMBED_MODEL": "BAAI/bge-small-en-v1.5",
    # .env.example defaults to 0 (auto-detect embedding dimension).
    "EMBED_DIM": "0",
    "EMBED_OPENAI_COMPAT_PROVIDER": "openai",
    "LLM_EXTRACTION_PROVIDER": "anthropic",
    "LLM_SYNTHESIS_PROVIDER": "anthropic",
    "LLM_MODEL": "claude-haiku-4-5-20251001",
    "LLM_SYNTHESIS_MODEL": "claude-sonnet-4-6",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "OPENAI_COMPAT_PROVIDER": "openai",
    "OLLAMA_BASE_URL": "http://localhost:11434",
}


def _looks_like_placeholder(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    v_l = v.lower()
    # Keep this deliberately simple; we just want to catch obvious “edit me” values.
    return (
        "change-me" in v_l
        or v_l == "changeme"
        or v_l == "changeme-replace-in-production"
        or v.startswith("sk-")
        or "openssl rand" in v_l
    )

ANTHROPIC_MODEL_DEFAULTS = {
    "extraction": "claude-haiku-4-5-20251001",
    "synthesis": "claude-sonnet-4-6",
}

OPENROUTER_MODEL_DEFAULTS = {
    "extraction": "openrouter/auto",
    "synthesis": "openrouter/auto",
}


def _mask_secret(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 12:
        return value[0:2] + "..." + value[-2:]
    return value[:6] + "..." + value[-4:]


def _find_env_file(start: Path) -> Path | None:
    cur = start.resolve()
    for i in range(0, 6):
        candidate = cur / ".env"
        if candidate.exists() and candidate.is_file():
            return candidate
        cur = cur.parent
    return None


def _parse_env_kv(lines: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        out[key] = value
    return out


def _set_env_var(lines: list[str], key: str, value: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(key)}=.*$")
    found = False
    for idx, line in enumerate(lines):
        if pattern.match(line.strip()):
            lines[idx] = f"{key}={value}\n"
            found = True
            break
    if not found:
        # Ensure there is a trailing newline before appending.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    return lines


def _prompt_choice(title: str, choices: list[str], default: str) -> str:
    print(title)
    for i, c in enumerate(choices, start=1):
        print(f"  {i}. {c}")
    raw = input(f"Select [default: {default}]: ").strip()
    if not raw:
        return default
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
    # Allow typing the value directly.
    if raw in choices:
        return raw
    print(f"Unknown choice '{raw}', using default '{default}'.")
    return default


def _prompt_text(title: str, default: str) -> str:
    raw = input(f"{title} [default: {default}]: ").strip()
    return raw if raw else default


def _prompt_secret(title: str, current: str) -> str:
    raw = input(f"{title} [current: {_mask_secret(current)}] (leave blank to keep): ").strip()
    return current if not raw else raw


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    # Prefer the current directory first (useful for container/exec contexts).
    cwd_env = Path.cwd() / ".env"
    repo_env = cwd_env if cwd_env.exists() and cwd_env.is_file() else _find_env_file(Path(__file__))
    if not repo_env:
        raise SystemExit("Could not find a `.env` file (searched up from backend/archivum).")

    env_lines = repo_env.read_text(encoding="utf-8").splitlines(keepends=True)
    kv = _parse_env_kv(env_lines)

    def get(key: str) -> str:
        return kv.get(key, DEFAULTS.get(key, ""))

    print(f"Configuring Archivum using: {repo_env}")
    print("")

    # ── Required app secrets ───────────────────────────────────────────────
    jwt_secret = get("JWT_SECRET")
    if _looks_like_placeholder(jwt_secret):
        jwt_secret = _prompt_secret("JWT signing secret (JWT_SECRET)", jwt_secret)
    else:
        print("JWT_SECRET looks set; leaving unchanged.")

    owner_password = get("OWNER_PASSWORD")
    if _looks_like_placeholder(owner_password):
        owner_password = _prompt_secret("Owner password (OWNER_PASSWORD)", owner_password)
    else:
        print("OWNER_PASSWORD looks set; leaving unchanged.")

    owner_username = get("OWNER_USERNAME") or "admin"
    if not owner_username.strip():
        owner_username = _prompt_text("Owner username (OWNER_USERNAME)", "admin")

    mcp_api_key = get("MCP_API_KEY")
    if _looks_like_placeholder(mcp_api_key):
        mcp_api_key = _prompt_secret("MCP API key (MCP_API_KEY)", mcp_api_key)
    else:
        print("MCP_API_KEY looks set; leaving unchanged.")

    if _looks_like_placeholder(jwt_secret):
        raise SystemExit("JWT_SECRET must be set to a non-placeholder value.")
    if _looks_like_placeholder(owner_password):
        raise SystemExit("OWNER_PASSWORD must be set to a non-placeholder value.")
    if _looks_like_placeholder(mcp_api_key):
        raise SystemExit("MCP_API_KEY must be set to a non-placeholder value.")

    archivum_host = get("ARCHIVUM_HOST")
    host_choice_default = "localhost-only" if not (archivum_host or "").strip() else "custom-domain"
    host_choice = _prompt_choice(
        "Public host for Caddy TLS (optional)?",
        ["localhost-only", "custom-domain"],
        host_choice_default,
    )
    if host_choice == "localhost-only":
        archivum_host = ""
    else:
        archivum_host = _prompt_text("Set ARCHIVUM_HOST (e.g. archivum.example.com)", archivum_host or "")

    # Embeddings (local or OpenAI-compatible)
    embed_provider = _prompt_choice(
        "Embeddings provider?",
        ["local", "openai_compat", "openrouter", "ollama"],
        get("EMBED_PROVIDER") or DEFAULTS["EMBED_PROVIDER"],
    )
    embed_model = _prompt_text("Embedding model (or Azure deployment name)", get("EMBED_MODEL"))
    embed_dim = _prompt_text("Embedding dimension (Qdrant collection size)", get("EMBED_DIM"))

    embed_openai_provider = _prompt_choice(
        "Embeddings OpenAI-compatible provider (only used if embeddings=openai_compat)",
        ["openai", "together", "fireworks", "groq", "deepinfra", "azure", "custom"],
        get("EMBED_OPENAI_COMPAT_PROVIDER") or DEFAULTS["EMBED_OPENAI_COMPAT_PROVIDER"],
    )
    embed_base_url = ""
    if embed_provider == "openai_compat" and embed_openai_provider in {"azure", "custom"}:
        embed_base_url = _prompt_text("Embeddings endpoint base URL (for azure/custom only)", get("EMBED_BASE_URL") or "")

    embed_api_key = get("EMBED_API_KEY") if "EMBED_API_KEY" in kv else ""
    if embed_provider == "openai_compat":
        embed_api_key = _prompt_secret("Embeddings API key (OpenAI-compatible)", embed_api_key)
    else:
        print("Embeddings provider is not openai_compat; leaving EMBED_API_KEY unchanged.")

    ollama_base_url = _prompt_text("Ollama base URL", get("OLLAMA_BASE_URL") or DEFAULTS["OLLAMA_BASE_URL"])

    # Extraction provider (entities + relationships)
    extraction_provider = _prompt_choice(
        "LLM extraction provider (entities + relationships)?",
        ["anthropic", "openrouter", "openai_compat", "ollama"],
        get("LLM_EXTRACTION_PROVIDER") or DEFAULTS["LLM_EXTRACTION_PROVIDER"],
    )
    default_extraction_model = kv.get(
        "LLM_MODEL",
        OPENROUTER_MODEL_DEFAULTS["extraction"]
        if extraction_provider == "openrouter"
        else ANTHROPIC_MODEL_DEFAULTS["extraction"],
    )
    llm_model = _prompt_text("Extraction model", default_extraction_model)

    # Synthesis provider (answers with citations)
    synthesis_provider = _prompt_choice(
        "LLM synthesis provider (query answering + citations)?",
        ["anthropic", "openrouter", "openai_compat", "ollama"],
        get("LLM_SYNTHESIS_PROVIDER") or DEFAULTS["LLM_SYNTHESIS_PROVIDER"],
    )
    default_synthesis_model = kv.get(
        "LLM_SYNTHESIS_MODEL",
        OPENROUTER_MODEL_DEFAULTS["synthesis"]
        if synthesis_provider == "openrouter"
        else ANTHROPIC_MODEL_DEFAULTS["synthesis"],
    )
    llm_synthesis_model = _prompt_text("Synthesis model", default_synthesis_model)

    # Keys/base URLs
    openrouter_api_key = get("OPENROUTER_API_KEY") if "OPENROUTER_API_KEY" in kv else ""
    openrouter_base_url = _prompt_text("OpenRouter base URL", get("OPENROUTER_BASE_URL") or DEFAULTS["OPENROUTER_BASE_URL"])

    if extraction_provider == "openrouter" or synthesis_provider == "openrouter":
        openrouter_api_key = _prompt_secret("OpenRouter API key", openrouter_api_key)
    else:
        print("OpenRouter not selected for this configuration; leaving OPENROUTER_API_KEY unchanged.")

    openai_compat_api_key = get("OPENAI_COMPAT_API_KEY") if "OPENAI_COMPAT_API_KEY" in kv else ""

    openai_compat_provider = _prompt_choice(
        "OpenAI-compatible LLM provider (only used if llm provider=openai_compat)",
        ["openai", "together", "fireworks", "groq", "deepinfra", "azure", "custom"],
        get("OPENAI_COMPAT_PROVIDER") or DEFAULTS["OPENAI_COMPAT_PROVIDER"],
    )
    openai_compat_base_url = ""
    if (extraction_provider == "openai_compat" or synthesis_provider == "openai_compat") and openai_compat_provider in {"azure", "custom"}:
        openai_compat_base_url = _prompt_text("OpenAI-compatible base URL (for azure/custom only)", get("OPENAI_COMPAT_BASE_URL") or "")

    if extraction_provider in {"openai_compat"} or synthesis_provider in {"openai_compat"}:
        openai_compat_api_key = _prompt_secret("OpenAI-compatible API key", openai_compat_api_key)
    else:
        print("OpenAI-compatible LLM not selected; leaving OPENAI_COMPAT_API_KEY unchanged.")

    anthropic_api_key = kv.get("ANTHROPIC_API_KEY", DEFAULTS.get("ANTHROPIC_API_KEY", ""))
    if extraction_provider == "anthropic" or synthesis_provider == "anthropic":
        anthropic_api_key = _prompt_secret("Anthropic API key", anthropic_api_key)
    else:
        print("Anthropic not selected for this configuration; leaving ANTHROPIC_API_KEY unchanged.")

    # Apply updates
    updates: list[tuple[str, str]] = [
        ("JWT_SECRET", jwt_secret),
        ("OWNER_PASSWORD", owner_password),
        ("OWNER_USERNAME", owner_username),
        ("MCP_API_KEY", mcp_api_key),
        ("ARCHIVUM_HOST", archivum_host),
        ("EMBED_PROVIDER", embed_provider),
        ("EMBED_MODEL", embed_model),
        ("EMBED_DIM", embed_dim),
        ("EMBED_OPENAI_COMPAT_PROVIDER", embed_openai_provider),
        ("EMBED_BASE_URL", embed_base_url),
        ("LLM_EXTRACTION_PROVIDER", extraction_provider),
        ("LLM_MODEL", llm_model),
        ("LLM_SYNTHESIS_PROVIDER", synthesis_provider),
        ("LLM_SYNTHESIS_MODEL", llm_synthesis_model),
        ("OPENROUTER_BASE_URL", openrouter_base_url),
        ("OPENAI_COMPAT_PROVIDER", openai_compat_provider),
        ("OPENAI_COMPAT_BASE_URL", openai_compat_base_url),
        ("OLLAMA_BASE_URL", ollama_base_url),
    ]

    if extraction_provider == "openrouter" or synthesis_provider == "openrouter":
        updates.append(("OPENROUTER_API_KEY", openrouter_api_key))

    if extraction_provider == "openai_compat" or synthesis_provider == "openai_compat":
        updates.append(("OPENAI_COMPAT_API_KEY", openai_compat_api_key))

    if extraction_provider == "anthropic" or synthesis_provider == "anthropic":
        updates.append(("ANTHROPIC_API_KEY", anthropic_api_key))

    if embed_provider == "openai_compat":
        updates.append(("EMBED_API_KEY", embed_api_key))

    for key, value in updates:
        # Avoid writing empty values for secrets if user opted to keep them.
        if value == "" and key in {"OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_COMPAT_API_KEY", "EMBED_API_KEY"}:
            continue
        env_lines = _set_env_var(env_lines, key, value)

    repo_env.write_text("".join(env_lines), encoding="utf-8")

    print("")
    print("Updated .env. Restart your stack to apply changes:")
    print("  docker compose up -d --build")


if __name__ == "__main__":
    main()
