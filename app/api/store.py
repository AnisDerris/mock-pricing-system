"""Thin Redis wrapper for zone demand state."""
from __future__ import annotations

import redis

from .config import settings


_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def _key(zone: str, kind: str) -> str:
    return f"zone:{zone}:{kind}"


def incr_signal(zone: str, kind: str, amount: int = 1) -> int:
    """Increment ride/driver counter for a zone (TTL-bounded sliding window)."""
    k = _key(zone, kind)
    pipe = client().pipeline()
    pipe.incrby(k, amount)
    pipe.expire(k, settings.demand_ttl_seconds)
    new_value, _ = pipe.execute()
    return int(new_value)


def get_counts(zone: str) -> tuple[int, int]:
    rides = int(client().get(_key(zone, "rides")) or 0)
    drivers = int(client().get(_key(zone, "drivers")) or 0)
    return rides, drivers
