from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from archivum.archgraph.registry import CODE_SUFFIXES
from archivum.archgraph.extractors.base import _make_id
from archivum.archgraph.mapper import CandidateArtifact, CandidateRelationship, Provenance

_PRUNE = {".git", "node_modules", ".venv", "__pycache__"}


@dataclass(frozen=True)
class RepoSnapshot:
    repo_id: str
    commit_sha: str
    root: Path
    remote_url: str | None


def snapshot_repo(root: Path) -> RepoSnapshot:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            commit_sha = result.stdout.strip()
        else:
            commit_sha = "working-tree"
    except (FileNotFoundError, subprocess.CalledProcessError):
        commit_sha = "working-tree"

    remote_url: str | None = None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            remote_url = result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    repo_id = _make_id(Path(remote_url).stem if remote_url else root.resolve().name)
    return RepoSnapshot(repo_id=repo_id, commit_sha=commit_sha, root=root, remote_url=remote_url)


def collect_files(root: Path) -> list[Path]:
    results = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _PRUNE for part in p.parts):
            continue
        if p.suffix in CODE_SUFFIXES:
            results.append(p)
    return sorted(results)


def repo_artifacts(snap: RepoSnapshot, *, scope: str) -> list[object]:
    prov = Provenance(
        chunk_id=f"repo:{snap.repo_id}",
        span="L0",
        extraction_method="EXTRACTED",
    )
    repo_art = CandidateArtifact(
        id=snap.repo_id,
        kind="repo",
        name=snap.repo_id,
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[prov],
    )
    commit_id = _make_id(snap.repo_id, snap.commit_sha)
    commit_art = CandidateArtifact(
        id=commit_id,
        kind="commit",
        name=snap.commit_sha,
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[prov],
    )
    rel = CandidateRelationship(
        id=_make_id(commit_id, snap.repo_id, "in_commit"),
        src_id=commit_id,
        dst_id=snap.repo_id,
        rel_type="in_commit",
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[prov],
    )
    return [repo_art, commit_art, rel]
