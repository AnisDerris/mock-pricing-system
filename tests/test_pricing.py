"""Tests mock du moteur de pricing food delivery — aucune dépendance externe."""
from app.api.config import settings
from app.api.pricing import (
    demand_multiplier,
    driver_availability_multiplier,
    hour_multiplier,
    quote,
    restaurant_load_multiplier,
    traffic_multiplier,
)


# ── Demand multiplier ──────────────────────────────────────────────────────

def test_demand_neutral_when_balanced():
    assert demand_multiplier(active_orders=5, available_drivers=5) == 1.0


def test_demand_grows_with_scarcity():
    low = demand_multiplier(active_orders=10, available_drivers=5)
    high = demand_multiplier(active_orders=20, available_drivers=5)
    assert 1.0 < low < high <= settings.surge_max


def test_demand_caps_at_max_when_no_drivers():
    assert demand_multiplier(active_orders=10, available_drivers=0) == settings.surge_max


def test_demand_idle_zone_is_neutral():
    assert demand_multiplier(active_orders=0, available_drivers=0) == 1.0


# ── Driver availability ─────────────────────────────────────────────────────

def test_driver_availability_no_drivers():
    assert driver_availability_multiplier(0) == 1.5


def test_driver_availability_very_scarce():
    assert driver_availability_multiplier(2) == 1.3


def test_driver_availability_scarce():
    assert driver_availability_multiplier(4) == 1.15


def test_driver_availability_normal():
    assert driver_availability_multiplier(10) == 1.0


# ── Restaurant load ─────────────────────────────────────────────────────────

def test_restaurant_load_idle():
    assert restaurant_load_multiplier(0.0) == 1.0


def test_restaurant_load_half():
    assert restaurant_load_multiplier(0.5) == 1.2


def test_restaurant_load_full():
    assert restaurant_load_multiplier(1.0) == 1.4


def test_restaurant_load_clamped_above():
    assert restaurant_load_multiplier(1.5) == restaurant_load_multiplier(1.0)


def test_restaurant_load_clamped_below():
    assert restaurant_load_multiplier(-0.5) == restaurant_load_multiplier(0.0)


# ── Traffic multiplier ──────────────────────────────────────────────────────

def test_traffic_clear():
    assert traffic_multiplier(1.0) == 1.0


def test_traffic_heavy():
    assert traffic_multiplier(2.0) == 1.3


def test_traffic_clamped():
    assert traffic_multiplier(3.0) == traffic_multiplier(2.0)


# ── Hour multiplier ─────────────────────────────────────────────────────────

def test_hour_lunch_peak():
    assert hour_multiplier(12.5) == 1.2


def test_hour_dinner_peak():
    assert hour_multiplier(20.0) == 1.2


def test_hour_late_night():
    assert hour_multiplier(23.5) == 1.15


def test_hour_offpeak():
    assert hour_multiplier(10.0) == 1.0


# ── Full quote ──────────────────────────────────────────────────────────────

def test_quote_cost_breakdown():
    q = quote(
        restaurant_id="test-rest",
        zone_livraison="test-zone",
        distance_km=5.0,
        heure=10.0,   # off-peak
        active_orders=3,
        available_drivers=5,
        load_factor=0.0,
        prep_time_minutes=15.0,
        traffic=1.0,
        weather=1.0,
    )
    assert q.distance_cost == round(5.0 * settings.per_km, 2)
    assert q.prep_time_cost == round(15.0 * settings.per_min_prep, 2)
    assert q.surge_multiplier >= settings.surge_min
    assert q.total > 0


def test_quote_surge_never_exceeds_max():
    """Sous des conditions extrêmes le surge doit être plafonné."""
    q = quote(
        restaurant_id="test-rest",
        zone_livraison="test-zone",
        distance_km=10.0,
        heure=20.0,         # dinner peak
        active_orders=100,
        available_drivers=0,
        load_factor=1.0,
        prep_time_minutes=40.0,
        traffic=2.0,
        weather=1.4,
    )
    assert q.surge_multiplier == settings.surge_max


def test_quote_estimated_times_are_positive():
    q = quote(
        restaurant_id="test-rest",
        zone_livraison="test-zone",
        distance_km=3.0,
        heure=14.0,
        active_orders=5,
        available_drivers=3,
        load_factor=0.5,
        prep_time_minutes=20.0,
        traffic=1.2,
        weather=1.0,
    )
    assert q.estimated_prep_minutes > 0
    assert q.estimated_delivery_minutes > 0


def test_quote_restaurant_id_preserved():
    q = quote(
        restaurant_id="mcdo-casa-center",
        zone_livraison="casa-center",
        distance_km=2.0,
        heure=9.0,
        active_orders=2,
        available_drivers=4,
        load_factor=0.2,
        prep_time_minutes=10.0,
        traffic=1.0,
        weather=1.0,
    )
    assert q.restaurant_id == "mcdo-casa-center"
    assert q.zone_livraison == "casa-center"

