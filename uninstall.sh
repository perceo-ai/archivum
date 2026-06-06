#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3 was not found."
  echo ""
  case "$(uname -s)" in
    Darwin)
      echo "Install Python from https://www.python.org/downloads/macos/ or with Homebrew:"
      echo "  brew install python"
      ;;
    Linux)
      echo "Install Python with your distro package manager, for example:"
      echo "  Ubuntu/Debian: sudo apt update && sudo apt install -y python3"
      echo "  Fedora:        sudo dnf install -y python3"
      echo "  Arch:          sudo pacman -S python"
      ;;
    *)
      echo "Install Python 3 from https://www.python.org/downloads/"
      ;;
  esac
  echo ""
  echo "Then re-run: ./uninstall.sh"
  exit 1
fi

exec "$PYTHON_BIN" scripts/uninstall.py "$@"
