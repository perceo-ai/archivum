#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BRANCH="${ARCHIVUM_BRANCH:-main}"
RAW_BASE="${ARCHIVUM_RAW_BASE:-https://raw.githubusercontent.com/pranavkannepalli/archivum/$BRANCH}"
USE_IMAGES=1

say() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
Usage: ./update.sh [--images|--build]

Updates Archivum runtime files, refreshes Docker images or local builds, and
restarts the Docker Compose stack while preserving .env and Docker volumes.

Options:
  --images  Pull and run published images from GHCR (default).
  --build   Build images locally from this checkout.
  -h, --help  Show this help.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --images)
      USE_IMAGES=1
      ;;
    --build)
      USE_IMAGES=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $arg"
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

compose_cmd() {
  if need_cmd docker && docker compose version >/dev/null 2>&1; then
    printf 'docker compose'
  elif need_cmd docker-compose && docker-compose version >/dev/null 2>&1; then
    printf 'docker-compose'
  else
    fail "Docker Compose was not found. Install Docker, then re-run ./update.sh."
  fi
}

download_file() {
  local remote_path="$1"
  local local_path="$2"
  local tmp_path
  mkdir -p "$(dirname "$local_path")"
  tmp_path="$(mktemp "$local_path.tmp.XXXXXX")"
  curl -fsSL "$RAW_BASE/$remote_path" -o "$tmp_path"
  mv "$tmp_path" "$local_path"
}

update_minimal_files() {
  need_cmd curl || fail "curl is required to update a minimal Archivum install."

  say "Updating Archivum runtime files from $RAW_BASE"
  download_file ".env.example" ".env.example"
  download_file "docker-compose.yml" "docker-compose.yml"
  download_file "docker-compose.images.yml" "docker-compose.images.yml"
  download_file "caddy/Caddyfile" "caddy/Caddyfile"
  download_file "scripts/install.py" "scripts/install.py"
  download_file "scripts/uninstall.py" "scripts/uninstall.py"
  download_file "uninstall.sh" "uninstall.sh"
  download_file "update.sh" "update.sh"
  chmod +x scripts/install.py scripts/uninstall.py uninstall.sh update.sh
}

update_checkout() {
  say "Updating Git checkout"
  git fetch --all --prune
  git pull --ff-only
}

ensure_env() {
  if [[ ! -f .env ]]; then
    if [[ ! -f .env.example ]]; then
      fail "Missing .env and .env.example; cannot create default configuration."
    fi
    cp .env.example .env
    warn "Created .env from .env.example. Review it before relying on the updated stack."
  fi
}

restart_stack() {
  local compose
  compose="$(compose_cmd)"

  if ! docker info >/dev/null 2>&1; then
    fail "Docker is not running or this user cannot access it."
  fi

  if [[ "$USE_IMAGES" == "1" ]]; then
    say "Pulling published Docker images"
    $compose -f docker-compose.yml -f docker-compose.images.yml pull

    say "Restarting Archivum with published images"
    $compose -f docker-compose.yml -f docker-compose.images.yml up -d --no-build --remove-orphans
  else
    say "Rebuilding local Docker images"
    $compose build --pull

    say "Restarting Archivum with local builds"
    $compose up -d --build --remove-orphans
  fi
}

main() {
  say "Archivum updater"

  if [[ -d .git ]]; then
    update_checkout
  else
    update_minimal_files
  fi

  ensure_env
  restart_stack

  say "Archivum update completed."
  echo "Run 'docker compose logs -f' if you want to follow startup logs."
}

main
