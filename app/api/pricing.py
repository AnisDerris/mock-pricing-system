"""Pure pricing logic — food delivery. No I/O, easy to unit-test."""
from __future__ import annotations

from .config import settings
from .schemas import PriceResponse


def demand_multiplier(active_orders: int, available_drivers: int) -> float:
    """Ratio commandes/livreurs → pression de demande."""
    if available_drivers <= 0:
        return settings.surge_max if active_orders > 0 else 1.0
    ratio = active_orders / available_drivers
    multiplier = 1.0 + max(0.0, (ratio - 1.0)) * 0.4
    return round(min(max(multiplier, settings.surge_min), settings.surge_max), 2)


def driver_availability_multiplier(available_drivers: int) -> float:
    """Rareté absolue des livreurs → risque de délai → prix ↑."""
    if available_drivers <= 0:
        return 1.5
    if available_drivers <= 2:
        return 1.3
    if available_drivers <= 5:
        return 1.15
    return 1.0


def restaurant_load_multiplier(load_factor: float) -> float:
    """Cuisine surchargée → temps d'attente → coût caché capturé dans le prix.

    load_factor : 0.0 (idle) → 1.0 (à pleine capacité)
    """
    load = max(0.0, min(load_factor, 1.0))
    return round(1.0 + load * 0.4, 2)


def traffic_multiplier(traffic_factor: float) -> float:
    """Conditions routières. 1.0=fluide, 2.0=embouteillages."""
    factor = max(1.0, min(traffic_factor, 2.0))
    return round(1.0 + (factor - 1.0) * 0.3, 2)


def hour_multiplier(heure: float) -> float:
    """Surcharge heure de pointe : déjeuner (12-14h) et dîner (19-22h)."""
    h = heure % 24
    if 12.0 <= h < 14.0 or 19.0 <= h < 22.0:
        return 1.2
    if h >= 22.0 or h < 6.0:  # tard la nuit
        return 1.15
    return 1.0


def quote(
    restaurant_id: str,
    zone_livraison: str,
    distance_km: float,
    heure: float,
    active_orders: int,
    available_drivers: int,
    load_factor: float,
    prep_time_minutes: float,
    traffic: float,
    weather: float,
) -> PriceResponse:
    # Coûts de base
    distance_cost = round(distance_km * settings.per_km, 2)
    prep_cost = round(prep_time_minutes * settings.per_min_prep, 2)
    base = settings.base_fare + distance_cost + prep_cost

    # Multiplicateurs individuels
    d_mult = demand_multiplier(active_orders, available_drivers)
    drv_mult = driver_availability_multiplier(available_drivers)
    rest_mult = restaurant_load_multiplier(load_factor)
    traf_mult = traffic_multiplier(traffic)
    h_mult = hour_multiplier(heure)

    # Surge combiné = produit de tous les facteurs, plafonné
    surge = d_mult * drv_mult * rest_mult * traf_mult * weather * h_mult
    surge = round(min(max(surge, settings.surge_min), settings.surge_max), 2)

    total = round(base * surge, 2)

    # Estimations de temps
    est_prep = round(prep_time_minutes * (1 + load_factor * 0.5), 1)
    est_delivery = round((distance_km / 25.0) * 60 * traffic, 1)  # 25 km/h vitesse de base

    return PriceResponse(
        restaurant_id=restaurant_id,
        zone_livraison=zone_livraison,
        base_fare=round(settings.base_fare, 2),
        distance_cost=distance_cost,
        prep_time_cost=prep_cost,
        demand_multiplier=round(d_mult, 2),
        driver_availability_multiplier=round(drv_mult, 2),
        restaurant_load_multiplier=round(rest_mult, 2),
        traffic_multiplier=round(traf_mult, 2),
        weather_multiplier=round(weather, 2),
        surge_multiplier=surge,
        estimated_prep_minutes=est_prep,
        estimated_delivery_minutes=est_delivery,
        total=total,
    )
