"""Strip hidden model reasoning before anything is content-addressed (spec §1)."""

from __future__ import annotations

import re
from typing import Any

HIDDEN_BLOCK_TYPES: frozenset[str] = frozenset(
    {"thinking", "reasoning", "redacted_thinking", "thoughts"}
)
_INLINE = re.compile(r"<(thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)


def redact_turn_text(text: str) -> str:
    return _INLINE.sub("", text or "").strip()


def visible_text_from_blocks(content: Any) -> str:
    if isinstance(content, str):
        return redact_turn_text(content)
    parts: list[str] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype in HIDDEN_BLOCK_TYPES:
            continue
        if btype == "text":
            parts.append(str(block.get("text", "")))
        elif btype == "tool_result":
            parts.append(str(block.get("content", "")))
    return redact_turn_text("\n".join(p for p in parts if p))
