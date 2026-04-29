from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from archivum.api import auth as auth_routes
from archivum.api import ingest as ingest_routes
from archivum.api import pages as pages_routes
from archivum.api.graph import router as graph_router
from archivum.api.query import router as query_router
from archivum.api.search import router as search_router
from archivum.api.system import router as system_router
from archivum.config import Settings, get_settings
from archivum.db import qdrant_client as qdrant
from archivum.db import sqlite
from archivum.db import graph
from archivum.auth import hash_password
from archivum.logging_config import setup_logging
from archivum.observability import new_trace_id, set_trace_id

logger = logging.getLogger(__name__)


class _TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        trace_id = request.headers.get("x-trace-id") or new_trace_id("http")
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response


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

    yield


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(title="Archivum API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(_TraceMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(auth_routes.router)
    app.include_router(pages_routes.router)
    app.include_router(ingest_routes.router)
    app.include_router(search_router)
    app.include_router(query_router)
    app.include_router(graph_router)
    app.include_router(system_router)

    return app


app = create_app()

