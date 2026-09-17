#!/usr/bin/env bash
# Copy the CLI into the backend package so the Docker image can serve it.
#
# The backend build context is ./apps/backend, so COPY cannot reach
# packages/archivum-cli. Same reason the agent skill is vendored, same fix.
# tests/test_vendored_cli.py fails if these drift.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$root/packages/archivum-cli"
dest="$root/apps/backend/archivum/agent_cli"

rm -rf "$dest"
mkdir -p "$dest"
cp -R "$src/src" "$dest/src"
cp "$src/package.json" "$dest/package.json"
echo "vendored $(find "$dest" -type f | wc -l | tr -d ' ') files into apps/backend/archivum/agent_cli"
