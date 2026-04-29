from __future__ import annotations

import logging
import os
import sys
from typing import Any

from archivum.observability import get_trace_id

_SAFE_EXTRA_PATCHED = False


def _logrecord_reserved_keys() -> set[str]:
    """
    Reserved keys in `logging.LogRecord` that cannot be overridden via `extra=`.
    """
    record = logging.LogRecord(
        name="archivum",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="",
        args=(),
        exc_info=None,
    )
    # 'message' and 'asctime' are derived by Formatter but still considered reserved.
    return set(record.__dict__.keys()) | {"message", "asctime"}


_RESERVED_LOGRECORD_KEYS = _logrecord_reserved_keys()


def _install_safe_extra_patch() -> None:
    """
    Prevent stdlib logging from raising `KeyError` when `extra` includes a reserved
    `LogRecord` attribute (e.g. `created`, `message`, `levelname`).

    Instead of crashing, we auto-rename colliding keys by prefixing them with `ctx_`.
    """
    global _SAFE_EXTRA_PATCHED
    if _SAFE_EXTRA_PATCHED:
        return

    original_make_record = logging.Logger.makeRecord

    def makeRecord(  # type: ignore[override]
        self: logging.Logger,
        name: str,
        level: int,
        fn: str,
        lno: int,
        msg: object,
        args: object,
        exc_info: object,
        func: str | None = None,
        extra: dict[str, Any] | None = None,
        sinfo: str | None = None,
    ) -> logging.LogRecord:
        if extra:
            safe: dict[str, Any] = {}
            for k, v in extra.items():
                safe[f"ctx_{k}" if k in _RESERVED_LOGRECORD_KEYS else k] = v
            extra = safe
        return original_make_record(self, name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)

    logging.Logger.makeRecord = makeRecord  # type: ignore[assignment]
    _SAFE_EXTRA_PATCHED = True


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - part of stdlib API
        record.trace_id = get_trace_id()  # type: ignore[attr-defined]
        return True


def _level_from_env(default: str = "INFO") -> int:
    raw = (os.getenv("LOG_LEVEL") or default).strip().upper()
    return getattr(logging, raw, logging.INFO)


def setup_logging(*, level: int | None = None) -> None:
    """
    Configure stdlib logging for all Archivum processes.

    Environment:
      - LOG_LEVEL: DEBUG|INFO|WARNING|ERROR (default INFO)
    """
    _install_safe_extra_patch()
    resolved_level = level if level is not None else _level_from_env()

    root = logging.getLogger()
    root.setLevel(resolved_level)

    fmt = (
        "%(asctime)s.%(msecs)03d "
        "%(levelname)s "
        "[%(process)d] "
        "trace=%(trace_id)s "
        "%(name)s: %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(resolved_level)
    handler.addFilter(_TraceIdFilter())
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    root.handlers.clear()
    root.addHandler(handler)

    # Reduce noise from chatty deps unless LOG_LEVEL=DEBUG.
    if resolved_level > logging.DEBUG:
        for noisy in ("httpx", "qdrant_client", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def log_extra(**fields: Any) -> dict[str, Any]:
    """
    Convenience helper so we consistently attach structured fields.
    """
    return {"extra": fields}

