from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from archivum.archgraph.cache import content_hash, load_cached, save_cached
from archivum.archgraph.extract import extract_file
from archivum.archgraph.mapper import (
    CandidateArtifact,
    CandidateEntity,
    CandidateRelationship,
    Provenance,
    map_extraction,
)
from archivum.archgraph.models import Extraction
from archivum.archgraph.repo import collect_files, repo_artifacts, snapshot_repo
from archivum.archgraph.resolve import resolve_cross_file
from archivum.archgraph.cross_repo import resolve_cross_repo
from archivum.archgraph.bridge import bridge_evidence
from archivum.archgraph.lexical import build_lexical_index


@dataclass
class IngestReport:
    files: int
    nodes: int
    edges: int
    rejected: int
    cache_hits: int


class _L1View:
    """Minimal L1 read API built from accepted entity/artifact candidates."""

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
                        "text": "",
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


async def ingest_repo(
    root: Path,
    *,
    scope: str,
    cache_dir: Path,
    validation,
    lexical_conn: aiosqlite.Connection,
) -> IngestReport:
    # Step 1: snapshot repo and collect repo-level artifacts
    snap = snapshot_repo(root)
    repo_cands = repo_artifacts(snap, scope=scope)

    # Step 2: collect files and extract (or load from cache)
    files = collect_files(root)
    all_extractions: list[Extraction] = []
    file_chunk_ids: list[tuple[Path, str]] = []
    cache_hits = 0

    for file in files:
        chunk_id = content_hash(file)
        ext = load_cached(file, cache_dir)
        if ext is None:
            ext = extract_file(file)
            save_cached(file, ext, cache_dir)
        else:
            cache_hits += 1
        all_extractions.append(ext)
        file_chunk_ids.append((file, chunk_id))

    # Step 3: resolve cross-file edges and wrap them in a synthetic Extraction
    inferred_edges = resolve_cross_file(all_extractions)
    if inferred_edges:
        cross_file_ext = Extraction(nodes=[], edges=inferred_edges, error=None)
        # Use a stable chunk_id for cross-file provenance
        cross_chunk_id = f"cross_file:{snap.repo_id}:{snap.commit_sha}"
        all_extractions.append(cross_file_ext)
        file_chunk_ids.append((root, cross_chunk_id))

    # Step 4: map all extractions into candidates
    all_candidates: list[object] = list(repo_cands)
    for (file_or_root, chunk_id), ext in zip(file_chunk_ids, all_extractions):
        mapped = map_extraction(ext, scope=scope, chunk_id=chunk_id)
        all_candidates.extend(mapped)

    # Step 5: validate first batch
    accepted_before = len(validation.accepted)
    rejected_before = len(validation.rejected)
    validation.validate_batch(all_candidates)

    # Step 6: build L1 view from currently accepted candidates and run cross-repo + bridge
    l1_view = _L1View(validation.accepted)
    cross_repo_rels = await resolve_cross_repo(l1_view)
    bridge_rels = await bridge_evidence(l1_view)
    extra_rels: list[object] = [*cross_repo_rels, *bridge_rels]
    if extra_rels:
        validation.validate_batch(extra_rels)

    # Step 7: build lexical index from accepted entity/artifact candidates
    code_nodes = [
        (c.id, c.name)
        for c in validation.accepted
        if isinstance(c, (CandidateEntity, CandidateArtifact))
    ]
    await build_lexical_index(lexical_conn, code_nodes)

    # Step 8: compute report counts as deltas from this run
    accepted_after = len(validation.accepted)
    rejected_after = len(validation.rejected)

    accepted_delta = accepted_after - accepted_before
    rejected_delta = rejected_after - rejected_before

    nodes_accepted = sum(
        1
        for c in validation.accepted[accepted_before:]
        if isinstance(c, (CandidateEntity, CandidateArtifact))
    )
    edges_accepted = sum(
        1
        for c in validation.accepted[accepted_before:]
        if isinstance(c, CandidateRelationship)
    )

    return IngestReport(
        files=len(files),
        nodes=nodes_accepted,
        edges=edges_accepted,
        rejected=rejected_delta,
        cache_hits=cache_hits,
    )
