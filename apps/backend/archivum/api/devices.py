from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from archivum.auth import CurrentUser, require_owner
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.devices.clients import client_registry
from archivum.devices.pairing import PairingError, PairingService
from archivum.devices.provisioning import ProvisioningError, ProvisioningService
from archivum.devices.repository import DeviceRepository

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# Never let a device row reach a client with its hash attached: the hash is the
# only thing standing between a leaked response body and an offline attack.
_PUBLIC_FIELDS = ("id", "name", "created_at", "last_seen_at", "revoked_at")


class RedeemRequest(BaseModel):
    secret: str = Field(min_length=1)
    device_name: str = Field(min_length=1, max_length=120)


class ProvisionRequest(BaseModel):
    secret: str = Field(min_length=1)
    device_name: str = Field(min_length=1, max_length=120)
    # Stable per machine, supplied by the CLI. Its only job is letting a
    # machine that re-runs setup replace its own key instead of accumulating a
    # second one, so it is matched, never trusted.
    fingerprint: str | None = Field(default=None, max_length=200)


class MintDeviceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class IssueProvisioningTokenRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    ttl_seconds: int | None = Field(default=None, ge=60)
    device_cap: int | None = Field(default=None, ge=1, le=1000)


def _public(device: dict[str, Any]) -> dict[str, Any]:
    return {field: device[field] for field in _PUBLIC_FIELDS}


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class SseUrlUnresolved(Exception):
    """The only SSE URL we could offer points at the wrong machine."""


def _is_loopback(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in _LOOPBACK_HOSTS or host.endswith(".localhost")


def _sse_url(request: Request, settings: Settings) -> str:
    """Resolve the SSE URL to hand a machine being linked.

    `mcp_public_url` is optional and commented out in `.env.example`, so a
    remote install can easily reach here with only `API_PUBLIC_URL` set. The
    fallback — `http://localhost:{mcp_port}/sse` — is correct on a
    single-machine install and actively wrong everywhere else: it is written
    into the linked machine's client configs, where it names *that* machine's
    port 8001. Refuse rather than hand out a URL that cannot reach this vault.
    """
    # Same idiom as `api/system.py`, which already resolves this endpoint.
    resolved = settings.mcp_public_url.strip() or f"http://localhost:{settings.mcp_port}/sse"
    if _is_loopback(resolved) and not _is_loopback(_api_base(request, settings)):
        raise SseUrlUnresolved(
            f"This vault is reached at {_api_base(request, settings)}, but the MCP "
            f"endpoint resolves to {resolved}, which points at the machine running "
            "`archivum connect` rather than at this vault. Set MCP_PUBLIC_URL in .env "
            "to the URL your MCP server is reachable at and restart the stack. The "
            "pairing token has not been spent — retry with the same one."
        )
    return resolved


def _api_base(request: Request, settings: Settings) -> str:
    configured = settings.api_public_url.strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


async def require_device(request: Request) -> dict[str, Any]:
    """Authenticate a caller by its own device key.

    Owner routes decode a JWT; a device key is an opaque bearer that only
    `DeviceRepository.verify` understands, so a device authenticating as
    itself needs its own dependency.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, raw_key = header.partition(" ")
    if scheme.lower() != "bearer" or not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device key required")
    async with sqlite.get_db() as conn:
        device = await DeviceRepository(conn).verify(raw_key)
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device key required")
    return device


@router.post("/pairing-tokens")
async def issue_pairing_token(
    request: Request,
    current_user: CurrentUser = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    async with sqlite.get_db() as conn:
        token, expires_at = await PairingService(conn).issue(
            _api_base(request, settings), wiki_id=current_user.wiki_id
        )
    return {"token": token, "expires_at": expires_at}


@router.post("/pairing/redeem")
async def redeem_pairing_token(
    body: RedeemRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    # Resolved before redeem, never after: redeem burns the token, and a
    # server misconfiguration must not cost the user their one-shot token.
    try:
        sse_url = _sse_url(request, settings)
    except SseUrlUnresolved as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": str(exc), "code": "mcp_url_unresolved"},
        ) from exc

    async with sqlite.get_db() as conn:
        try:
            device, raw_key = await PairingService(conn).redeem(
                body.secret, body.device_name
            )
        except PairingError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": str(exc), "code": "pairing_refused"},
            ) from exc
    return {
        "device_id": device["id"],
        "key": raw_key,
        "sse_url": sse_url,
        "vault_name": settings.owner_username or "Archivum",
        "skill_url": f"{_api_base(request, settings)}/api/mcp/skill",
    }


def _streamable_url(sse_url: str) -> str:
    """The `/mcp` sibling of a resolved `/sse` URL.

    One app serves both transports off one port, so the difference is the path
    and nothing else. Derived rather than separately configured because two
    settings that must agree are two settings that will eventually disagree.
    """
    if sse_url.endswith("/sse"):
        return f"{sse_url[: -len('/sse')]}/mcp"
    return sse_url


@router.post("/provisioning-tokens")
async def issue_provisioning_token(
    body: IssueProvisioningTokenRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Mint a reusable token an agent can link itself with.

    Returned once. Unlike a pairing token this is meant to live in a shell
    profile or secret manager, so the response says plainly what it can and
    cannot do rather than leaving that to documentation nobody reads.
    """
    async with sqlite.get_db() as conn:
        token, record = await ProvisioningService(conn).issue(
            _api_base(request, settings),
            wiki_id=current_user.wiki_id,
            name=body.name,
            ttl_seconds=body.ttl_seconds,
            device_cap=body.device_cap,
        )
    return {
        "token": token,
        "env_var": "ARCHIVUM_PROVISION_TOKEN",
        **record,
    }


@router.get("/provisioning-tokens")
async def list_provisioning_tokens(
    current_user: CurrentUser = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with sqlite.get_db() as conn:
        return await ProvisioningService(conn).list_tokens(wiki_id=current_user.wiki_id)


@router.delete("/provisioning-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_provisioning_token(
    token_id: str,
    revoke_devices: bool = False,
    current_user: CurrentUser = Depends(require_owner),
) -> None:
    """Retire a token. `revoke_devices` is the answer to a leak, not to rotation."""
    async with sqlite.get_db() as conn:
        revoked = await ProvisioningService(conn).revoke(
            token_id, revoke_devices=revoke_devices
        )
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown token")


@router.post("/pairing/provision")
async def provision_device(
    body: ProvisionRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Exchange a provisioning secret for this machine's own device key."""
    # Resolved before minting for the reason redeem does it: a server that
    # cannot name its own MCP endpoint should fail before it hands out a
    # credential pointing at the wrong machine.
    try:
        sse_url = _sse_url(request, settings)
    except SseUrlUnresolved as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": str(exc), "code": "mcp_url_unresolved"},
        ) from exc

    async with sqlite.get_db() as conn:
        try:
            device, raw_key = await ProvisioningService(conn).provision(
                body.secret, body.device_name, fingerprint=body.fingerprint
            )
        except ProvisioningError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": str(exc), "code": "provisioning_refused"},
            ) from exc
    return {
        "device_id": device["id"],
        "key": raw_key,
        "sse_url": sse_url,
        "mcp_url": _streamable_url(sse_url),
        "vault_name": settings.owner_username or "Archivum",
        "skill_url": f"{_api_base(request, settings)}/api/mcp/skill",
    }


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def mint_device_key(
    body: MintDeviceRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Mint a key directly, for clients that cannot run an installer.

    claude.ai and ChatGPT are configured by pasting a URL and a header into a
    browser, so there is no machine to run `connect` and no pairing token to
    redeem. The key is returned once and appears in the device list like any
    other, which is what keeps it revocable per row.
    """
    try:
        sse_url = _sse_url(request, settings)
    except SseUrlUnresolved as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": str(exc), "code": "mcp_url_unresolved"},
        ) from exc

    async with sqlite.get_db() as conn:
        device, raw_key = await DeviceRepository(conn).mint(
            body.name, wiki_id=current_user.wiki_id
        )
    return {
        **_public(device),
        "key": raw_key,
        "sse_url": sse_url,
        "mcp_url": _streamable_url(sse_url),
    }


@router.get("/clients")
async def get_client_registry(
    request: Request,
    _device: dict[str, Any] = Depends(require_device),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """What to write, and where, for every client this server knows about.

    Served rather than compiled into the CLI so that supporting a new agent is
    a server-side edit every linked machine picks up on its next run.
    """
    try:
        sse_url = _sse_url(request, settings)
    except SseUrlUnresolved as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": str(exc), "code": "mcp_url_unresolved"},
        ) from exc
    return client_registry(sse_url=sse_url, streamable_url=_streamable_url(sse_url))


SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "agent_skills" / "archivum-memory" / "SKILL.md"
)


@router.get("/skill", response_class=PlainTextResponse)
async def get_agent_skill() -> str:
    """Serve the archivum-memory skill so `connect` can install it anywhere.

    Unauthenticated on purpose: the skill is public repository content that
    tells an agent which tools to reach for, and gating it would mean a machine
    could not be set up before it has a key.
    """
    if not SKILL_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Agent skill is not bundled with this build.", "code": "skill_missing"},
        )
    return SKILL_PATH.read_text()


@router.get("/devices/self")
async def get_own_device(
    device: dict[str, Any] = Depends(require_device),
) -> dict[str, Any]:
    """What `--status` calls: a 200 here means the caller's own key still authenticates.

    Registered ahead of `/devices/{device_id}` so "self" is never captured as
    a device id path parameter.
    """
    return _public(device)


@router.delete("/devices/self")
async def revoke_own_device(
    device: dict[str, Any] = Depends(require_device),
) -> dict[str, bool]:
    """What `--revoke` calls: a device key can revoke only itself.

    Registered ahead of `/devices/{device_id}` for the same routing reason as
    `get_own_device` above.
    """
    async with sqlite.get_db() as conn:
        revoked = await DeviceRepository(conn).revoke(device["id"])
    return {"revoked": revoked}


@router.get("/devices")
async def list_devices(
    current_user: CurrentUser = Depends(require_owner),
) -> dict[str, list[dict[str, Any]]]:
    async with sqlite.get_db() as conn:
        devices = await DeviceRepository(conn).list_devices(current_user.wiki_id)
    return {"devices": [_public(d) for d in devices]}


@router.delete("/devices/{device_id}")
async def revoke_device(
    device_id: str,
    current_user: CurrentUser = Depends(require_owner),
) -> dict[str, bool]:
    async with sqlite.get_db() as conn:
        repo = DeviceRepository(conn)
        # DeviceRepository.revoke() matches by id alone, with no wiki scoping
        # of its own — mirror the check sharing.py's revoke_grant/revoke_principal
        # make, so an owner of one wiki cannot revoke another wiki's device by
        # guessing its id.
        device = await repo.get(device_id)
        if device is None or device["wiki_id"] != current_user.wiki_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "No such device", "code": "device_not_found"},
            )
        revoked = await repo.revoke(device_id)
    return {"revoked": revoked}
