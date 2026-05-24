"""Pydantic request/response models — Food Delivery Pricing."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class OrderType(str, Enum):
    delivery = "delivery"
    pickup = "pickup"


class PriceRequest(BaseModel):
    restaurant_id: str = Field(..., examples=["mcdo-casa-center"])
    zone_livraison: str = Field(..., examples=["casa-center"])
    adresse: str = Field(..., examples=["23 Rue Mohammed V, Casablanca"])
    distance_km: float = Field(..., gt=0, le=50, description="Distance en km")
    heure: float = Field(..., ge=0, lt=24, description="Heure de la commande (0-23.99)")
    type_commande: OrderType = Field(OrderType.delivery)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class PriceResponse(BaseModel):
    restaurant_id: str
    zone_livraison: str
    base_fare: float
    distance_cost: float
    prep_time_cost: float
    demand_multiplier: float
    driver_availability_multiplier: float
    restaurant_load_multiplier: float
    traffic_multiplier: float
    weather_multiplier: float
    surge_multiplier: float           # multiplicateur final combiné
    estimated_prep_minutes: float
    estimated_delivery_minutes: float
    total: float
    currency: str = "MAD"


class ZoneState(BaseModel):
    zone: str
    active_orders: int
    available_drivers: int
    traffic_factor: float
    demand_multiplier: float


class RestaurantState(BaseModel):
    restaurant_id: str
    load_factor: float                # 0.0 = idle, 1.0 = at capacity
    estimated_prep_minutes: float
    is_open: bool
