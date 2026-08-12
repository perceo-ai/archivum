"""Resolve which memory assets an agent is equipped with.

A loadout is the lever that stops "we have memory" from becoming "dump
everything into context": only bound assets are handed over, `always` bindings
unconditionally and `on_demand` bindings when the session query matches.
"""

from __future__ import annotations

import re

from archivum.knowledge.models import Citation
from archivum.memory.models import LoadoutEntry, LoadoutPackage, MemoryAsset
from archivum.memory.registry import MemoryAssetRegistry

DEFAULT_LOADOUT_LIMIT = 12
_MIN_TOKEN_CHARS = 3
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def query_tokens(query: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(query.casefold())
        if len(token) >= _MIN_TOKEN_CHARS
    }


def asset_tokens(asset: MemoryAsset) -> set[str]:
    haystack = " ".join(
        [asset.name, asset.summary, asset.body[:2000], " ".join(asset.tags)]
    )
    return set(_TOKEN_RE.findall(haystack.casefold()))


def match_score(asset: MemoryAsset, tokens: set[str]) -> float:
    if not tokens:
        return 0.0
    overlap = tokens & asset_tokens(asset)
    return round(len(overlap) / len(tokens), 4)


async def resolve_loadout(
    registry: MemoryAssetRegistry,
    *,
    agent_key: str,
    wiki_id: str,
    query: str = "",
    limit: int = DEFAULT_LOADOUT_LIMIT,
    min_match: float = 0.2,
) -> LoadoutPackage:
    """Return the assets this agent should start with, cited.

    Archived and draft assets are never handed to an agent: only assets the
    owner has explicitly activated are inheritable experience.
    """
    agent = await registry.get_agent(agent_key, wiki_id)
    if agent is None:
        return LoadoutPackage(
            agent_key=agent_key,
            query=query,
            entries=[],
            citations=[],
            insufficient_evidence=True,
            reason=f"No agent profile named '{agent_key}'.",
        )

    bindings = await registry.list_bindings(agent_key=agent_key, wiki_id=wiki_id)
    tokens = query_tokens(query)
    entries: list[LoadoutEntry] = []
    skipped_on_demand = 0

    for binding in bindings:
        asset = await registry.get_asset(binding.asset_id)
        if asset is None or asset.status != "active" or asset.wiki_id != wiki_id:
            continue
        if binding.mode == "always":
            reason = "Always-on binding."
        else:
            score = match_score(asset, tokens)
            if score < min_match:
                skipped_on_demand += 1
                continue
            reason = f"Query match {score:.2f} against on-demand binding."
        entries.append(
            LoadoutEntry(
                asset=asset,
                mode=binding.mode,
                priority=binding.priority,
                reason=reason,
            )
        )

    entries.sort(key=lambda entry: (entry.priority, entry.asset.id))
    entries = entries[: max(limit, 0)]
    citations = _dedupe(
        [citation for entry in entries for citation in entry.asset.citations]
    )

    if not entries:
        reason = (
            f"Agent '{agent_key}' has no active bindings."
            if not bindings
            else f"No bound asset matched this session ({skipped_on_demand} on-demand skipped)."
        )
        return LoadoutPackage(
            agent_key=agent_key,
            query=query,
            entries=[],
            citations=[],
            insufficient_evidence=True,
            reason=reason,
        )

    return LoadoutPackage(
        agent_key=agent_key,
        query=query,
        entries=entries,
        citations=citations,
        insufficient_evidence=not citations,
        reason=(
            "Loadout assets carry no citations; treat their content as unverified."
            if not citations
            else None
        ),
    )


def _dedupe(citations: list[Citation]) -> list[Citation]:
    unique: list[Citation] = []
    seen: set[tuple[str, str, int | None, int | None, str | None]] = set()
    for citation in citations:
        key = (
            citation.source_id,
            citation.chunk_id,
            citation.span_start,
            citation.span_end,
            citation.quote,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique
