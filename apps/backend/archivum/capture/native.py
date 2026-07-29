"""Live capture writer for Perceo-controlled agent workers. Buffers redacted
turns/tool-calls/decisions/outcomes, then flushes one Conversation to the store."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, datetime

from archivum.capture.redaction import redact_turn_text
from archivum.capture.schema import (
    Conversation,
    Decision,
    Outcome,
    Role,
    ToolCall,
    Turn,
)
from archivum.capture.store import CaptureResult, CaptureStore


def _now() -> str:
    return datetime.now(UTC).isoformat()


class NativeCaptureWriter:
    def __init__(
        self,
        store: CaptureStore,
        *,
        session_id: str,
        interface: str = "claude_code_native",
        scope: str = "personal",
        origin_uri: str = "",
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._interface = interface
        self._scope = scope
        self._origin_uri = origin_uri
        self._started_at = _now()
        self._turns: list[Turn] = []
        self._decisions: list[Decision] = []
        self._outcomes: list[Outcome] = []

    def record_turn(
        self, role: Role, text: str, tool_calls: Sequence[ToolCall] = ()
    ) -> None:
        self._turns.append(
            Turn(role=role, text=redact_turn_text(text), ts=_now(),
                 tool_calls=tuple(tool_calls))
        )

    def record_tool_call(
        self, name: str, arguments: dict, result: str | None = None, ok: bool = True
    ) -> None:
        tc = ToolCall(
            name=name, arguments=arguments,
            result=None if result is None else redact_turn_text(result),
            started_at=_now(), ok=ok,
        )
        if not self._turns:
            self._turns.append(Turn(role="assistant", text="", ts=_now()))
        last = self._turns[-1]
        self._turns[-1] = dataclasses.replace(last, tool_calls=last.tool_calls + (tc,))

    def record_decision(self, statement: str, rationale: str = "") -> None:
        self._decisions.append(
            Decision(statement=statement, rationale=rationale, turn_index=len(self._turns) - 1)
        )

    def record_outcome(self, task: str, status: str = "unknown", detail: str = "") -> None:
        self._outcomes.append(
            Outcome(task=task, status=status, detail=detail, turn_index=len(self._turns) - 1)  # type: ignore[arg-type]
        )

    def build(self) -> Conversation:
        return Conversation(
            session_id=self._session_id, interface=self._interface,
            started_at=self._started_at, turns=tuple(self._turns),
            decisions=tuple(self._decisions), outcomes=tuple(self._outcomes),
            scope=self._scope, origin_uri=self._origin_uri,
        )

    async def flush(self) -> CaptureResult:
        return await self._store.capture(self.build())
