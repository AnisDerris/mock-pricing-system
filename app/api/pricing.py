"""Pure pricing logic — no I/O, easy to unit-test."""
from __future__ import annotations

from .config import settings
from .schemas import PriceResponse


def demand_multiplier(open_rides: int, available_drivers: int) -> float:
    """Uber-style: ratio of demand vs supply, smoothed and clamped."""
    if available_drivers <= 0:
        return settings.surge_max if open_rides > 0 else 1.0
    ratio = open_rides / available_drivers
    # 1 ride per driver = neutral; each extra ride per driver adds 0.5x.
    multiplier = 1.0 + max(0.0, (ratio - 1.0)) * 0.5
    return round(min(max(multiplier, settings.surge_min), settings.surge_max), 2)


def quote(
    zone: str,
    distance_km: float,
    duration_min: float,
    demand: float,
    weather: float,
) -> PriceResponse:
    distance_cost = distance_km * settings.per_km
    time_cost = duration_min * settings.per_min
    base = settings.base_fare + distance_cost + time_cost

    surge = min(max(demand * weather, settings.surge_min), settings.surge_max)
    total = round(base * surge, 2)

    return PriceResponse(
        zone=zone,
        base_fare=round(settings.base_fare, 2),
        distance_cost=round(distance_cost, 2),
        time_cost=round(time_cost, 2),
        surge_multiplier=round(surge, 2),
        demand_multiplier=round(demand, 2),
        weather_multiplier=round(weather, 2),
        total=total,
    )
