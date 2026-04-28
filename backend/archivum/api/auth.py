"""Authentication routes: /api/auth/*"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from archivum.auth import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from archivum.config import Settings, get_settings
from archivum.db import sqlite

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"  # owner|collaborator|viewer


class AuthResponse(BaseModel):
    username: str
    role: str
    wiki_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_access_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,  # Set True in production behind HTTPS
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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    user = await sqlite.get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        username=user["username"],
        role=user["role"],
        wiki_id=user.get("wiki_id", "default"),
        settings=settings,
    )
    raw_refresh, hashed_refresh = create_refresh_token()
    expires_at = (
        datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    ).isoformat()

    await sqlite.store_refresh_token(user["id"], hashed_refresh, expires_at)

    _set_access_cookie(response, access_token, settings)
    _set_refresh_cookie(response, raw_refresh, settings)

    return AuthResponse(
        username=user["username"],
        role=user["role"],
        wiki_id=user.get("wiki_id", "default"),
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")
    return {"detail": "Logged out"}


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    response: Response,
    # Read raw refresh token from httpOnly cookie
    settings: Settings = Depends(get_settings),
    # We can't use Cookie() nicely in Depends chain, so extract manually:
) -> AuthResponse:
    # This will be handled via request directly in FastAPI
    raise HTTPException(status_code=400, detail="Use POST with cookie")


@router.post("/refresh/token", response_model=AuthResponse)
async def refresh_token(
    response: Response,
    settings: Settings = Depends(get_settings),
    # Inject request to read cookie manually
) -> AuthResponse:
    raise HTTPException(status_code=400, detail="Use the /refresh endpoint")


from fastapi import Request  # noqa: E402


@router.post("/refresh", response_model=AuthResponse, include_in_schema=False)
async def _refresh_duplicate():  # pragma: no cover
    pass


# Override with correct implementation
router.routes = [r for r in router.routes if getattr(r, "path", "") != "/api/auth/refresh" or getattr(r, "name", "") == "refresh"]


@router.post("/token/refresh", response_model=AuthResponse)
async def token_refresh(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = await sqlite.get_refresh_token(token_hash)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )

    # Check expiry
    expires_at = datetime.fromisoformat(record["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # Rotate: revoke old, issue new
    await sqlite.revoke_refresh_token(token_hash)
    new_raw, new_hashed = create_refresh_token()
    new_expires = (
        datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    ).isoformat()
    await sqlite.store_refresh_token(record["user_id"], new_hashed, new_expires)

    access_token = create_access_token(
        username=record["username"],
        role=record["role"],
        wiki_id=record.get("wiki_id", "default"),
        settings=settings,
    )

    _set_access_cookie(response, access_token, settings)
    _set_refresh_cookie(response, new_raw, settings)

    return AuthResponse(
        username=record["username"],
        role=record["role"],
        wiki_id=record.get("wiki_id", "default"),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AuthResponse:
    """Only the owner can register new users."""
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can register new users",
        )

    existing = await sqlite.get_user_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Username already exists", "code": "username_taken"},
        )

    if body.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Cannot create another owner", "code": "invalid_role"},
        )

    hashed = hash_password(body.password)
    await sqlite.create_user(
        username=body.username,
        password_hash=hashed,
        role=body.role,
        wiki_id=current_user.wiki_id,
    )

    return AuthResponse(
        username=body.username,
        role=body.role,
        wiki_id=current_user.wiki_id,
    )


@router.get("/me", response_model=AuthResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(
        username=current_user.username,
        role=current_user.role,
        wiki_id=current_user.wiki_id,
    )
