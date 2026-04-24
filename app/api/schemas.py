"""Pydantic request/response models."""
from pydantic import BaseModel, Field


class PriceRequest(BaseModel):
    zone: str = Field(..., examples=["casa-center"])
    distance_km: float = Field(..., gt=0, le=500)
    duration_min: float = Field(..., gt=0, le=600)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class PriceResponse(BaseModel):
    zone: str
    base_fare: float
    distance_cost: float
    time_cost: float
    surge_multiplier: float
    demand_multiplier: float
    weather_multiplier: float
    total: float
    currency: str = "USD"


class ZoneState(BaseModel):
    zone: str
    open_rides: int
    available_drivers: int
    demand_multiplier: float
