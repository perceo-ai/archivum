"""Connector registry. Built-in connectors self-register on import."""

from __future__ import annotations

from pathlib import Path

from archivum.capture.importers.base import ImportConnector, ImportResult

_REGISTRY: list[ImportConnector] = []


def register(connector: ImportConnector) -> None:
    _REGISTRY.append(connector)


def connector_for(path: Path) -> ImportConnector | None:
    for connector in _REGISTRY:
        if connector.can_handle(path):
            return connector
    return None


def all_connectors() -> tuple[ImportConnector, ...]:
    return tuple(_REGISTRY)


__all__ = [
    "ImportConnector",
    "ImportResult",
    "register",
    "connector_for",
    "all_connectors",
]
