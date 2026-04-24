"""Weather multiplier using the free Open-Meteo API (no key required)."""
from __future__ import annotations

import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


async def weather_multiplier(lat: float | None, lon: float | None) -> float:
    """Return surge bump based on current weather. Fail-open to 1.0."""
    if lat is None or lon is None:
        return 1.0
    params = {"latitude": lat, "longitude": lon, "current": "precipitation,weather_code"}
    try:
        async with httpx.AsyncClient(timeout=settings.weather_timeout_seconds) as c:
            r = await c.get(settings.weather_url, params=params)
            r.raise_for_status()
            current = r.json().get("current", {})
    except Exception as exc:  # network, timeout, 5xx -> degrade gracefully
        log.warning("weather lookup failed: %s", exc)
        return 1.0

    precipitation = float(current.get("precipitation", 0) or 0)
    code = int(current.get("weather_code", 0) or 0)

    # Open-Meteo WMO codes: 71-77 snow, 95-99 thunderstorm
    if code >= 95:
        return 1.4
    if 71 <= code <= 77:
        return 1.3
    if precipitation >= 2.5:
        return 1.2
    if precipitation > 0:
        return 1.1
    return 1.0
