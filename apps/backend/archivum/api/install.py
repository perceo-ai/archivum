"""The one line a fresh machine runs.

    curl -fsSL https://<server>/install | sh

Served by the vault itself rather than a package registry, which buys three
things: the URL already names the server, so nothing needs to be told where to
phone home; the CLI can never be a different version than the server it talks
to; and a machine with no registry access still links.

Nothing here authenticates. The script and the CLI are public code, and the
credential comes from the environment variable the script reads, never from
this endpoint.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response

from archivum.config import Settings, get_settings

router = APIRouter(tags=["install"])

CLI_ROOT = Path(__file__).resolve().parent.parent / "agent_cli"

# Excluded from the tarball rather than filtered on the way in, so a stray file
# in the vendored directory cannot end up on someone's machine.
_ALLOWED_SUFFIXES = {".js", ".json"}


def _api_base(request: Request, settings: Settings) -> str:
    configured = settings.api_public_url.strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def build_cli_tarball() -> bytes:
    """Pack the vendored CLI. Deterministic, so a re-download is a no-op."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=9) as tar:
        for path in sorted(CLI_ROOT.rglob("*")):
            if not path.is_file() or path.suffix not in _ALLOWED_SUFFIXES:
                continue
            info = tarfile.TarInfo(str(path.relative_to(CLI_ROOT)))
            data = path.read_bytes()
            info.size = len(data)
            # Fixed metadata: the same source must produce the same bytes, or
            # every poll looks like a new version.
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


INSTALL_SH = """#!/bin/sh
# Archivum installer. Served by the vault it installs against.
set -eu

BASE="{base}"
DEST="${{ARCHIVUM_HOME:-$HOME/.archivum}}"
CLI="$DEST/cli"
BIN="${{ARCHIVUM_BIN:-$HOME/.local/bin}}"

if ! command -v node >/dev/null 2>&1; then
  echo "archivum: node 20+ is required and was not found on PATH." >&2
  echo "  Install Node, then re-run this line." >&2
  exit 1
fi

NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if [ "$NODE_MAJOR" -lt 20 ]; then
  echo "archivum: node 20+ is required (found $(node -v))." >&2
  exit 1
fi

echo "archivum: fetching the CLI from $BASE"
mkdir -p "$CLI" "$BIN"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if ! curl -fsSL "$BASE/install/cli.tar.gz" -o "$TMP/cli.tar.gz"; then
  echo "archivum: could not download the CLI from $BASE." >&2
  exit 1
fi
# Replaced wholesale rather than merged: a half-updated CLI is worse than none.
rm -rf "$CLI"
mkdir -p "$CLI"
tar -xzf "$TMP/cli.tar.gz" -C "$CLI"

cat > "$BIN/archivum" <<LAUNCHER
#!/bin/sh
exec node "$CLI/src/index.js" "\\$@"
LAUNCHER
chmod +x "$BIN/archivum"
echo "archivum: installed $BIN/archivum"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "archivum: note - $BIN is not on your PATH; add it to use 'archivum' directly." >&2 ;;
esac

# Linking is the point of running this, so it happens here rather than being
# left as a second command nobody is around to type.
if [ -n "${{ARCHIVUM_PROVISION_TOKEN:-}}" ]; then
  echo "archivum: linking this machine"
  exec node "$CLI/src/index.js" connect --auto
fi

echo ""
echo "archivum: installed, but not linked - ARCHIVUM_PROVISION_TOKEN is not set."
echo "  Issue a provisioning token in Settings -> Agent Access, then:"
echo ""
echo "    export ARCHIVUM_PROVISION_TOKEN=arch1p_..."
echo "    archivum connect --auto"
echo ""
echo "  Or link this machine once with a pairing token:"
echo ""
echo "    archivum connect arch1_..."
"""


INSTALL_PS1 = """# Archivum installer. Served by the vault it installs against.
$ErrorActionPreference = 'Stop'

$Base = '{base}'
$Dest = if ($env:ARCHIVUM_HOME) {{ $env:ARCHIVUM_HOME }} else {{ Join-Path $HOME '.archivum' }}
$Cli  = Join-Path $Dest 'cli'
$Bin  = if ($env:ARCHIVUM_BIN) {{ $env:ARCHIVUM_BIN }} else {{ Join-Path $HOME '.local\\bin' }}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {{
  Write-Error 'archivum: node 20+ is required and was not found on PATH.'
}}

$NodeMajor = [int](node -p 'process.versions.node.split(".")[0]')
if ($NodeMajor -lt 20) {{
  Write-Error "archivum: node 20+ is required (found $(node -v))."
}}

Write-Host "archivum: fetching the CLI from $Base"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {{
  Invoke-WebRequest -Uri "$Base/install/cli.tar.gz" -OutFile "$Tmp\\cli.tar.gz" -UseBasicParsing
  if (Test-Path $Cli) {{ Remove-Item -Recurse -Force $Cli }}
  New-Item -ItemType Directory -Force -Path $Cli | Out-Null
  tar -xzf "$Tmp\\cli.tar.gz" -C $Cli
}} finally {{
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}}

$Launcher = Join-Path $Bin 'archivum.cmd'
Set-Content -Path $Launcher -Value "@echo off`r`nnode `"$Cli\\src\\index.js`" %*"
Write-Host "archivum: installed $Launcher"

if ($env:ARCHIVUM_PROVISION_TOKEN) {{
  Write-Host 'archivum: linking this machine'
  & node "$Cli\\src\\index.js" connect --auto
}} else {{
  Write-Host ''
  Write-Host 'archivum: installed, but not linked - ARCHIVUM_PROVISION_TOKEN is not set.'
  Write-Host '  Issue a provisioning token in Settings -> Agent Access, then:'
  Write-Host ''
  Write-Host '    $env:ARCHIVUM_PROVISION_TOKEN = "arch1p_..."'
  Write-Host '    archivum connect --auto'
}}
"""


@router.get("/install", response_class=PlainTextResponse)
async def install_script(
    request: Request, settings: Settings = Depends(get_settings)
) -> PlainTextResponse:
    return PlainTextResponse(
        INSTALL_SH.format(base=_api_base(request, settings)),
        media_type="text/x-shellscript",
    )


@router.get("/install.ps1", response_class=PlainTextResponse)
async def install_script_powershell(
    request: Request, settings: Settings = Depends(get_settings)
) -> PlainTextResponse:
    return PlainTextResponse(
        INSTALL_PS1.format(base=_api_base(request, settings)),
        media_type="text/plain",
    )


@router.get("/install/cli.tar.gz")
async def install_cli_tarball() -> Response:
    return Response(
        content=build_cli_tarball(),
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="archivum-cli.tar.gz"'},
    )
