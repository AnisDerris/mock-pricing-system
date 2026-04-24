"""FastAPI entrypoint for the mock pricing service."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .pricing import demand_multiplier, quote
from .schemas import PriceRequest, PriceResponse, ZoneState
from .store import get_counts
from .weather import weather_multiplier

logging.basicConfig(level=settings.log_level)

app = FastAPI(title=settings.service_name, version="0.1.0")
Instrumentator().instrument(app).expose(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/price", response_model=PriceResponse)
async def price(req: PriceRequest) -> PriceResponse:
    rides, drivers = get_counts(req.zone)
    demand = demand_multiplier(rides, drivers)
    weather = await weather_multiplier(req.lat, req.lon)
    return quote(req.zone, req.distance_km, req.duration_min, demand, weather)


@app.get("/zones/{zone}", response_model=ZoneState)
def zone_state(zone: str) -> ZoneState:
    rides, drivers = get_counts(zone)
    if rides == 0 and drivers == 0:
        raise HTTPException(status_code=404, detail="zone has no recent activity")
    return ZoneState(
        zone=zone,
        open_rides=rides,
        available_drivers=drivers,
        demand_multiplier=demand_multiplier(rides, drivers),
    )
