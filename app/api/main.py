"""FastAPI entrypoint — Food Delivery Dynamic Pricing."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .database import AsyncSessionLocal, create_tables, log_pricing
from .pricing import demand_multiplier as _dm, quote
from .schemas import PriceRequest, PriceResponse, RestaurantState, ZoneState
from .store import get_restaurant_state, get_zone_state
from .weather import weather_multiplier

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)

app = FastAPI(title=settings.service_name, version="1.0.0")
Instrumentator().instrument(app).expose(app)


@app.on_event("startup")
async def startup() -> None:
    await create_tables()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


def _compute_price(req: PriceRequest, weather: float) -> PriceResponse:
    zone = get_zone_state(req.zone_livraison)
    restaurant = get_restaurant_state(req.restaurant_id)
    return quote(
        restaurant_id=req.restaurant_id,
        zone_livraison=req.zone_livraison,
        distance_km=req.distance_km,
        heure=req.heure,
        active_orders=zone["active_orders"],
        available_drivers=zone["available_drivers"],
        load_factor=restaurant["load_factor"],
        prep_time_minutes=restaurant["prep_time_minutes"],
        traffic=zone["traffic_factor"],
        weather=weather,
    )


@app.post("/price", response_model=PriceResponse)
async def price(req: PriceRequest) -> PriceResponse:
    """Prix instantané pour une commande food delivery."""
    weather = await weather_multiplier(req.lat, req.lon)
    result = _compute_price(req, weather)

    async def _audit() -> None:
        try:
            async with AsyncSessionLocal() as session:
                await log_pricing(session, req.model_dump(), result.model_dump())
        except Exception as exc:
            log.warning("audit log failed: %s", exc)

    asyncio.ensure_future(_audit())
    return result


@app.post("/price/stream")
async def price_stream(req: PriceRequest) -> StreamingResponse:
    """SSE : pousse un prix mis à jour toutes les 5 s pendant 60 s.

    Le client reçoit les mises à jour en temps réel sans rechargement de page.
    """
    weather = await weather_multiplier(req.lat, req.lon)

    async def event_generator() -> AsyncIterator[str]:
        for _ in range(12):  # ~60 secondes
            result = _compute_price(req, weather)
            yield f"data: {json.dumps(result.model_dump())}\n\n"
            await asyncio.sleep(5)
        yield 'data: {"stream":"ended"}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/zones/{zone}", response_model=ZoneState)
def zone_state(zone: str) -> ZoneState:
    state = get_zone_state(zone)
    if state["active_orders"] == 0 and state["available_drivers"] == 3:
        # valeurs par défaut = zone inconnue
        raise HTTPException(status_code=404, detail="zone has no recent activity")
    return ZoneState(
        zone=zone,
        active_orders=state["active_orders"],
        available_drivers=state["available_drivers"],
        traffic_factor=state["traffic_factor"],
        demand_multiplier=_dm(state["active_orders"], state["available_drivers"]),
    )


@app.get("/restaurants/{restaurant_id}", response_model=RestaurantState)
def restaurant_state(restaurant_id: str) -> RestaurantState:
    state = get_restaurant_state(restaurant_id)
    return RestaurantState(
        restaurant_id=restaurant_id,
        load_factor=state["load_factor"],
        estimated_prep_minutes=state["prep_time_minutes"],
        is_open=state["is_open"],
    )
