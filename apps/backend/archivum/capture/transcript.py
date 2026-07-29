"""Render a Conversation into a stable human-readable transcript plus the
character span of each turn, used as the L1 Document text and chunk anchors."""

from __future__ import annotations

import json

from archivum.capture.schema import Conversation, ToolCall, Turn

TurnSpan = tuple[int, int, str]

_SEP = "\n\n"


def _render_tool_call(tc: ToolCall) -> str:
    args = json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False)
    status = "" if tc.ok else " [error]"
    result = "" if tc.result is None else f" -> {tc.result}"
    return f"  ↳ {tc.name}({args}){status}{result}"


def _render_turn(turn: Turn) -> str:
    lines = [f"[{turn.role}] {turn.text}".rstrip()]
    lines.extend(_render_tool_call(tc) for tc in turn.tool_calls)
    return "\n".join(lines)


def render_transcript(conv: Conversation) -> tuple[str, list[TurnSpan]]:
    blocks = [_render_turn(t) for t in conv.turns]
    text = _SEP.join(blocks)
    spans: list[TurnSpan] = []
    cursor = 0
    for block in blocks:
        start = cursor
        end = start + len(block)
        spans.append((start, end, block))
        cursor = end + len(_SEP)
    return text, spans
