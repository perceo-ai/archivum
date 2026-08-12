"""Deterministic canonical JSON for a Conversation + its content hash (L0 key)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from archivum.capture.schema import Conversation, Decision, Outcome, ToolCall, Turn
from archivum.store.hashing import sha256_bytes


def to_canonical_dict(conv: Conversation) -> dict[str, Any]:
    d = dataclasses.asdict(conv)
    d.pop("metadata", None)  # transport-only, excluded from identity
    return d


def to_canonical_bytes(conv: Conversation) -> bytes:
    return json.dumps(
        to_canonical_dict(conv),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_hash(conv: Conversation) -> str:
    return sha256_bytes(to_canonical_bytes(conv))


def from_canonical_dict(data: dict[str, Any]) -> Conversation:
    """Rebuild a Conversation from its canonical form (L0 blob bytes).

    `metadata` is transport-only and excluded from the canonical form, so a
    round-tripped Conversation always has an empty metadata dict.
    """
    return Conversation(
        session_id=data["session_id"],
        interface=data["interface"],
        started_at=data.get("started_at", ""),
        turns=tuple(
            Turn(
                role=turn.get("role", "user"),
                text=turn.get("text", ""),
                ts=turn.get("ts", ""),
                tool_calls=tuple(
                    ToolCall(
                        name=call.get("name", ""),
                        arguments=call.get("arguments", {}) or {},
                        result=call.get("result"),
                        call_id=call.get("call_id"),
                        started_at=call.get("started_at"),
                        ok=bool(call.get("ok", True)),
                    )
                    for call in turn.get("tool_calls", []) or []
                ),
            )
            for turn in data.get("turns", []) or []
        ),
        decisions=tuple(
            Decision(
                statement=item.get("statement", ""),
                rationale=item.get("rationale", ""),
                turn_index=int(item.get("turn_index", -1)),
            )
            for item in data.get("decisions", []) or []
        ),
        outcomes=tuple(
            Outcome(
                task=item.get("task", ""),
                status=item.get("status", "unknown"),
                detail=item.get("detail", ""),
                turn_index=int(item.get("turn_index", -1)),
            )
            for item in data.get("outcomes", []) or []
        ),
        scope=data.get("scope", "personal"),
        origin_uri=data.get("origin_uri", ""),
    )


def from_canonical_bytes(raw: bytes) -> Conversation:
    return from_canonical_dict(json.loads(raw.decode("utf-8")))
