"""Canonical conversation value objects — the single shape every capture path
converges on. User-visible content only (redaction happens upstream)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant", "tool", "system"]
ExtractionMethod = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: str | None = None
    call_id: str | None = None
    started_at: str | None = None
    ok: bool = True


@dataclass(frozen=True, slots=True)
class Turn:
    role: Role
    text: str
    ts: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class Decision:
    statement: str
    rationale: str = ""
    turn_index: int = -1


@dataclass(frozen=True, slots=True)
class Outcome:
    task: str
    status: Literal["success", "failure", "partial", "unknown"] = "unknown"
    detail: str = ""
    turn_index: int = -1


@dataclass(frozen=True, slots=True)
class Conversation:
    session_id: str
    interface: str
    started_at: str
    turns: tuple[Turn, ...]
    decisions: tuple[Decision, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    scope: str = "personal"
    origin_uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
