#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${ARCHIVUM_REPO_URL:-https://github.com/pranavkannepalli/archivum.git}"
INSTALL_DIR="${ARCHIVUM_INSTALL_DIR:-$HOME/archivum}"
BRANCH="${ARCHIVUM_BRANCH:-main}"
RAW_BASE="${ARCHIVUM_RAW_BASE:-https://raw.githubusercontent.com/pranavkannepalli/archivum/$BRANCH}"
FULL_CLONE="${ARCHIVUM_FULL_CLONE:-0}"

say() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

sudo_cmd() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif need_cmd sudo; then
    sudo "$@"
  else
    fail "This step needs root permissions. Install sudo or run as root: $*"
  fi
}

install_packages_linux() {
  local packages=("$@")
  if need_cmd apt-get; then
    sudo_cmd apt-get update
    sudo_cmd apt-get install -y "${packages[@]}"
  elif need_cmd dnf; then
    sudo_cmd dnf install -y "${packages[@]}"
  elif need_cmd yum; then
    sudo_cmd yum install -y "${packages[@]}"
  elif need_cmd pacman; then
    local pacman_packages=()
    local package
    for package in "${packages[@]}"; do
      if [[ "$package" == "python3" ]]; then
        pacman_packages+=(python)
      else
        pacman_packages+=("$package")
      fi
    done
    sudo_cmd pacman -Sy --noconfirm "${pacman_packages[@]}"
  elif need_cmd zypper; then
    sudo_cmd zypper --non-interactive install "${packages[@]}"
  elif need_cmd apk; then
    sudo_cmd apk add --no-cache "${packages[@]}"
  else
    warn "No supported package manager found. Please install manually: ${packages[*]}"
  fi
}

ensure_basics() {
  case "$(uname -s)" in
    Linux)
      local packages=()
      need_cmd curl || packages+=(curl)
      need_cmd python3 || packages+=(python3)
      if [[ "$FULL_CLONE" == "1" ]]; then
        need_cmd git || packages+=(git)
      fi
      if [[ ${#packages[@]} -gt 0 ]]; then
        say "Installing required packages: ${packages[*]}"
        install_packages_linux "${packages[@]}"
      fi
      ;;
    Darwin)
      needs_macos_packages=0
      if ! need_cmd python3; then
        needs_macos_packages=1
      fi
      if [[ "$FULL_CLONE" == "1" ]] && ! need_cmd git; then
        needs_macos_packages=1
      fi
      if [[ "$needs_macos_packages" == "1" ]]; then
        if need_cmd brew; then
          say "Installing required packages with Homebrew."
          if [[ "$FULL_CLONE" == "1" ]]; then
            brew install git python
          else
            brew install python
          fi
        else
          fail "Install Homebrew from https://brew.sh or install Python 3, then re-run this command."
        fi
      fi
      ;;
    *)
      fail "Unsupported OS for bootstrap.sh. On Windows, use: irm https://raw.githubusercontent.com/pranavkannepalli/archivum/main/scripts/bootstrap.ps1 | iex"
      ;;
  esac
}

ensure_docker() {
  if need_cmd docker && docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    say "Docker is ready."
    return
  fi

  case "$(uname -s)" in
    Linux)
      if ! need_cmd docker; then
        say "Installing Docker using Docker's official convenience installer."
        curl -fsSL https://get.docker.com | sudo_cmd sh
      fi
      if need_cmd systemctl; then
        sudo_cmd systemctl enable --now docker || true
      fi
      if ! docker info >/dev/null 2>&1; then
        warn "Docker installed, but this user cannot access it yet."
        warn "Run: sudo usermod -aG docker \"$USER\""
        warn "Then log out and back in, or run this installer again with sudo."
        sudo_cmd docker info >/dev/null
      fi
      ;;
    Darwin)
      if need_cmd brew; then
        say "Installing Docker Desktop with Homebrew."
        brew install --cask docker || true
      fi
      open -a Docker >/dev/null 2>&1 || true
      warn "Waiting for Docker Desktop to start. Finish any Docker Desktop prompts."
      for _ in $(seq 1 90); do
        if docker info >/dev/null 2>&1; then
          say "Docker is ready."
          return
        fi
        sleep 2
      done
      fail "Docker Desktop did not become ready. Start Docker Desktop, then re-run this command."
      ;;
  esac
}

download_file() {
  local remote_path="$1"
  local local_path="$2"
  mkdir -p "$(dirname "$local_path")"
  curl -fsSL "$RAW_BASE/$remote_path" -o "$local_path"
}

fetch_minimal_files() {
  say "Downloading minimal Archivum runtime files into $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  download_file ".env.example" "$INSTALL_DIR/.env.example"
  download_file "docker-compose.yml" "$INSTALL_DIR/docker-compose.yml"
  download_file "docker-compose.images.yml" "$INSTALL_DIR/docker-compose.images.yml"
  download_file "caddy/Caddyfile" "$INSTALL_DIR/caddy/Caddyfile"
  download_file "scripts/install.py" "$INSTALL_DIR/scripts/install.py"
  chmod +x "$INSTALL_DIR/scripts/install.py"
}

fetch_full_repo() {
  need_cmd git || fail "Git is required for ARCHIVUM_FULL_CLONE=1."
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    say "Updating Archivum in $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --all --prune
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only
  else
    say "Cloning Archivum into $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  fi
}

main() {
  say "Archivum one-command installer"
  ensure_basics
  ensure_docker
  if [[ "$FULL_CLONE" == "1" ]]; then
    fetch_full_repo
  else
    fetch_minimal_files
  fi
  cd "$INSTALL_DIR"
  if [[ -r /dev/tty ]]; then
    python3 scripts/install.py --images </dev/tty
  else
    fail "No interactive terminal found. Download scripts/bootstrap.sh and run it from a terminal."
  fi
}

main "$@"
