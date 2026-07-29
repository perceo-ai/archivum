from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from archivum.api import auth as auth_routes
from archivum.api import export as export_routes
from archivum.api import folders as folders_routes
from archivum.api import ingest as ingest_routes
from archivum.api import life_os as life_os_routes
from archivum.api import pages as pages_routes
from archivum.api import public as public_routes
from archivum.api import share as share_routes
from archivum.api.graph import router as graph_router
from archivum.api.query import router as query_router
from archivum.api.search import router as search_router
from archivum.api.sources import router as sources_router
from archivum.api.system import router as system_router
from archivum.config import Settings, get_settings
from archivum.db import qdrant_client as qdrant
from archivum.db import sqlite
from archivum.db import graph
from archivum.auth import hash_password
from archivum.logging_config import setup_logging
from archivum.observability import new_trace_id, set_trace_id
from archivum.page_write_queue import run_page_write_worker
from archivum.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


class _TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        trace_id = request.headers.get("x-trace-id") or new_trace_id("http")
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class _CSRFProtection(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        method = request.method.upper()
        if method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            if request.url.path == "/api/auth/refresh":
                return await call_next(request)

            auth_header = request.headers.get("authorization")
            # Non-browser clients (MCP/CLI) use Bearer tokens; skip CSRF.
            if not (auth_header and auth_header.startswith("Bearer ")):
                has_cookie_auth = "access_token" in request.cookies or "refresh_token" in request.cookies
                if has_cookie_auth:
                    csrf_cookie = request.cookies.get("csrf_token")
                    csrf_header = request.headers.get("x-csrf-token")
                    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                        return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()

    setup_logging()
    set_trace_id(new_trace_id("startup"))
    logger.info(
        "Starting Archivum API",
        extra={"qdrant_url": settings.qdrant_url, "db_path": str(settings.db_path), "wiki_dir": str(settings.wiki_dir)},
    )

    # Ensure directories exist
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.kuzu_path.mkdir(parents=True, exist_ok=True)

    # Init derived stores
    await sqlite.init_db(settings)
    await qdrant.init_collection(settings)
    await graph.init_graph(settings)

    # Ensure owner exists
    owner_pw = settings.owner_password or secrets.token_urlsafe(24)
    await sqlite.ensure_owner_exists(settings.owner_username, hash_password(owner_pw))

    write_worker_task: asyncio.Task[None] | None = None
    if settings.page_write_worker_enabled:
        write_worker_task = asyncio.create_task(run_page_write_worker(settings))

    try:
        yield
    finally:
        if write_worker_task:
            write_worker_task.cancel()
            try:
                await write_worker_task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(title="Archivum API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(_TraceMiddleware)
    app.add_middleware(_SecurityHeadersMiddleware)
    app.add_middleware(_CSRFProtection)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(auth_routes.router)
    app.include_router(export_routes.router)
    app.include_router(folders_routes.router)
    app.include_router(pages_routes.router)
    app.include_router(public_routes.router)
    app.include_router(ingest_routes.router)
    app.include_router(life_os_routes.router)
    app.include_router(search_router)
    app.include_router(query_router)
    app.include_router(graph_router)
    app.include_router(sources_router)
    app.include_router(system_router)
    app.include_router(share_routes.router)
    app.include_router(share_routes.mgmt_router)

    return app


app = create_app()
