#!/usr/bin/env python3
"""Cross-platform Archivum installer.

Uses only the Python standard library so it can run on macOS, Linux, and
Windows once Python is available. The shell/PowerShell launchers handle the
"Python not found" case with platform-specific instructions.
"""

from __future__ import annotations

import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import textwrap
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"


PROVIDER_OPTIONS = ["anthropic", "openrouter", "openai_compat", "ollama"]
OPENAI_COMPAT_OPTIONS = ["openai", "together", "fireworks", "groq", "deepinfra", "azure", "custom"]
EMBED_OPTIONS = ["local", "openai_compat", "openrouter", "ollama"]

DEFAULTS = {
    "ANTHROPIC_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "JWT_SECRET": "",
    "OWNER_PASSWORD": "",
    "OWNER_USERNAME": "admin",
    "MCP_API_KEY": "",
    "ARCHIVUM_HOST": "",
    "PUBLIC_WIKI_ENABLED": "false",
    "EMBED_PROVIDER": "local",
    "EMBED_MODEL": "BAAI/bge-small-en-v1.5",
    "EMBED_DIM": "0",
    "EMBED_OPENAI_COMPAT_PROVIDER": "openai",
    "EMBED_BASE_URL": "",
    "EMBED_API_KEY": "",
    "EMBED_AZURE_API_VERSION": "2024-02-15-preview",
    "OLLAMA_BASE_URL": "http://host.docker.internal:11434",
    "LLM_EXTRACTION_PROVIDER": "anthropic",
    "LLM_SYNTHESIS_PROVIDER": "anthropic",
    "LLM_MODEL": "claude-haiku-4-5-20251001",
    "LLM_SYNTHESIS_MODEL": "claude-sonnet-4-6",
    "OPENAI_COMPAT_PROVIDER": "openai",
    "OPENAI_COMPAT_BASE_URL": "",
    "OPENAI_COMPAT_API_KEY": "",
    "OPENAI_COMPAT_AZURE_API_VERSION": "2024-02-15-preview",
}


MODEL_PRESETS = {
    "anthropic": {
        "extraction": "claude-haiku-4-5-20251001",
        "synthesis": "claude-sonnet-4-6",
    },
    "openrouter": {
        "extraction": "openrouter/auto",
        "synthesis": "openrouter/auto",
    },
    "openai_compat": {
        "extraction": "gpt-4o-mini",
        "synthesis": "gpt-4o",
    },
    "ollama": {
        "extraction": "llama3.1",
        "synthesis": "llama3.1",
    },
}


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(value: str, code: str) -> str:
    if not supports_color():
        return value
    return f"{code}{value}{RESET}"


def clear() -> None:
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def line() -> None:
    print(color("─" * 72, DIM))


def header(title: str, subtitle: str = "") -> None:
    clear()
    print(color("╭" + "─" * 70 + "╮", CYAN))
    print(color("│", CYAN) + color(f" Archivum Installer".ljust(70), BOLD) + color("│", CYAN))
    print(color("│", CYAN) + f" {title}".ljust(70) + color("│", CYAN))
    if subtitle:
        print(color("│", CYAN) + color(f" {subtitle}".ljust(70), DIM) + color("│", CYAN))
    print(color("╰" + "─" * 70 + "╯", CYAN))
    print()


def info(message: str) -> None:
    print(color("• ", CYAN) + message)


def ok(message: str) -> None:
    print(color("✓ ", GREEN) + message)


def warn(message: str) -> None:
    print(color("! ", YELLOW) + message)


def error(message: str) -> None:
    print(color("✗ ", RED) + message)


def pause() -> None:
    input(color("\nPress Enter to continue...", DIM))


def run(cmd: list[str], *, cwd: Path = ROOT, check: bool = False, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def parse_args(argv: list[str]) -> dict[str, bool]:
    return {
        "use_images": "--build" not in argv,
        "force_images": "--images" in argv,
    }


def compose_command(compose: list[str], *, use_images: bool) -> list[str]:
    if not use_images:
        return compose
    return compose + ["-f", "docker-compose.yml", "-f", "docker-compose.images.yml"]


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        if not ENV_EXAMPLE.exists():
            raise SystemExit("Missing .env.example; cannot create .env.")
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    values = DEFAULTS.copy()
    values.update(parse_env(ENV_FILE.read_text(encoding="utf-8")))
    return values


def write_env(values: dict[str, str]) -> None:
    existing = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True) if ENV_FILE.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=.*$")

    for line_text in existing:
        match = pattern.match(line_text.strip())
        if not match:
            output.append(line_text)
            continue
        key = match.group(1)
        if key in values:
            existing_value = parse_env(line_text).get(key, "")
            if key.endswith("_API_KEY") and has_secret({"existing": existing_value}, "existing") and not has_secret(values, key):
                output.append(line_text)
                seen.add(key)
                continue
            output.append(f"{key}={values[key]}\n")
            seen.add(key)
        else:
            output.append(line_text)

    missing_keys = [key for key in DEFAULTS if key not in seen and key in values]
    if missing_keys:
        if output and not output[-1].endswith("\n"):
            output[-1] += "\n"
        output.append("\n# ─── Installer-managed values ───────────────────────────────────────────────\n")
        for key in missing_keys:
            output.append(f"{key}={values[key]}\n")

    ENV_FILE.write_text("".join(output), encoding="utf-8")


def is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    return (
        "change-me" in normalized
        or normalized == "changeme"
        or "replace-in-production" in normalized
        or "openssl rand" in normalized
        or normalized.endswith("...")
    )


def secret_default(value: str) -> str:
    if is_placeholder_secret(value):
        return ""
    return value


def has_value(values: dict[str, str], key: str) -> bool:
    return bool(values.get(key, "").strip())


def has_secret(values: dict[str, str], key: str) -> bool:
    return not is_placeholder_secret(values.get(key, ""))


def env_needs_configuration(values: dict[str, str]) -> bool:
    for key in ("OWNER_PASSWORD", "JWT_SECRET", "MCP_API_KEY"):
        if not has_secret(values, key):
            return True

    extraction = values.get("LLM_EXTRACTION_PROVIDER", "")
    synthesis = values.get("LLM_SYNTHESIS_PROVIDER", "")
    selected_llms = {extraction, synthesis}
    if not selected_llms <= set(PROVIDER_OPTIONS) or "" in selected_llms:
        return True
    if not has_value(values, "LLM_MODEL") or not has_value(values, "LLM_SYNTHESIS_MODEL"):
        return True
    if "anthropic" in selected_llms and not has_secret(values, "ANTHROPIC_API_KEY"):
        return True
    if "openrouter" in selected_llms and (
        not has_value(values, "OPENROUTER_BASE_URL") or not has_secret(values, "OPENROUTER_API_KEY")
    ):
        return True
    if "openai_compat" in selected_llms:
        if values.get("OPENAI_COMPAT_PROVIDER") not in OPENAI_COMPAT_OPTIONS:
            return True
        if values.get("OPENAI_COMPAT_PROVIDER") in {"azure", "custom"} and not has_value(values, "OPENAI_COMPAT_BASE_URL"):
            return True
        if not has_secret(values, "OPENAI_COMPAT_API_KEY"):
            return True
    if "ollama" in selected_llms and not has_value(values, "OLLAMA_BASE_URL"):
        return True

    embed_provider = values.get("EMBED_PROVIDER", "")
    if embed_provider not in EMBED_OPTIONS:
        return True
    if not has_value(values, "EMBED_MODEL") or not has_value(values, "EMBED_DIM"):
        return True
    if embed_provider == "openai_compat":
        if values.get("EMBED_OPENAI_COMPAT_PROVIDER") not in OPENAI_COMPAT_OPTIONS:
            return True
        if values.get("EMBED_OPENAI_COMPAT_PROVIDER") in {"azure", "custom"} and not has_value(values, "EMBED_BASE_URL"):
            return True
        if not has_secret(values, "EMBED_API_KEY"):
            return True
    if embed_provider == "openrouter" and (
        not has_value(values, "OPENROUTER_BASE_URL") or not has_secret(values, "OPENROUTER_API_KEY")
    ):
        return True
    if embed_provider == "ollama" and not has_value(values, "OLLAMA_BASE_URL"):
        return True

    return False


def mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 10:
        return value[:2] + "..." + value[-2:]
    return value[:6] + "..." + value[-4:]


def ask_text(label: str, default: str = "", *, required: bool = False, secret: bool = False) -> str:
    while True:
        shown = mask(default) if secret else default
        prompt = f"{label}"
        if shown:
            prompt += f" [{shown}]"
        prompt += ": "
        value = input(prompt).strip()
        if not value:
            value = default
        if value or not required:
            return value
        warn("Required value.")


def ask_bool(label: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{label} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1", "on"}


def ask_choice(label: str, choices: list[str], default: str) -> str:
    if default not in choices:
        default = choices[0]
    print(label)
    for idx, choice in enumerate(choices, start=1):
        marker = color("  →", GREEN) if choice == default else "   "
        print(f"{marker} {idx}. {choice}")
    raw = input(f"Select 1-{len(choices)} [{default}]: ").strip()
    if not raw:
        return default
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
    if raw in choices:
        return raw
    warn(f"Unknown choice '{raw}', using {default}.")
    return default


def generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def docker_install_url() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "https://docs.docker.com/desktop/setup/install/mac-install/"
    if system == "windows":
        return "https://docs.docker.com/desktop/setup/install/windows-install/"
    return "https://docs.docker.com/engine/install/"


def docker_instructions() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return textwrap.dedent(
            """
            Install Docker Desktop for Mac:
              1. Open https://docs.docker.com/desktop/setup/install/mac-install/
              2. Install Docker Desktop.
              3. Start Docker Desktop and wait until it says "Docker is running".
              4. Re-run this installer.
            """
        ).strip()
    if system == "windows":
        return textwrap.dedent(
            """
            Install Docker Desktop for Windows:
              1. Open https://docs.docker.com/desktop/setup/install/windows-install/
              2. Install Docker Desktop with WSL 2 enabled.
              3. Reboot if prompted.
              4. Start Docker Desktop and wait until it says "Docker is running".
              5. Re-run this installer from PowerShell.
            """
        ).strip()
    return textwrap.dedent(
        """
        Install Docker Engine for your Linux distro:
          Ubuntu/Debian: https://docs.docker.com/engine/install/ubuntu/
          Fedora:        https://docs.docker.com/engine/install/fedora/
          CentOS/RHEL:   https://docs.docker.com/engine/install/centos/
          Arch:          sudo pacman -S docker docker-compose

        After installing, enable and start Docker:
          sudo systemctl enable --now docker

        Optional, let your user run Docker without sudo:
          sudo usermod -aG docker "$USER"
          # then log out and back in
        """
    ).strip()


def find_compose_command() -> list[str] | None:
    docker = shutil.which("docker")
    if docker:
        result = run([docker, "compose", "version"])
        if result.returncode == 0:
            return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    if legacy:
        result = run([legacy, "version"])
        if result.returncode == 0:
            return [legacy]
    return None


def docker_ready(compose: list[str] | None) -> bool:
    docker = shutil.which("docker")
    if not docker or not compose:
        return False
    result = run([docker, "info"])
    return result.returncode == 0


def ensure_docker() -> list[str] | None:
    header("Docker Check", "Archivum runs permanently through Docker Compose.")
    compose = find_compose_command()
    if docker_ready(compose):
        ok("Docker and Docker Compose are ready.")
        return compose

    error("Docker is not installed, Docker Compose is missing, or the Docker daemon is not running.")
    print()
    print(docker_instructions())
    print()
    if ask_bool("Open Docker install instructions in your browser?", default=True):
        webbrowser.open(docker_install_url())
    print()
    warn("Install/start Docker, then run this installer again.")
    return None


def configure_access(values: dict[str, str]) -> None:
    header("Access Control", "Create the owner login and server secrets.")
    values["OWNER_USERNAME"] = ask_text("Owner username", values.get("OWNER_USERNAME") or "admin", required=True)

    current_pw = secret_default(values.get("OWNER_PASSWORD", ""))
    if current_pw:
        keep = ask_bool(f"Keep existing owner password {mask(current_pw)}?", default=True)
        values["OWNER_PASSWORD"] = current_pw if keep else ask_text("New owner password", required=True, secret=True)
    else:
        values["OWNER_PASSWORD"] = ask_text("Owner password", required=True, secret=True)

    if not secret_default(values.get("JWT_SECRET", "")):
        values["JWT_SECRET"] = generate_secret(48)
        ok("Generated JWT_SECRET.")
    if not secret_default(values.get("MCP_API_KEY", "")):
        values["MCP_API_KEY"] = generate_secret(32)
        ok("Generated MCP_API_KEY.")

    values["PUBLIC_WIKI_ENABLED"] = "true" if ask_bool(
        "Expose the entire wiki publicly as read-only at /public?",
        default=(values.get("PUBLIC_WIKI_ENABLED", "false").lower() == "true"),
    ) else "false"

    public_host = ask_bool("Use a public domain with Caddy TLS?", default=bool(values.get("ARCHIVUM_HOST", "").strip()))
    values["ARCHIVUM_HOST"] = ask_text("Domain, for example archivum.example.com", values.get("ARCHIVUM_HOST", ""), required=True) if public_host else ""


def configure_llms(values: dict[str, str]) -> None:
    header("AI Providers", "Pick providers independently for ingest extraction and query answers.")
    extraction = ask_choice("Extraction provider: entities, relationships, generated pages", PROVIDER_OPTIONS, values.get("LLM_EXTRACTION_PROVIDER", "anthropic"))
    synthesis = ask_choice("Synthesis provider: question answering with citations", PROVIDER_OPTIONS, values.get("LLM_SYNTHESIS_PROVIDER", "anthropic"))
    values["LLM_EXTRACTION_PROVIDER"] = extraction
    values["LLM_SYNTHESIS_PROVIDER"] = synthesis

    values["LLM_MODEL"] = ask_text(
        "Extraction model",
        values.get("LLM_MODEL") or MODEL_PRESETS[extraction]["extraction"],
        required=True,
    )
    values["LLM_SYNTHESIS_MODEL"] = ask_text(
        "Synthesis model",
        values.get("LLM_SYNTHESIS_MODEL") or MODEL_PRESETS[synthesis]["synthesis"],
        required=True,
    )

    selected = {extraction, synthesis}
    if "anthropic" in selected:
        values["ANTHROPIC_API_KEY"] = ask_text("Anthropic API key", secret_default(values.get("ANTHROPIC_API_KEY", "")), required=True, secret=True)
    if "openrouter" in selected:
        values["OPENROUTER_BASE_URL"] = ask_text("OpenRouter base URL", values.get("OPENROUTER_BASE_URL") or DEFAULTS["OPENROUTER_BASE_URL"], required=True)
        values["OPENROUTER_API_KEY"] = ask_text("OpenRouter API key", secret_default(values.get("OPENROUTER_API_KEY", "")), required=True, secret=True)
    if "openai_compat" in selected:
        values["OPENAI_COMPAT_PROVIDER"] = ask_choice("OpenAI-compatible provider", OPENAI_COMPAT_OPTIONS, values.get("OPENAI_COMPAT_PROVIDER", "openai"))
        if values["OPENAI_COMPAT_PROVIDER"] in {"azure", "custom"}:
            values["OPENAI_COMPAT_BASE_URL"] = ask_text("OpenAI-compatible base URL", values.get("OPENAI_COMPAT_BASE_URL", ""), required=True)
        else:
            values["OPENAI_COMPAT_BASE_URL"] = values.get("OPENAI_COMPAT_BASE_URL", "")
        values["OPENAI_COMPAT_API_KEY"] = ask_text("OpenAI-compatible API key", secret_default(values.get("OPENAI_COMPAT_API_KEY", "")), required=True, secret=True)
    if "ollama" in selected:
        values["OLLAMA_BASE_URL"] = ask_text("Ollama base URL", values.get("OLLAMA_BASE_URL") or DEFAULTS["OLLAMA_BASE_URL"], required=True)


def configure_embeddings(values: dict[str, str]) -> None:
    header("Embeddings", "Local embeddings are simplest and avoid another API key.")
    provider = ask_choice("Embedding provider", EMBED_OPTIONS, values.get("EMBED_PROVIDER", "local"))
    values["EMBED_PROVIDER"] = provider
    values["EMBED_MODEL"] = ask_text("Embedding model", values.get("EMBED_MODEL") or DEFAULTS["EMBED_MODEL"], required=True)
    values["EMBED_DIM"] = ask_text("Embedding dimension, 0 means auto-detect", values.get("EMBED_DIM") or "0", required=True)

    if provider == "openai_compat":
        values["EMBED_OPENAI_COMPAT_PROVIDER"] = ask_choice(
            "Embeddings OpenAI-compatible provider",
            OPENAI_COMPAT_OPTIONS,
            values.get("EMBED_OPENAI_COMPAT_PROVIDER", "openai"),
        )
        if values["EMBED_OPENAI_COMPAT_PROVIDER"] in {"azure", "custom"}:
            values["EMBED_BASE_URL"] = ask_text("Embeddings base URL", values.get("EMBED_BASE_URL", ""), required=True)
        values["EMBED_API_KEY"] = ask_text("Embeddings API key", secret_default(values.get("EMBED_API_KEY", "")), required=True, secret=True)
    elif provider == "ollama":
        values["OLLAMA_BASE_URL"] = ask_text("Ollama base URL", values.get("OLLAMA_BASE_URL") or DEFAULTS["OLLAMA_BASE_URL"], required=True)
    elif provider == "openrouter":
        values["OPENROUTER_BASE_URL"] = ask_text("OpenRouter base URL", values.get("OPENROUTER_BASE_URL") or DEFAULTS["OPENROUTER_BASE_URL"], required=True)
        values["OPENROUTER_API_KEY"] = ask_text("OpenRouter API key", secret_default(values.get("OPENROUTER_API_KEY", "")), required=True, secret=True)


def summary(values: dict[str, str]) -> bool:
    header("Review", "No secrets are printed in full.")
    rows = [
        ("Owner", values["OWNER_USERNAME"]),
        ("Public wiki", values["PUBLIC_WIKI_ENABLED"]),
        ("Host", values["ARCHIVUM_HOST"] or "localhost"),
        ("Extraction", f"{values['LLM_EXTRACTION_PROVIDER']} / {values['LLM_MODEL']}"),
        ("Synthesis", f"{values['LLM_SYNTHESIS_PROVIDER']} / {values['LLM_SYNTHESIS_MODEL']}"),
        ("Embeddings", f"{values['EMBED_PROVIDER']} / {values['EMBED_MODEL']}"),
        ("MCP API key", mask(values["MCP_API_KEY"])),
    ]
    for key, value in rows:
        print(f"{color(key + ':', BOLD):<24} {value}")
    line()
    return ask_bool("Write .env and continue?", default=True)


def start_stack(compose: list[str], *, use_images: bool) -> bool:
    header("Start Archivum", "This starts containers with restart policies.")
    base = compose_command(compose, use_images=use_images)
    if use_images:
        cmd = base + ["up", "-d", "--no-build"]
        info("Using published Docker images. Use --build if you want to build locally.")
    else:
        cmd = base + ["up", "-d", "--build"]
        info("Building Docker images locally.")
    info("Running: " + " ".join(cmd))
    result = run(cmd, capture=False)
    if result.returncode != 0:
        error("Docker Compose failed.")
        return False

    ok("Containers started.")
    info("Waiting briefly for services to settle...")
    time.sleep(3)
    ps = run(base + ["ps"])
    print(ps.stdout or "")
    return True


def print_finish(values: dict[str, str]) -> None:
    host = values.get("ARCHIVUM_HOST") or "localhost"
    scheme = "https"
    header("Done", "Archivum is installed and running.")
    print(f"Web UI:       {color(f'{scheme}://{host}', GREEN)}")
    print(f"Public wiki:  {scheme}://{host}/public")
    print(f"MCP SSE:      http://localhost:8001/sse")
    print(f"MCP bearer:   {mask(values['MCP_API_KEY'])}")
    print()
    print("Useful commands:")
    print("  docker compose logs -f")
    print("  docker compose ps")
    print("  docker compose down")
    print("  docker compose up -d")
    print()
    if platform.system().lower() == "linux":
        print("Permanent startup note: Docker services are configured with restart: unless-stopped.")
        print("Make sure Docker itself starts on boot: sudo systemctl enable --now docker")
    else:
        print("Permanent startup note: containers use restart: unless-stopped.")
        print("Enable Docker Desktop to start when you log in if you want Archivum always on.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    os.chdir(ROOT)
    header("Welcome", "Configure keys, providers, Docker, and startup in one pass.")
    print("This installer writes `.env` and starts Archivum with Docker Compose.")
    print("By default it pulls published images, so users do not build packages locally.")
    print("It does not send your API keys anywhere except into your local `.env` file.")
    pause()

    compose = ensure_docker()
    if compose is None:
        return 1

    values = read_env()
    if env_needs_configuration(values) or ask_bool("Reconfigure existing .env?", default=False):
        configure_access(values)
        configure_llms(values)
        configure_embeddings(values)
        if not summary(values):
            warn("Cancelled before writing changes.")
            return 1

        write_env(values)
        ok(f"Wrote {ENV_FILE}")
    else:
        ok("Keeping existing .env unchanged.")

    if ask_bool("Start Archivum now?", default=True):
        if not start_stack(compose, use_images=args["use_images"] or args["force_images"]):
            return 1
    print_finish(values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
