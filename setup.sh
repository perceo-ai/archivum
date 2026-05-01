#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — fill in your values before continuing"
fi

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "backend/.venv/bin/python not found or not executable."
  echo "Run: cd backend && uv sync (or build the backend image), then retry."
  exit 1
fi

cd backend
backend/.venv/bin/python -m archivum.cli_config
