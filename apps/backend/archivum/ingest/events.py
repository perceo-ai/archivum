"""In-memory ingest event hub for live task updates."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

SubscriberQueue = asyncio.Queue[dict[str, Any]]

_subscribers: dict[str, set[SubscriberQueue]] = {}
_lock = asyncio.Lock()


@asynccontextmanager
async def subscribe(wiki_id: str) -> AsyncGenerator[SubscriberQueue, None]:
    queue: SubscriberQueue = asyncio.Queue(maxsize=100)
    async with _lock:
        _subscribers.setdefault(wiki_id, set()).add(queue)

    try:
        yield queue
    finally:
        async with _lock:
            subscribers = _subscribers.get(wiki_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                _subscribers.pop(wiki_id, None)


async def publish(wiki_id: str, event: dict[str, Any]) -> None:
    async with _lock:
        subscribers = list(_subscribers.get(wiki_id, set()))

    if not subscribers:
        return

    payload = dict(event)
    stale: list[SubscriberQueue] = []
    for queue in subscribers:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            stale.append(queue)

    if stale:
        async with _lock:
            current = _subscribers.get(wiki_id)
            if not current:
                return
            for queue in stale:
                current.discard(queue)
            if not current:
                _subscribers.pop(wiki_id, None)
