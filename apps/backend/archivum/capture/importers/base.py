"""Import connector contract: a pure parser from a file to Conversations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from archivum.capture.schema import Conversation


@dataclass(frozen=True, slots=True)
class ImportResult:
    conversations: tuple[Conversation, ...]
    interface: str


@runtime_checkable
class ImportConnector(Protocol):
    interface: str

    def can_handle(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> ImportResult: ...
