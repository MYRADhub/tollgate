"""The company clock. Real time plus an offset that the demo can move forward,
so a visitor can watch a day of follow-ups, replies and deliveries in seconds.

Every timestamp, every job's due time and every "today" comes from here. The
offset lives in the database so the API and the worker agree on the time; each
process caches it for a second."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

_cache: tuple[float, int] = (0.0, 0)  # (monotonic fetched at, offset seconds)
TTL_S = 1.0


def _read() -> int:
    from sqlalchemy import text

    from . import db

    try:
        with db.engine.connect() as c:
            row = c.execute(text("SELECT offset_s FROM demo_clock WHERE id = 1")).first()
        return int(row[0]) if row else 0
    except Exception:
        return 0  # table not created yet


def offset_s() -> int:
    global _cache
    at, val = _cache
    if time.monotonic() - at > TTL_S:
        val = _read()
        _cache = (time.monotonic(), val)
    return val


def now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_s())


def aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; everything here is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def today() -> date:
    return now().date()


def _set(s, seconds: int) -> None:
    from .models import DemoClock

    global _cache
    row = s.get(DemoClock, 1)
    if row is None:
        row = DemoClock(id=1, offset_s=seconds)
        s.add(row)
    else:
        row.offset_s = seconds
    s.flush()
    _cache = (time.monotonic(), seconds)


def advance(s, hours: float, max_days: float) -> int:
    """Move the clock forward. Returns the new offset in seconds."""
    current = _read()
    target = min(current + int(hours * 3600), int(max_days * 86400))
    if target <= current:
        raise ValueError(f"the demo clock is already {max_days:g} days ahead; reset the demo to start over")
    _set(s, target)
    return target


def reset(s) -> None:
    _set(s, 0)


def forget() -> None:
    """Drop the cached offset (tests, and after a reset in another process)."""
    global _cache
    _cache = (0.0, 0)
