from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


class FakeValidationLayer:
    """Stand-in for PER-317's ValidationLayer.validate_batch."""

    _VALID_METHODS = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}

    def __init__(self) -> None:
        self.accepted: list[object] = []
        self.rejected: list[object] = []

    def validate_batch(self, candidates: list) -> None:
        for candidate in candidates:
            provenance = getattr(candidate, "provenance", [])
            method = getattr(candidate, "extraction_method", "")
            if provenance and method in self._VALID_METHODS:
                self.accepted.append(candidate)
            else:
                self.rejected.append(candidate)


@pytest.fixture
def fake_validation() -> FakeValidationLayer:
    return FakeValidationLayer()


@pytest.fixture
def git_repo(tmp_path):
    # skip if git missing
    if shutil.which("git") is None:
        pytest.skip("git not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    # copy the py_sample fixture files into repo/
    src = Path(__file__).parent / "fixtures" / "py_sample"
    for f in src.glob("*.py"):
        (repo / f.name).write_text(f.read_text())
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env)
    return repo


class FakeL1:
    """In-memory stand-in for PER-317's L1 read API used by archgraph resolvers."""

    def __init__(self, objects=None):
        # each object: dict with keys: id, kind, scope, label, and optional 'text' (for chunk/pr bodies)
        self._objects = list(objects or [])

    async def list_objects(self, kind=None, scope=None):
        return [
            o
            for o in self._objects
            if (kind is None or o.get("kind") == kind)
            and (scope is None or o.get("scope") == scope)
        ]
