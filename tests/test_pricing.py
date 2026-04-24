from app.api.pricing import demand_multiplier, quote


def test_demand_neutral_when_supply_meets_demand():
    assert demand_multiplier(open_rides=5, available_drivers=5) == 1.0


def test_demand_grows_with_scarcity():
    low = demand_multiplier(open_rides=10, available_drivers=5)
    high = demand_multiplier(open_rides=20, available_drivers=5)
    assert 1.0 < low < high <= 3.0


def test_demand_caps_at_max_when_no_drivers():
    assert demand_multiplier(open_rides=5, available_drivers=0) == 3.0


def test_demand_idle_zone_is_neutral():
    assert demand_multiplier(open_rides=0, available_drivers=0) == 1.0


def test_quote_breakdown_sums_correctly():
    q = quote("z", distance_km=10, duration_min=20, demand=1.0, weather=1.0)
    assert q.distance_cost == 9.0
    assert q.time_cost == 5.0
    assert q.total == round((2.5 + 9.0 + 5.0) * 1.0, 2)


def test_surge_is_clamped():
    q = quote("z", distance_km=10, duration_min=20, demand=5.0, weather=2.0)
    assert q.surge_multiplier == 3.0
