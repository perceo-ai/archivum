from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator


trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    trace_id_var.set(trace_id)


def new_trace_id(prefix: str | None = None) -> str:
    base = uuid.uuid4().hex[:12]
    return f"{prefix}-{base}" if prefix else base


@contextmanager
def span(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """
    Lightweight timing span.

    Usage:
        with span("qdrant.upsert", slug=slug) as s:
            ...
        logger.info("done", extra=s)
    """
    started = time.perf_counter()
    data: dict[str, Any] = {"span": name, **fields}
    try:
        yield data
    finally:
        data["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)

