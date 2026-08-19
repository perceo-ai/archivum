from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from pathlib import Path


class CliModelError(RuntimeError):
    pass


_CODEX_LOGIN_PROC: asyncio.subprocess.Process | None = None
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{5})\b")
_URL_RE = re.compile(r"https://auth\.openai\.com/codex/device")


def cli_status() -> dict[str, dict[str, str | bool]]:
    return {
        "codex_cli": {
            "available": shutil.which("codex") is not None,
            "command": shutil.which("codex") or "",
            "label": "Codex CLI",
        },
        "claude_cli": {
            "available": shutil.which("claude") is not None,
            "command": shutil.which("claude") or "",
            "label": "Claude Code",
        },
    }


async def codex_login_status() -> dict[str, str | bool]:
    command = shutil.which("codex")
    if not command:
        return {"available": False, "authenticated": False, "detail": "Codex CLI is not installed"}
    proc = await asyncio.create_subprocess_exec(
        command,
        "login",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
    output = _clean(stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace"))
    authenticated = proc.returncode == 0 and "not logged" not in output.lower() and "not authenticated" not in output.lower()
    return {
        "available": True,
        "authenticated": authenticated,
        "detail": output.strip() or ("Authenticated" if authenticated else "Not authenticated"),
    }


async def start_codex_device_login() -> dict[str, str | bool]:
    global _CODEX_LOGIN_PROC
    command = shutil.which("codex")
    if not command:
        raise CliModelError("Codex CLI is not installed on this server")

    if _CODEX_LOGIN_PROC and _CODEX_LOGIN_PROC.returncode is None:
        _CODEX_LOGIN_PROC.terminate()
        await _CODEX_LOGIN_PROC.wait()

    proc = await asyncio.create_subprocess_exec(
        command,
        "login",
        "--device-auth",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _CODEX_LOGIN_PROC = proc
    output = ""
    assert proc.stdout is not None
    deadline = asyncio.get_running_loop().time() + 12
    while asyncio.get_running_loop().time() < deadline:
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=1)
        except asyncio.TimeoutError:
            continue
        if not line:
            break
        output += line.decode("utf-8", errors="replace")
        clean = _clean(output)
        code = _CODE_RE.search(clean)
        if code and _URL_RE.search(clean):
            return {
                "started": True,
                "provider": "codex_cli",
                "url": "https://auth.openai.com/codex/device",
                "code": code.group(1),
                "detail": "Enter this code in the browser to authenticate Codex on the Archivum server.",
            }

    clean = _clean(output)
    raise CliModelError(clean.strip() or "Codex did not return a device login code")


async def cli_chat_completion(
    *,
    provider: str,
    model: str,
    prompt: str,
    timeout_seconds: int = 300,
) -> str:
    normalized = provider.strip().lower()
    command = shutil.which("codex" if normalized == "codex_cli" else "claude")
    if not command:
        raise CliModelError(f"{normalized} is not installed on this server")

    if normalized == "codex_cli":
        return await _run_codex(command, model=model, prompt=prompt, timeout_seconds=timeout_seconds)
    if normalized == "claude_cli":
        return await _run_claude(command, model=model, prompt=prompt, timeout_seconds=timeout_seconds)
    raise CliModelError(f"Unsupported CLI provider: {provider}")


async def _run_codex(command: str, *, model: str, prompt: str, timeout_seconds: int) -> str:
    with tempfile.TemporaryDirectory(prefix="archivum-codex-") as tmp:
        output_path = Path(tmp) / "answer.md"
        args = [
            command,
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
        ]
        if model.strip():
            args.extend(["--model", model.strip()])
        args.append("-")
        await _run_process(args, prompt, timeout_seconds=timeout_seconds)
        if output_path.exists():
            answer = output_path.read_text(encoding="utf-8", errors="replace").strip()
            if answer:
                return answer
        raise CliModelError("Codex CLI completed without an answer")


async def _run_claude(command: str, *, model: str, prompt: str, timeout_seconds: int) -> str:
    args = [
        command,
        "--print",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "text",
    ]
    if model.strip():
        args.extend(["--model", model.strip()])
    args.append(prompt)
    return await _run_process(args, None, timeout_seconds=timeout_seconds)


async def _run_process(args: list[str], stdin: str | None, *, timeout_seconds: int) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(stdin.encode("utf-8") if stdin is not None else None),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise CliModelError(f"CLI model timed out after {timeout_seconds} seconds") from exc

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        detail = err or out or f"exit code {proc.returncode}"
        raise CliModelError(f"CLI model failed: {detail[-800:]}")
    return out


def _clean(text: str) -> str:
    return _ANSI_RE.sub("", text)
