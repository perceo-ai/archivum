"""Importer for Claude Code session transcripts (one JSON object per line)."""

from __future__ import annotations

import json
from pathlib import Path

from archivum.capture.importers import register
from archivum.capture.importers.base import ImportResult
from archivum.capture.redaction import visible_text_from_blocks
from archivum.capture.schema import Conversation, ToolCall, Turn

_INTERFACE = "claude_code_import"


class ClaudeCodeImporter:
    interface = _INTERFACE

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".jsonl"

    def parse(self, path: Path) -> ImportResult:
        session_id = path.stem
        started_at = ""
        turns: list[Turn] = []
        pending: dict[str, ToolCall] = {}  # call_id -> ToolCall awaiting result
        turn_of_call: dict[str, int] = {}  # call_id -> index in `turns`

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "summary":
                continue
            session_id = obj.get("sessionId", session_id)
            started_at = started_at or obj.get("timestamp", "")
            message = obj.get("message") or {}
            role = message.get("role", obj.get("type", "user"))
            content = message.get("content", "")

            # Fill any tool_results into the ToolCall they answer.
            results = self._tool_results(content)
            if results:
                for call_id, result_text in results.items():
                    call = pending.pop(call_id, None)
                    if call is None:
                        continue
                    idx = turn_of_call.get(call_id)
                    if idx is None:
                        continue
                    filled = ToolCall(
                        name=call.name, arguments=call.arguments, result=result_text,
                        call_id=call.call_id, started_at=call.started_at, ok=call.ok,
                    )
                    turn = turns[idx]
                    turns[idx] = Turn(
                        role=turn.role, text=turn.text, ts=turn.ts,
                        tool_calls=tuple(
                            filled if tc.call_id == call_id else tc for tc in turn.tool_calls
                        ),
                    )
                # Also emit a turn for any visible text blocks bundled with tool_results.
                visible_text = self._text_only_blocks(content)
                if not visible_text:
                    continue

            calls = self._tool_uses(content)
            text = self._text_only_blocks(content) if results else visible_text_from_blocks(content)
            if not text and not calls:
                continue
            turn = Turn(role=role, text=text, ts=obj.get("timestamp", ""),
                        tool_calls=tuple(calls))
            turns.append(turn)
            for call in calls:
                if call.call_id:
                    pending[call.call_id] = call
                    turn_of_call[call.call_id] = len(turns) - 1

        conv = Conversation(
            session_id=session_id, interface=_INTERFACE,
            started_at=started_at, turns=tuple(turns), origin_uri=str(path),
        )
        return ImportResult(conversations=(conv,), interface=_INTERFACE)

    @staticmethod
    def _tool_uses(content: object) -> list[ToolCall]:
        if not isinstance(content, list):
            return []
        out: list[ToolCall] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append(ToolCall(
                    name=str(block.get("name", "")),
                    arguments=dict(block.get("input", {})),
                    result=None, call_id=block.get("id"),
                ))
        return out

    @staticmethod
    def _text_only_blocks(content: object) -> str:
        """Return visible text from only `text`-type blocks (excludes tool_result/thinking)."""
        from archivum.capture.redaction import visible_text_from_blocks
        if not isinstance(content, list):
            return visible_text_from_blocks(content)
        text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return visible_text_from_blocks(text_blocks)

    @staticmethod
    def _tool_results(content: object) -> dict[str, str]:
        if not isinstance(content, list):
            return {}
        out: dict[str, str] = {}
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                cid = block.get("tool_use_id")
                if cid:
                    out[cid] = str(block.get("content", ""))
        return out


register(ClaudeCodeImporter())
