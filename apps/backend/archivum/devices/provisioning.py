"""Reusable tokens that let an agent link its own machine.

A pairing token is single-use and short-lived, which is right when a person is
copying it into a terminal and wrong when an agent is setting up a machine
nobody is watching. A provisioning token is the reusable counterpart.

It earns that reach by being able to do strictly less. A device key
authenticates every MCP tool; a provisioning secret is accepted at one endpoint
and reads nothing. So the worst a leaked provisioning token can do is create
device keys — bounded by `device_cap`, visible in the activity stream as they
are minted, and removable in one step along with every key they produced.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from archivum.devices.pairing import encode_pairing_token
from archivum.devices.repository import DeviceRepository
from archivum.sharing.models import hash_token

PROVISION_PREFIX = "arch1p_"
DEFAULT_DEVICE_CAP = 25

# One message for every failure mode, for the reason pairing gives one: a
# caller learning *why* it was refused learns whether a guessed secret exists.
_REFUSED = "Provisioning token is not valid. Issue a new one from Settings."


class ProvisioningError(Exception):
    """A provisioning token was unknown, expired, revoked, or at its cap."""


class ProvisioningService:
    def __init__(
        self, conn: aiosqlite.Connection, *, device_cap: int = DEFAULT_DEVICE_CAP
    ) -> None:
        self.conn = conn
        self.device_cap = device_cap
        self.devices = DeviceRepository(conn)

    async def issue(
        self,
        base_url: str,
        *,
        wiki_id: str = "default",
        name: str = "",
        ttl_seconds: int | None = None,
        device_cap: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Mint a provisioning token and return it with its stored record.

        The raw token is returned once and never recoverable, matching how
        device keys and share links are handled.
        """
        secret = secrets.token_urlsafe(32)
        token_id = f"prov_{secrets.token_urlsafe(12)}"
        expires_at = (
            None
            if ttl_seconds is None
            else (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        )
        await self.conn.execute(
            "INSERT INTO provisioning_tokens "
            "(id, wiki_id, name, secret_hash, expires_at, device_cap) VALUES (?,?,?,?,?,?)",
            (
                token_id,
                wiki_id,
                name,
                hash_token(secret),
                expires_at,
                self.device_cap if device_cap is None else device_cap,
            ),
        )
        await self.conn.commit()
        record = await self.get(token_id)
        assert record is not None
        return encode_pairing_token(base_url, secret, prefix=PROVISION_PREFIX), record

    async def get(self, token_id: str) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM provisioning_tokens WHERE id=?", (token_id,)
        ) as cur:
            row = await cur.fetchone()
        return self._public(dict(row)) if row else None

    async def list_tokens(self, wiki_id: str = "default") -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM provisioning_tokens WHERE wiki_id=? ORDER BY created_at DESC",
            (wiki_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._public(dict(row)) for row in rows]

    async def provision(
        self,
        secret: str,
        device_name: str,
        *,
        fingerprint: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Exchange a provisioning secret for a fresh device key.

        The whole exchange runs in one write transaction. Checked and minted
        separately, two concurrent redemptions both saw room under the cap and
        both minted; and a redemption that passed the liveness check just
        before `revoke(revoke_devices=True)` inserted a live key *after* the
        revocation. That defeats both controls that exist to contain a leaked
        token. `BEGIN IMMEDIATE` takes the write lock up front, so a second
        caller waits rather than reading a count that is about to change.
        """
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = await self._live_token(secret)

            # Re-running setup on a machine replaces that machine's key rather
            # than adding a second one, which is what `connect` already does on
            # re-run. Before the cap check on purpose: a machine reinstalling
            # repeatedly must not exhaust the cap it already occupies a slot of.
            replaced = await self._revoke_fingerprint(row["id"], fingerprint)
            if not replaced and await self._live_device_count(row["id"]) >= row["device_cap"]:
                raise ProvisioningError(
                    "This provisioning token has reached its device limit. "
                    "Revoke a device or issue a new token from Settings."
                )

            device, raw_key = await self.devices.mint(
                device_name,
                wiki_id=row["wiki_id"],
                provisioned_by=row["id"],
                fingerprint=fingerprint,
                commit=False,
            )
            await self.conn.execute(
                "UPDATE provisioning_tokens SET last_used_at=datetime('now') WHERE id=?",
                (row["id"],),
            )
        except BaseException:
            await self.conn.rollback()
            raise
        await self.conn.commit()
        return device, raw_key

    async def revoke(self, token_id: str, *, revoke_devices: bool = False) -> bool:
        """Retire a token, optionally taking the keys it minted with it.

        Devices survive by default: rotating a provisioning secret is routine
        housekeeping and should not log out every machine that ever used it.
        Passing `revoke_devices` is the response to a leak, where every key the
        token produced is suspect.
        """
        if revoke_devices:
            await self.conn.execute(
                "UPDATE device_keys SET revoked_at=datetime('now') "
                "WHERE provisioned_by=? AND revoked_at IS NULL",
                (token_id,),
            )
        cur = await self.conn.execute(
            "UPDATE provisioning_tokens SET revoked_at=datetime('now') "
            "WHERE id=? AND revoked_at IS NULL",
            (token_id,),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def _live_token(self, secret: str) -> dict[str, Any]:
        async with self.conn.execute(
            "SELECT * FROM provisioning_tokens "
            "WHERE secret_hash=? AND revoked_at IS NULL",
            (hash_token(secret),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise ProvisioningError(_REFUSED)
        expires_at = row["expires_at"]
        if expires_at and datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc):
            raise ProvisioningError(_REFUSED)
        return dict(row)

    async def _live_device_count(self, token_id: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM device_keys "
            "WHERE provisioned_by=? AND revoked_at IS NULL",
            (token_id,),
        ) as cur:
            row = await cur.fetchone()
        return int(row["n"])

    async def _revoke_fingerprint(self, token_id: str, fingerprint: str | None) -> bool:
        """Revoke this machine's previous key. True when one was actually live."""
        if not fingerprint:
            return False
        cur = await self.conn.execute(
            "UPDATE device_keys SET revoked_at=datetime('now') "
            "WHERE provisioned_by=? AND fingerprint=? AND revoked_at IS NULL",
            (token_id, fingerprint),
        )
        return cur.rowcount > 0

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        """Everything but the hash.

        Returning `secret_hash` to a settings screen would put an offline-
        guessable value on a page whose whole job is being looked at.
        """
        return {key: value for key, value in row.items() if key != "secret_hash"}
