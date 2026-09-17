"""The vendored CLI the server hands out must match the one in the repo.

Two copies exist for the reason the agent skill has two: the backend Docker
build context is `./apps/backend`, so `COPY` cannot reach `packages/`. Editing
the package alone would serve a stale CLI to every machine that runs the
install line, and nothing else would notice.

Run `scripts/sync-vendored-cli.sh` to fix a failure here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "packages" / "archivum-cli"
VENDORED = REPO_ROOT / "apps" / "backend" / "archivum" / "agent_cli"

_HINT = "Run scripts/sync-vendored-cli.sh and commit the result."


def _relative_files(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and "node_modules" not in path.parts
    }


def test_the_vendored_cli_has_every_source_file():
    expected = {f for f in _relative_files(SOURCE / "src")}
    actual = {f for f in _relative_files(VENDORED / "src")}

    assert actual == expected, _HINT


@pytest.mark.parametrize("name", sorted(_relative_files(SOURCE / "src")))
def test_each_vendored_source_file_matches(name: str):
    assert (VENDORED / "src" / name).read_text() == (SOURCE / "src" / name).read_text(), _HINT


def test_the_vendored_package_manifest_matches():
    assert (VENDORED / "package.json").read_text() == (SOURCE / "package.json").read_text(), _HINT


def test_the_vendored_cli_carries_no_dependencies():
    """The install script runs it with plain `node`, never `npm install`.

    A dependency here would turn a one-line install into a package fetch on a
    machine that may have no registry access at all.
    """
    import json

    manifest = json.loads((VENDORED / "package.json").read_text())

    assert not manifest.get("dependencies"), (
        "The CLI gained a dependency. The served installer runs it with node "
        "directly, so it must stay dependency-free."
    )
