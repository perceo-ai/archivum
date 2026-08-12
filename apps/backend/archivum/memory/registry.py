"""SQLite persistence for governed memory assets, agents, and bindings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from archivum.knowledge.models import Citation
from archivum.memory.models import (
    ASSET_STATUSES,
    ASSET_TYPES,
    ASSET_VISIBILITIES,
    BINDING_MODES,
    MEMORY_LAYERS,
    AgentProfile,
    AssetBinding,
    MemoryAsset,
    MemoryAssetVersion,
)
from archivum.memory.schema import MEMORY_SCHEMA

_ASSET_LIST_LIMIT = 500


async def init_memory_schema(conn: aiosqlite.Connection) -> None:
    """Create the memory registry tables on an open SQLite connection."""
    conn.row_factory = aiosqlite.Row
    await conn.executescript(MEMORY_SCHEMA)
    await conn.commit()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _citations_json(citations: list[Citation]) -> str:
    return _dumps([citation.model_dump() for citation in citations])


def _validate(asset_type: str, layer: str, status: str, visibility: str) -> None:
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"Unsupported memory asset type: {asset_type}")
    if layer not in MEMORY_LAYERS:
        raise ValueError(f"Unsupported memory layer: {layer}")
    if status not in ASSET_STATUSES:
        raise ValueError(f"Unsupported memory asset status: {status}")
    if visibility not in ASSET_VISIBILITIES:
        raise ValueError(f"Unsupported memory asset visibility: {visibility}")


class MemoryAssetRegistry:
    """Register, version, govern, and equip memory assets."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ── Assets ────────────────────────────────────────────────────────────

    async def register_asset(
        self,
        *,
        id: str,
        wiki_id: str,
        asset_type: str,
        layer: str,
        name: str,
        scope: str,
        owner: str = "person:self",
        status: str = "draft",
        visibility: str = "private",
        page_slug: str | None = None,
        summary: str = "",
        body: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        citations: list[Citation] | None = None,
        change_note: str = "",
    ) -> MemoryAsset:
        """Create or update an asset, bumping the version only when content changes.

        Status and visibility are governance state, not content: changing them
        alone does not create a new version. Use `set_status`/`set_visibility`.
        """
        _validate(asset_type, layer, status, visibility)
        tags = tags or []
        metadata = metadata or {}
        citations = citations or []
        now = _now()

        existing = await self.get_asset(id)
        if existing is None:
            version = 1
            created_at = now
            effective_status = status
            effective_visibility = visibility
        else:
            changed = (
                existing.name != name
                or existing.summary != summary
                or existing.body != body
                or existing.tags != tags
                or existing.metadata != metadata
                or [c.model_dump() for c in existing.citations]
                != [c.model_dump() for c in citations]
            )
            version = existing.version + 1 if changed else existing.version
            created_at = existing.created_at
            # Governance state survives content edits.
            effective_status = existing.status
            effective_visibility = existing.visibility

        await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                """
                INSERT INTO memory_assets
                    (id, wiki_id, asset_type, layer, name, owner, scope, status,
                     visibility, version, page_slug, summary, body, tags, metadata,
                     citations, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    wiki_id=excluded.wiki_id,
                    asset_type=excluded.asset_type,
                    layer=excluded.layer,
                    name=excluded.name,
                    owner=excluded.owner,
                    scope=excluded.scope,
                    version=excluded.version,
                    page_slug=excluded.page_slug,
                    summary=excluded.summary,
                    body=excluded.body,
                    tags=excluded.tags,
                    metadata=excluded.metadata,
                    citations=excluded.citations,
                    updated_at=excluded.updated_at
                """,
                (
                    id,
                    wiki_id,
                    asset_type,
                    layer,
                    name,
                    owner,
                    scope,
                    effective_status,
                    effective_visibility,
                    version,
                    page_slug,
                    summary,
                    body,
                    _dumps(tags),
                    _dumps(metadata),
                    _citations_json(citations),
                    created_at,
                    now,
                ),
            )
            await self._conn.execute(
                """
                INSERT INTO memory_asset_versions
                    (asset_id, version, name, summary, body, status, metadata,
                     citations, change_note, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_id, version) DO UPDATE SET
                    name=excluded.name,
                    summary=excluded.summary,
                    body=excluded.body,
                    status=excluded.status,
                    metadata=excluded.metadata,
                    citations=excluded.citations,
                    change_note=excluded.change_note
                """,
                (
                    id,
                    version,
                    name,
                    summary,
                    body,
                    effective_status,
                    _dumps(metadata),
                    _citations_json(citations),
                    change_note,
                    now,
                ),
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

        loaded = await self.get_asset(id)
        assert loaded is not None
        return loaded

    async def get_asset(self, asset_id: str) -> MemoryAsset | None:
        async with self._conn.execute(
            "SELECT * FROM memory_assets WHERE id=?", (asset_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_asset(row) if row else None

    async def list_assets(
        self,
        *,
        wiki_id: str,
        asset_type: str | None = None,
        layer: str | None = None,
        status: str | None = None,
        scope: str | None = None,
        limit: int = _ASSET_LIST_LIMIT,
    ) -> list[MemoryAsset]:
        clauses = ["wiki_id=?"]
        params: list[Any] = [wiki_id]
        if asset_type is not None:
            clauses.append("asset_type=?")
            params.append(asset_type)
        if layer is not None:
            clauses.append("layer=?")
            params.append(layer)
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        if scope is not None:
            clauses.append("scope=?")
            params.append(scope)
        params.append(max(limit, 0))
        async with self._conn.execute(
            f"SELECT * FROM memory_assets WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC, id ASC LIMIT ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_asset(row) for row in rows]

    async def set_status(self, asset_id: str, status: str) -> MemoryAsset:
        if status not in ASSET_STATUSES:
            raise ValueError(f"Unsupported memory asset status: {status}")
        return await self._set_field(asset_id, "status", status)

    async def set_visibility(self, asset_id: str, visibility: str) -> MemoryAsset:
        if visibility not in ASSET_VISIBILITIES:
            raise ValueError(f"Unsupported memory asset visibility: {visibility}")
        return await self._set_field(asset_id, "visibility", visibility)

    async def _set_field(self, asset_id: str, column: str, value: str) -> MemoryAsset:
        cursor = await self._conn.execute(
            f"UPDATE memory_assets SET {column}=?, updated_at=? WHERE id=?",
            (value, _now(), asset_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Memory asset '{asset_id}' not found")
        if column == "status":
            # Keep the current version snapshot's governance state in sync.
            await self._conn.execute(
                "UPDATE memory_asset_versions SET status=? "
                "WHERE asset_id=? AND version=(SELECT version FROM memory_assets WHERE id=?)",
                (value, asset_id, asset_id),
            )
        await self._conn.commit()
        loaded = await self.get_asset(asset_id)
        assert loaded is not None
        return loaded

    async def delete_asset(self, asset_id: str) -> bool:
        await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                "DELETE FROM memory_asset_bindings WHERE asset_id=?", (asset_id,)
            )
            await self._conn.execute(
                "DELETE FROM memory_asset_versions WHERE asset_id=?", (asset_id,)
            )
            cursor = await self._conn.execute(
                "DELETE FROM memory_assets WHERE id=?", (asset_id,)
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        return cursor.rowcount > 0

    async def list_versions(self, asset_id: str) -> list[MemoryAssetVersion]:
        async with self._conn.execute(
            "SELECT * FROM memory_asset_versions WHERE asset_id=? ORDER BY version DESC",
            (asset_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_version(row) for row in rows]

    # ── Agents and bindings ───────────────────────────────────────────────

    async def upsert_agent(
        self, *, agent_key: str, wiki_id: str, name: str, description: str = ""
    ) -> AgentProfile:
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO memory_agents (agent_key, wiki_id, name, description, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(wiki_id, agent_key) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                updated_at=excluded.updated_at
            """,
            (agent_key, wiki_id, name, description, now, now),
        )
        await self._conn.commit()
        agent = await self.get_agent(agent_key, wiki_id)
        assert agent is not None
        return agent

    async def get_agent(self, agent_key: str, wiki_id: str) -> AgentProfile | None:
        async with self._conn.execute(
            "SELECT * FROM memory_agents WHERE wiki_id=? AND agent_key=?",
            (wiki_id, agent_key),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_agent(row) if row else None

    async def list_agents(self, wiki_id: str) -> list[AgentProfile]:
        async with self._conn.execute(
            "SELECT * FROM memory_agents WHERE wiki_id=? ORDER BY agent_key ASC",
            (wiki_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_agent(row) for row in rows]

    async def delete_agent(self, agent_key: str, wiki_id: str) -> bool:
        await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                "DELETE FROM memory_asset_bindings WHERE wiki_id=? AND agent_key=?",
                (wiki_id, agent_key),
            )
            cursor = await self._conn.execute(
                "DELETE FROM memory_agents WHERE wiki_id=? AND agent_key=?",
                (wiki_id, agent_key),
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        return cursor.rowcount > 0

    async def bind_asset(
        self,
        *,
        agent_key: str,
        wiki_id: str,
        asset_id: str,
        mode: str = "always",
        priority: int = 100,
    ) -> AssetBinding:
        if mode not in BINDING_MODES:
            raise ValueError(f"Unsupported binding mode: {mode}")
        if await self.get_agent(agent_key, wiki_id) is None:
            raise KeyError(f"Agent '{agent_key}' not found")
        if await self.get_asset(asset_id) is None:
            raise KeyError(f"Memory asset '{asset_id}' not found")
        await self._conn.execute(
            """
            INSERT INTO memory_asset_bindings (wiki_id, agent_key, asset_id, mode, priority, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(wiki_id, agent_key, asset_id) DO UPDATE SET
                mode=excluded.mode,
                priority=excluded.priority
            """,
            (wiki_id, agent_key, asset_id, mode, priority, _now()),
        )
        await self._conn.commit()
        return AssetBinding(
            agent_key=agent_key, asset_id=asset_id, mode=mode, priority=priority
        )

    async def unbind_asset(self, *, agent_key: str, wiki_id: str, asset_id: str) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM memory_asset_bindings WHERE wiki_id=? AND agent_key=? AND asset_id=?",
            (wiki_id, agent_key, asset_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_bindings(self, *, agent_key: str, wiki_id: str) -> list[AssetBinding]:
        async with self._conn.execute(
            "SELECT agent_key, asset_id, mode, priority FROM memory_asset_bindings "
            "WHERE wiki_id=? AND agent_key=? ORDER BY priority ASC, asset_id ASC",
            (wiki_id, agent_key),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            AssetBinding(
                agent_key=row["agent_key"],
                asset_id=row["asset_id"],
                mode=row["mode"],
                priority=row["priority"],
            )
            for row in rows
        ]


def _row_to_asset(row: aiosqlite.Row) -> MemoryAsset:
    return MemoryAsset(
        id=row["id"],
        wiki_id=row["wiki_id"],
        asset_type=row["asset_type"],
        layer=row["layer"],
        name=row["name"],
        owner=row["owner"],
        scope=row["scope"],
        status=row["status"],
        visibility=row["visibility"],
        version=row["version"],
        page_slug=row["page_slug"],
        summary=row["summary"],
        body=row["body"],
        tags=json.loads(row["tags"]),
        metadata=json.loads(row["metadata"]),
        citations=[Citation(**c) for c in json.loads(row["citations"])],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_version(row: aiosqlite.Row) -> MemoryAssetVersion:
    return MemoryAssetVersion(
        asset_id=row["asset_id"],
        version=row["version"],
        name=row["name"],
        summary=row["summary"],
        body=row["body"],
        status=row["status"],
        metadata=json.loads(row["metadata"]),
        citations=[Citation(**c) for c in json.loads(row["citations"])],
        change_note=row["change_note"],
        created_at=row["created_at"],
    )


def _row_to_agent(row: aiosqlite.Row) -> AgentProfile:
    return AgentProfile(
        agent_key=row["agent_key"],
        wiki_id=row["wiki_id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
