"""In-process pub/sub for server-sent events. The worker writes to the DB; the
API process polls the audit table, so this bus is only for same-process
listeners and is best-effort."""

import asyncio
from typing import Any

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(event: dict[str, Any]) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except (asyncio.QueueFull, RuntimeError):
            pass
