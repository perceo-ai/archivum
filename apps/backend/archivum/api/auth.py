"""Authentication routes: /api/auth/*"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from archivum.auth import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    require_owner,
    verify_password,
)
from archivum.config import Settings, get_settings
from archivum.db import sqlite

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    # v1 UX: password-only login for the owner (username defaults to admin)
    password: str
    username: str | None = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"  # owner|collaborator|viewer


class AuthResponse(BaseModel):
    username: str
    role: str
    wiki_id: str


def _set_access_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,  # set True behind HTTPS
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/auth/refresh",
    )


def _set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    # Double-submit cookie: frontend reads `csrf_token` and echoes it back via `X-CSRF-Token`.
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=False,
        samesite="strict",
        secure=False,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    username = (body.username or settings.owner_username).strip()
    user = await sqlite.get_user_by_username(username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        username=user["username"],
        role=user["role"],
        wiki_id=user.get("wiki_id", "default"),
        settings=settings,
    )

    csrf_token = secrets.token_urlsafe(32)

    raw_refresh, hashed_refresh = create_refresh_token()
    expires_at = (datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)).isoformat()
    await sqlite.store_refresh_token(user["id"], hashed_refresh, expires_at)

    _set_access_cookie(response, access_token, settings)
    _set_refresh_cookie(response, raw_refresh, settings)
    _set_csrf_cookie(response, csrf_token, settings)

    return AuthResponse(username=user["username"], role=user["role"], wiki_id=user.get("wiki_id", "default"))


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")
    response.delete_cookie("csrf_token", path="/")
    return {"detail": "Logged out"}


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = await sqlite.get_refresh_token(token_hash)
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked refresh token")

    expires_at = datetime.fromisoformat(record["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    # Rotate refresh token
    await sqlite.revoke_refresh_token(token_hash)
    new_raw, new_hashed = create_refresh_token()
    new_expires = (datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)).isoformat()
    await sqlite.store_refresh_token(record["user_id"], new_hashed, new_expires)

    access_token = create_access_token(
        username=record["username"],
        role=record["role"],
        wiki_id=record.get("wiki_id", "default"),
        settings=settings,
    )

    csrf_token = secrets.token_urlsafe(32)

    _set_access_cookie(response, access_token, settings)
    _set_refresh_cookie(response, new_raw, settings)
    _set_csrf_cookie(response, csrf_token, settings)

    return AuthResponse(username=record["username"], role=record["role"], wiki_id=record.get("wiki_id", "default"))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AuthResponse:
    if current_user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can register new users")

    existing = await sqlite.get_user_by_username(body.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"detail": "Username already exists", "code": "username_taken"})

    if body.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"detail": "Cannot create another owner", "code": "invalid_role"})

    hashed = hash_password(body.password)
    await sqlite.create_user(username=body.username, password_hash=hashed, role=body.role, wiki_id=current_user.wiki_id)

    return AuthResponse(username=body.username, role=body.role, wiki_id=current_user.wiki_id)


@router.get("/me", response_model=AuthResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(username=current_user.username, role=current_user.role, wiki_id=current_user.wiki_id)


# ── Invite token endpoints ─────────────────────────────────────────────────────

class CreateInviteRequest(BaseModel):
    role: str = "viewer"  # collaborator|viewer
    expires_in_days: int | None = 7


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: CreateInviteRequest,
    current_user: CurrentUser = Depends(require_owner),
) -> dict:
    if body.role not in {"collaborator", "viewer"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role must be 'collaborator' or 'viewer'")

    token = secrets.token_urlsafe(32)
    expires_at: str | None = None
    if body.expires_in_days is not None:
        expires_at = (datetime.now(UTC) + timedelta(days=body.expires_in_days)).isoformat()

    await sqlite.create_invite_token(
        wiki_id=current_user.wiki_id,
        token=token,
        role=body.role,
        created_by=current_user.username,
        expires_at=expires_at,
    )

    return {
        "token": token,
        "url": f"/register?invite={token}",
        "role": body.role,
        "expires_at": expires_at,
    }


@router.get("/invites")
async def list_invites(
    current_user: CurrentUser = Depends(require_owner),
) -> list[dict]:
    return await sqlite.list_invite_tokens(current_user.wiki_id)


class RegisterWithInviteRequest(BaseModel):
    invite_token: str
    username: str
    password: str


@router.post("/register-with-invite", status_code=status.HTTP_201_CREATED)
async def register_with_invite(body: RegisterWithInviteRequest) -> dict:
    record = await sqlite.get_invite_token(body.invite_token)
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite token")

    if record["used"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token has already been used")

    if record["expires_at"]:
        expires_at = datetime.fromisoformat(str(record["expires_at"]).replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token has expired")

    existing = await sqlite.get_user_by_username(body.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    hashed = hash_password(body.password)
    await sqlite.create_user(
        username=body.username,
        password_hash=hashed,
        role=record["role"],
        wiki_id=record["wiki_id"],
    )
    await sqlite.mark_invite_used(body.invite_token)

    return {"detail": "registered"}
