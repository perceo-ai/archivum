"""Importer for ChatGPT data-export `conversations.json` (list of mappings)."""

from __future__ import annotations

import json
from pathlib import Path

from archivum.capture.importers import register
from archivum.capture.importers.base import ImportResult
from archivum.capture.redaction import HIDDEN_BLOCK_TYPES, redact_turn_text
from archivum.capture.schema import Conversation, Turn

_INTERFACE = "chatgpt_import"
_ROLES = {"user", "assistant", "system", "tool"}


class ChatGptImporter:
    interface = _INTERFACE

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".json":
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return isinstance(data, list) and all(
            isinstance(e, dict) and "mapping" in e for e in data
        )

    def parse(self, path: Path) -> ImportResult:
        data = json.loads(path.read_text(encoding="utf-8"))
        conversations: list[Conversation] = []
        for entry in data:
            title = str(entry.get("title", ""))
            create_time = entry.get("create_time", 0)
            nodes = [
                n["message"]
                for n in entry.get("mapping", {}).values()
                if isinstance(n, dict) and isinstance(n.get("message"), dict)
            ]
            turns: list[Turn] = []
            for msg in sorted(nodes, key=lambda m: m.get("create_time") or 0):
                content = msg.get("content") or {}
                if content.get("content_type") in HIDDEN_BLOCK_TYPES:
                    continue
                role = (msg.get("author") or {}).get("role", "user")
                if role not in _ROLES:
                    role = "user"
                text = redact_turn_text(
                    "\n".join(str(p) for p in content.get("parts", []) if p)
                )
                if not text:
                    continue
                ct = msg.get("create_time")
                turns.append(Turn(role=role, text=text, ts="" if ct is None else str(ct)))
            conversations.append(Conversation(
                session_id=f"{title}:{create_time}", interface=_INTERFACE,
                started_at=str(create_time), turns=tuple(turns), origin_uri=str(path),
            ))
        return ImportResult(conversations=tuple(conversations), interface=_INTERFACE)


register(ChatGptImporter())
