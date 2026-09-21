"""Provisioning tokens: one reusable secret an agent redeems without a human.

A pairing token is single-use and expires in fifteen minutes, which is right
when a person is copying it into a terminal. It is wrong for an agent setting
itself up on a machine nobody is watching. A provisioning token is the reusable
counterpart, and it buys that convenience by being able to do strictly less: it
mints device keys and cannot read a single page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from archivum.devices.provisioning import (
    PROVISION_PREFIX,
    ProvisioningError,
    ProvisioningService,
)
from archivum.devices.pairing import decode_pairing_token
from archivum.devices.repository import DeviceRepository
from archivum.devices.schema import init_devices_schema


@pytest.fixture
async def conn(tmp_path):
    async with aiosqlite.connect(tmp_path / "devices.db") as conn:
        conn.row_factory = aiosqlite.Row
        await init_devices_schema(conn)
        yield conn


@pytest.fixture
def service(conn):
    return ProvisioningService(conn)


async def _issue(service, **kwargs):
    token, _record = await service.issue("https://vault.example.com", **kwargs)
    return token


@pytest.mark.asyncio
async def test_issued_token_carries_the_server_url(service):
    """The env var must be self-sufficient.

    `ARCHIVUM_PROVISION_TOKEN` is the only thing a fresh machine is given, so
    the URL travels inside it exactly as it does for pairing. Requiring a
    second variable for the host would reintroduce the setup step this removes.
    """
    token = await _issue(service)

    assert token.startswith(PROVISION_PREFIX)
    base_url, _secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    assert base_url == "https://vault.example.com"


@pytest.mark.asyncio
async def test_provision_mints_a_usable_device_key(service, conn):
    token = await _issue(service)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)

    device, raw_key = await service.provision(secret, "laptop")

    assert raw_key.startswith("amk_")
    assert device["name"] == "laptop"
    assert await DeviceRepository(conn).verify(raw_key) is not None


@pytest.mark.asyncio
async def test_the_same_token_provisions_more_than_one_machine(service):
    """The difference from pairing that justifies the whole type."""
    token = await _issue(service)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)

    _first, first_key = await service.provision(secret, "laptop")
    _second, second_key = await service.provision(secret, "desktop")

    assert first_key != second_key


@pytest.mark.asyncio
async def test_unknown_secret_is_refused(service):
    with pytest.raises(ProvisioningError):
        await service.provision("never-issued", "laptop")


@pytest.mark.asyncio
async def test_revoked_token_stops_minting(service):
    token, record = await service.issue("https://vault.example.com")
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    await service.revoke(record["id"])

    with pytest.raises(ProvisioningError):
        await service.provision(secret, "laptop")


@pytest.mark.asyncio
async def test_expired_token_stops_minting(service, conn):
    token, record = await service.issue("https://vault.example.com")
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    await conn.execute(
        "UPDATE provisioning_tokens SET expires_at=? WHERE id=?", (past, record["id"])
    )
    await conn.commit()

    with pytest.raises(ProvisioningError):
        await service.provision(secret, "laptop")


@pytest.mark.asyncio
async def test_a_token_with_no_expiry_keeps_working(service):
    """Expiry is opt-in: a dotfile-managed token that dies silently at midnight
    is worse than one the owner chose to keep."""
    token = await _issue(service, ttl_seconds=None)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)

    _device, raw_key = await service.provision(secret, "laptop")

    assert raw_key.startswith("amk_")


@pytest.mark.asyncio
async def test_device_cap_bounds_the_blast_radius(service):
    """A leaked token should cost a bounded number of keys, not unlimited ones."""
    token = await _issue(service, device_cap=2)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)

    await service.provision(secret, "one")
    await service.provision(secret, "two")

    with pytest.raises(ProvisioningError):
        await service.provision(secret, "three")


@pytest.mark.asyncio
async def test_reprovisioning_a_fingerprint_revokes_that_machines_old_key(service, conn):
    """Re-running setup on a machine must not leave two live keys for it.

    This mirrors what `connect` already does on re-run, and it is what keeps a
    machine that reinstalls repeatedly from consuming the device cap.
    """
    token = await _issue(service, device_cap=2)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    devices = DeviceRepository(conn)

    _first, first_key = await service.provision(secret, "laptop", fingerprint="fp-1")
    _second, second_key = await service.provision(secret, "laptop", fingerprint="fp-1")

    assert await devices.verify(first_key) is None
    assert await devices.verify(second_key) is not None


@pytest.mark.asyncio
async def test_reprovisioning_a_fingerprint_does_not_consume_the_cap(service):
    token = await _issue(service, device_cap=1)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)

    await service.provision(secret, "laptop", fingerprint="fp-1")
    _device, raw_key = await service.provision(secret, "laptop", fingerprint="fp-1")

    assert raw_key.startswith("amk_")


@pytest.mark.asyncio
async def test_revoking_a_token_can_take_its_devices_with_it(service, conn):
    """The reason a mint is recorded against its token at all."""
    token, record = await service.issue("https://vault.example.com")
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    _device, raw_key = await service.provision(secret, "laptop")

    await service.revoke(record["id"], revoke_devices=True)

    assert await DeviceRepository(conn).verify(raw_key) is None


@pytest.mark.asyncio
async def test_revoking_a_token_leaves_devices_alone_by_default(service, conn):
    """Rotating the provisioning secret should not log out every machine."""
    token, record = await service.issue("https://vault.example.com")
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    _device, raw_key = await service.provision(secret, "laptop")

    await service.revoke(record["id"])

    assert await DeviceRepository(conn).verify(raw_key) is not None


@pytest.mark.asyncio
async def test_a_provisioning_secret_is_not_a_device_key(service, conn):
    """The property the whole key class exists for.

    If a provisioning secret authenticated as a device, the token stored in a
    dotfile would read the vault, and splitting the types would have bought
    nothing.
    """
    token = await _issue(service)
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)

    assert await DeviceRepository(conn).verify(secret) is None
    assert await DeviceRepository(conn).verify(token) is None


@pytest.mark.asyncio
async def test_provisioning_records_when_the_token_was_last_used(service, conn):
    """An owner deciding whether to retire a token needs to know if it is live."""
    token, record = await service.issue("https://vault.example.com")
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    await service.provision(secret, "laptop")

    async with conn.execute(
        "SELECT last_used_at FROM provisioning_tokens WHERE id=?", (record["id"],)
    ) as cur:
        row = await cur.fetchone()

    assert row["last_used_at"] is not None


@pytest.mark.asyncio
async def test_listing_tokens_never_exposes_the_secret(service):
    await _issue(service, name="dotfiles")

    listed = await service.list_tokens()

    assert [t["name"] for t in listed] == ["dotfiles"]
    assert all("secret" not in key for token in listed for key in token)
