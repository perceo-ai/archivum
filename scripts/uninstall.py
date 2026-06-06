#!/usr/bin/env python3
"""Cross-platform Archivum uninstaller.

The default path is intentionally conservative: stop and remove the compose
stack while preserving data volumes, pulled images, and local configuration.
Destructive cleanup requires explicit flags and confirmation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(value: str, code: str) -> str:
    if not supports_color():
        return value
    return f"{code}{value}{RESET}"


def info(message: str) -> None:
    print(color("• ", CYAN) + message)


def ok(message: str) -> None:
    print(color("✓ ", GREEN) + message)


def warn(message: str) -> None:
    print(color("! ", YELLOW) + message)


def error(message: str) -> None:
    print(color("✗ ", RED) + message)


def run(cmd: list[str], *, cwd: Path = ROOT, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    if dry_run:
        print("+ " + " ".join(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def ask_bool(label: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{label} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1", "on"}


def find_compose_command() -> list[str] | None:
    docker = shutil.which("docker")
    if docker:
        result = subprocess.run([docker, "compose", "version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode == 0:
            return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    if legacy:
        result = subprocess.run([legacy, "version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode == 0:
            return [legacy]
    return None


def compose_files() -> list[str]:
    files = ["docker-compose.yml"]
    if (ROOT / "docker-compose.images.yml").exists():
        files.append("docker-compose.images.yml")
    return files


def compose_command(compose: list[str]) -> list[str]:
    cmd = compose[:]
    for path in compose_files():
        cmd.extend(["-f", path])
    return cmd


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archivum-uninstall",
        description="Stop and optionally remove an Archivum Docker Compose install.",
    )
    parser.add_argument("--volumes", action="store_true", help="Remove Docker volumes, including wiki data, uploads, SQLite, Kuzu, and Qdrant.")
    parser.add_argument("--images", action="store_true", help="Remove locally built Compose images.")
    parser.add_argument("--files", action="store_true", help="Remove this Archivum install directory after stopping containers.")
    parser.add_argument("--yes", "-y", action="store_true", help="Do not prompt for confirmation.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changing anything.")
    return parser.parse_args(argv)


def safe_to_remove_install_dir(path: Path) -> tuple[bool, str]:
    resolved = path.resolve()
    home = Path.home().resolve()
    anchors = {resolved.anchor, str(home)}
    if str(resolved) in anchors:
        return False, f"refusing to remove unsafe install directory: {resolved}"
    if len(resolved.parts) < 3:
        return False, f"refusing to remove shallow install directory: {resolved}"
    required = ["docker-compose.yml", ".env.example", "scripts"]
    missing = [name for name in required if not (resolved / name).exists()]
    if missing:
        return False, f"refusing to remove {resolved}; missing expected Archivum files: {', '.join(missing)}"
    return True, ""


def print_plan(args: argparse.Namespace) -> None:
    print(color("Archivum Uninstaller", BOLD))
    print()
    print(f"Install directory: {ROOT}")
    print()
    print("This will:")
    print("  - stop and remove Archivum containers")
    print("  - remove the Archivum Docker network")
    if args.volumes:
        print(color("  - remove Docker volumes with wiki data, raw uploads, SQLite, Kuzu, and Qdrant", YELLOW))
    else:
        print("  - preserve Docker volumes and all application data")
    if args.images:
        print("  - remove locally built Compose images")
    else:
        print("  - preserve Docker images")
    if args.files:
        print(color("  - remove the local Archivum install directory", YELLOW))
    else:
        print("  - preserve local files such as .env and compose files")
    print()


def stop_stack(compose: list[str], args: argparse.Namespace) -> int:
    cmd = compose_command(compose) + ["down", "--remove-orphans"]
    if args.volumes:
        cmd.append("--volumes")
    if args.images:
        cmd.extend(["--rmi", "local"])

    info("Running: " + " ".join(cmd))
    result = run(cmd, dry_run=args.dry_run)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        error("Docker Compose cleanup failed.")
    return result.returncode


def remove_install_dir(args: argparse.Namespace) -> int:
    allowed, reason = safe_to_remove_install_dir(ROOT)
    if not allowed:
        error(reason)
        return 1
    parent = ROOT.parent
    target_name = ROOT.name
    info(f"Removing install directory: {ROOT}")
    if args.dry_run:
        print(f"+ rm -rf {ROOT}")
        return 0
    os.chdir(parent)
    shutil.rmtree(parent / target_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    os.chdir(ROOT)

    compose = find_compose_command()
    if compose is None:
        error("Docker Compose was not found. Install Docker, or remove files manually.")
        return 1

    print_plan(args)

    if not args.yes:
        if args.volumes:
            warn("The --volumes option deletes local Archivum data.")
        if args.files:
            warn("The --files option deletes this install directory.")
        if not ask_bool("Continue?", default=not (args.volumes or args.files)):
            warn("Cancelled.")
            return 1

    status = stop_stack(compose, args)
    if status != 0:
        return status

    if args.files:
        status = remove_install_dir(args)
        if status != 0:
            return status

    ok("Archivum uninstall step completed.")
    if not args.volumes:
        info("Data volumes were preserved. Reinstalling later can reuse them.")
    if not args.files:
        info("Local files were preserved. Remove the directory manually if you no longer need it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
