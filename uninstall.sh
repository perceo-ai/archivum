#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 20 or newer is required."
  echo "Install it from https://nodejs.org/ or with your OS package manager, then re-run: ./uninstall.sh"
  exit 1
fi

if [[ -f packages/archivum-cli/src/index.js ]]; then
  exec node packages/archivum-cli/src/index.js uninstall "$@"
fi

exec npx --yes archivum uninstall "$@"
