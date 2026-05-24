"""Redis wrapper pour l'état temps réel du food delivery."""
from __future__ import annotations

import redis

from .config import settings

_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


# ── État de zone (commandes + livreurs + trafic) ────────────────────────────

def get_zone_state(zone: str) -> dict:
    r = client()
    return {
        "active_orders": int(r.get(f"zone:{zone}:orders") or 0),
        "available_drivers": int(r.get(f"zone:{zone}:drivers") or 3),
        "traffic_factor": float(r.get(f"zone:{zone}:traffic") or 1.0),
    }


# ── État restaurant ──────────────────────────────────────────────────────────

def get_restaurant_state(restaurant_id: str) -> dict:
    r = client()
    return {
        "load_factor": float(r.get(f"restaurant:{restaurant_id}:load") or 0.3),
        "prep_time_minutes": float(r.get(f"restaurant:{restaurant_id}:prep_time") or 15.0),
        "is_open": (r.get(f"restaurant:{restaurant_id}:open") or "1") == "1",
    }


# ── Écriture (appelée par les consumers) ────────────────────────────────────

def update_zone_orders(zone: str, delta: int, ttl: int | None = None) -> None:
    ttl = ttl or settings.demand_ttl_seconds
    key = f"zone:{zone}:orders"
    pipe = client().pipeline()
    pipe.incrby(key, delta)
    pipe.expire(key, ttl)
    val, _ = pipe.execute()
    if int(val) < 0:
        client().set(key, 0, ex=ttl)


def update_zone_drivers(zone: str, delta: int, ttl: int | None = None) -> None:
    ttl = ttl or settings.demand_ttl_seconds
    key = f"zone:{zone}:drivers"
    pipe = client().pipeline()
    pipe.incrby(key, delta)
    pipe.expire(key, ttl)
    val, _ = pipe.execute()
    if int(val) < 0:
        client().set(key, 0, ex=ttl)


def set_traffic(zone: str, traffic_factor: float, ttl: int = 120) -> None:
    client().set(f"zone:{zone}:traffic", round(traffic_factor, 3), ex=ttl)


def set_restaurant_load(
    restaurant_id: str, load_factor: float, prep_time: float, ttl: int = 180
) -> None:
    r = client()
    r.set(f"restaurant:{restaurant_id}:load", round(load_factor, 3), ex=ttl)
    r.set(f"restaurant:{restaurant_id}:prep_time", round(prep_time, 1), ex=ttl)


def set_restaurant_status(restaurant_id: str, is_open: bool, ttl: int = 300) -> None:
    client().set(
        f"restaurant:{restaurant_id}:open", "1" if is_open else "0", ex=ttl
    )
