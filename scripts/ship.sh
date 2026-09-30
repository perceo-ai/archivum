#!/usr/bin/env bash
# Ship main to perceo-control, then bring this machine's `archivum` up to date
# from the server that was just deployed.
#
#   make ship          # deploy + refresh the CLI here
#   make ship-check    # report deploy state, change nothing
#
# The deploy pulls origin/main on the target, so merge first; what is checked
# out here does not matter. The CLI is refreshed through the served installer
# rather than `archivum self-update` because the CLI already on this machine
# may predate that command.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$root/scripts/deploy-perceo-control.sh" "$@"
[ "${1:-}" = "--check" ] && exit 0

base="${ARCHIVUM_URL:-}"
if [ -z "$base" ] && [ -f "$HOME/.archivum/connection.json" ]; then
  base=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("base_url",""))' "$HOME/.archivum/connection.json")
fi
if [ -z "$base" ] && command -v docker >/dev/null 2>&1; then
  published=$(docker port archivum-backend 8000 2>/dev/null | head -1 || true)
  [ -n "$published" ] && base="http://$published"
fi
if [ -z "$base" ]; then
  echo "→ Deployed. No server address known here; set ARCHIVUM_URL to refresh the CLI." >&2
  exit 0
fi

echo "→ Refreshing the CLI on $(hostname) from $base"
curl -fsSL "${base%/}/install" | sh
