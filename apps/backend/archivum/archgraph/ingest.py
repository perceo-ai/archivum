from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from archivum.archgraph.cache import load_cached, save_cached
from archivum.archgraph.extract import extract_file
from archivum.archgraph.extractors.base import _file_namespace
from archivum.archgraph.mapper import (
    CandidateArtifact,
    CandidateEntity,
    CandidateRelationship,
    Provenance,
    candidate_to_knowledge_object,
    candidate_to_knowledge_relationship,
    map_extraction,
)
from archivum.archgraph.models import Extraction
from archivum.archgraph.registry import CODE_SUFFIXES
from archivum.archgraph.repo import collect_files, repo_artifacts, snapshot_repo
from archivum.archgraph.resolve import resolve_cross_file
from archivum.archgraph.cross_repo import resolve_cross_repo
from archivum.archgraph.bridge import bridge_evidence
from archivum.archgraph.lexical import build_lexical_index
from archivum.knowledge.repository import KnowledgeRepository


@dataclass
class IngestReport:
    files: int
    nodes: int
    edges: int
    rejected: int
    cache_hits: int


class _L1View:
    """Minimal L1 read API built from accepted entity/artifact candidates.

    Note on evidence bridging: code candidates carry no free-text body, so the
    ``text`` field is passed through from the candidate when present and is
    otherwise empty. ``bridge_evidence`` matches on that text, so in a code-only
    ingest it correctly emits nothing — bridging is *evidence-gated*: it fires
    only once L1 also holds PR/conversation/deploy objects (with text) from
    PER-316 capture / PER-317. That is by design, not a silent no-op.
    """

    def __init__(self, candidates: list[object]) -> None:
        self._objects: list[dict] = []
        for c in candidates:
            if isinstance(c, (CandidateEntity, CandidateArtifact)):
                self._objects.append(
                    {
                        "id": c.id,
                        "kind": c.kind,
                        "scope": c.scope,
                        "label": c.name,
                        "text": getattr(c, "text", ""),
                    }
                )
            elif isinstance(c, CandidateRelationship):
                self._objects.append(
                    {
                        "id": c.id,
                        "kind": c.rel_type,
                        "scope": c.scope,
                        "label": c.rel_type,
                        "text": "",
                    }
                )

    async def list_objects(self, kind: str | None = None, scope: str | None = None) -> list[dict]:
        return [
            o
            for o in self._objects
            if (kind is None or o.get("kind") == kind)
            and (scope is None or o.get("scope") == scope)
        ]


def changed_files(root: Path, since_sha: str | None) -> tuple[list[Path], list[Path]]:
    """Return (changed_or_added, deleted) absolute Paths, code files only.

    Falls back to (collect_files(root), []) when since_sha is None,
    root is not a git repo, or any subprocess error occurs.
    """
    if since_sha is None:
        return collect_files(root), []

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-status", f"{since_sha}..HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return collect_files(root), []
    except (FileNotFoundError, subprocess.SubprocessError):
        return collect_files(root), []

    changed: list[Path] = []
    deleted: list[Path] = []

    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].strip()
        rel_path = parts[1].strip()
        # Rename lines look like "R100\told_name\tnew_name" — index the new
        # name and clean stale records for the old namespace.
        if status.startswith("R"):
            old_path = root / rel_path
            if old_path.suffix in CODE_SUFFIXES:
                deleted.append(old_path)
            rel_path = parts[2].strip() if len(parts) >= 3 else rel_path
            status = "R"

        abs_path = root / rel_path
        if abs_path.suffix not in CODE_SUFFIXES:
            continue

        if status == "D":
            deleted.append(abs_path)
        else:
            changed.append(abs_path)

    return changed, deleted


def prune_dangling(candidates: list, deleted_files: set[str]) -> tuple[list, int]:
    """Drop candidates whose provenance ALL cite a deleted file.

    A candidate is pruned only when it has at least one provenance entry
    AND every provenance chunk_id is in deleted_files.
    Candidates with no provenance are kept.
    Returns (kept, pruned_count).
    """
    kept: list = []
    pruned_count = 0

    for candidate in candidates:
        provenance: list[Provenance] = getattr(candidate, "provenance", [])
        if not provenance:
            kept.append(candidate)
            continue

        all_deleted = all(p.chunk_id in deleted_files for p in provenance)
        if all_deleted:
            pruned_count += 1
        else:
            kept.append(candidate)

    return kept, pruned_count


async def ingest_repo(
    root: Path,
    *,
    scope: str,
    cache_dir: Path,
    knowledge: KnowledgeRepository,
    lexical_conn: aiosqlite.Connection,
    update: bool = False,
    since_sha: str | None = None,
) -> IngestReport:
    # Step 1: snapshot repo and collect repo-level artifacts
    snap = snapshot_repo(root)
    repo_cands = repo_artifacts(snap, scope=scope)

    # Step 2: collect files (full or incremental) and extract (or load from cache)
    if update:
        files, deleted = changed_files(root, since_sha)
    else:
        files = collect_files(root)
        deleted = []

    all_extractions: list[Extraction] = []
    file_chunk_ids: list[tuple[Path, str]] = []
    cache_hits = 0

    for file in files:
        # Use str(file) as chunk_id so prune_dangling can match by file path
        chunk_id = str(file)
        cache_namespace = _file_namespace(file, root=root, scope=scope)
        ext = load_cached(file, cache_dir, namespace=cache_namespace)
        if ext is None:
            ext = extract_file(file, root=root, scope=scope)
            save_cached(file, ext, cache_dir, namespace=cache_namespace)
        else:
            cache_hits += 1
        all_extractions.append(ext)
        file_chunk_ids.append((file, chunk_id))

    # Step 3: resolve cross-file edges. Anchor each edge's provenance to ITS OWN
    # source file (the calling site), not a synthetic repo-level key — otherwise
    # a cross-file edge whose source file is later deleted would be un-prunable on
    # --update and dangle forever. Grouping by source_file keeps chunk_id file-
    # addressable so prune_dangling reaches it. Sorted for deterministic emission.
    inferred_edges = resolve_cross_file(all_extractions)
    edges_by_file: dict[str, list] = {}
    for edge in inferred_edges:
        edges_by_file.setdefault(edge.source_file, []).append(edge)
    for src_file in sorted(edges_by_file):
        all_extractions.append(Extraction(nodes=[], edges=edges_by_file[src_file], error=None))
        file_chunk_ids.append((Path(src_file), src_file))

    # Step 4: map all extractions into candidates
    all_candidates: list[object] = list(repo_cands)
    for (file_or_root, chunk_id), ext in zip(file_chunk_ids, all_extractions):
        mapped = map_extraction(ext, scope=scope, chunk_id=chunk_id)
        all_candidates.extend(mapped)

    # Step 5 (incremental only): prune candidates from deleted files and remove
    # stale canonical records from every touched file before current upserts.
    if update and deleted:
        deleted_strs = {str(p) for p in deleted}
        all_candidates, _ = prune_dangling(all_candidates, deleted_strs)

    if update:
        touched_strs = {str(p) for p in files}
        touched_strs.update(str(p) for p in deleted)
        await knowledge.delete_records_with_only_citations_in(
            scope=scope, chunk_ids=touched_strs
        )

    # Step 6: persist canonical knowledge records and their provenance.
    for candidate in all_candidates:
        if isinstance(candidate, (CandidateEntity, CandidateArtifact)):
            await knowledge.upsert_object(candidate_to_knowledge_object(candidate))
        elif isinstance(candidate, CandidateRelationship):
            await knowledge.upsert_relationship(candidate_to_knowledge_relationship(candidate))
    accepted = all_candidates

    # Step 7: build a read view from this run and resolve derived relationships.
    l1_view = _L1View(accepted)
    cross_repo_rels = await resolve_cross_repo(l1_view)
    bridge_rels = await bridge_evidence(l1_view)
    extra_rels: list[object] = [*cross_repo_rels, *bridge_rels]
    if extra_rels:
        for relationship in extra_rels:
            await knowledge.upsert_relationship(candidate_to_knowledge_relationship(relationship))
        accepted.extend(extra_rels)

    # Step 8: rebuild lexical index from canonical code objects in this scope.
    # Incremental runs only extract touched files, but lexical is a full
    # projection and its builder clears existing rows before repopulating.
    canonical_objects = await knowledge.list_objects(scope=scope, limit=100_000)
    code_nodes = [
        (object_.id, object_.label)
        for object_ in canonical_objects
        if object_.properties.get("source_scope") == scope
    ]
    await build_lexical_index(lexical_conn, code_nodes)

    nodes_accepted = sum(
        1
        for c in accepted
        if isinstance(c, (CandidateEntity, CandidateArtifact))
    )
    edges_accepted = sum(
        1
        for c in accepted
        if isinstance(c, CandidateRelationship)
    )

    return IngestReport(
        files=len(files),
        nodes=nodes_accepted,
        edges=edges_accepted,
        rejected=0,
        cache_hits=cache_hits,
    )
