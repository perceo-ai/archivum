"""Typed models for memory assets, agent profiles, and loadouts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from archivum.knowledge.models import Citation

# Asset types mirror the memory kinds an owner actually accumulates: editable
# wiki pages, distilled conversation memory, reusable procedures, code graphs,
# ingested source bundles, project/scenario memory, and the owner profile.
# These are storage-layer containers; the strategy's semantic memory types
# (profile, preference, decision, principle, fact, procedure, skill,
# relationship, source_summary, code_insight) live on the atoms and
# candidates inside them — see `archivum.memory.atoms.SEMANTIC_ATOM_TYPES`.
AssetType = Literal[
    "wiki",
    "chat",
    "skill",
    "codegraph",
    "source",
    "scenario",
    "persona",
]

AssetStatus = Literal["draft", "active", "archived"]
AssetVisibility = Literal["private", "shared", "public"]

# L0 raw evidence, L1 atoms, L2 scenario memory, L3 owner persona.
MemoryLayer = Literal["L0", "L1", "L2", "L3"]

BindingMode = Literal["always", "on_demand"]

ASSET_TYPES: frozenset[str] = frozenset(
    {"wiki", "chat", "skill", "codegraph", "source", "scenario", "persona"}
)
ASSET_STATUSES: frozenset[str] = frozenset({"draft", "active", "archived"})
ASSET_VISIBILITIES: frozenset[str] = frozenset({"private", "shared", "public"})
MEMORY_LAYERS: frozenset[str] = frozenset({"L0", "L1", "L2", "L3"})
BINDING_MODES: frozenset[str] = frozenset({"always", "on_demand"})


class MemoryAsset(BaseModel):
    """A governed unit of memory that can be reviewed, versioned, and equipped."""

    id: str
    wiki_id: str
    asset_type: AssetType
    layer: MemoryLayer
    name: str
    owner: str
    scope: str
    status: AssetStatus
    visibility: AssetVisibility
    version: int
    page_slug: str | None = None
    summary: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    approved_by: str | None = None
    reviewed_at: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: list[str] = Field(default_factory=list)
    conflict_lineage: list[str] = Field(default_factory=list)
    retired_at: str | None = None
    created_at: str = ""
    updated_at: str = ""


class MemoryAssetVersion(BaseModel):
    """An immutable snapshot of an asset at one version."""

    asset_id: str
    version: int
    name: str
    summary: str
    body: str
    status: AssetStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    change_note: str = ""
    created_at: str = ""


class MemoryScope(BaseModel):
    """A budgeted memory scope such as person:self, a topic, project, or repo."""

    id: str
    wiki_id: str
    scope_type: Literal["human", "topic", "project", "repo", "person", "org"]
    name: str
    parent_scope_id: str | None = None
    budget_tokens: int = 4_000
    budget_items: int = 20
    retention_policy: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class AgentProfile(BaseModel):
    """A named agent that memory assets can be bound to."""

    agent_key: str
    wiki_id: str
    name: str
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


class AssetBinding(BaseModel):
    """Which asset an agent is equipped with, and how eagerly."""

    agent_key: str
    asset_id: str
    mode: BindingMode = "always"
    priority: int = 100


class LoadoutEntry(BaseModel):
    asset: MemoryAsset
    mode: BindingMode
    priority: int
    reason: str


class LoadoutPackage(BaseModel):
    """What an agent is handed at the start of a session."""

    agent_key: str
    query: str = ""
    entries: list[LoadoutEntry] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = True
    reason: str | None = None
