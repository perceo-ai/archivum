#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 20 or newer is required."
  echo "Install it from https://nodejs.org/ or with your OS package manager, then re-run: ./install.sh"
  exit 1
fi

if [[ -f packages/archivum-cli/src/index.js ]]; then
  exec node packages/archivum-cli/src/index.js install "$@"
fi

echo "The Archivum CLI was not found at packages/archivum-cli/src/index.js."
echo "Run this from a full checkout: git clone https://github.com/perceo-ai/archivum.git"
echo "(The unscoped 'archivum' package on npm is not ours, so there is no npx fallback.)"
exit 1
