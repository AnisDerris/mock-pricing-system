"""PostgreSQL async client — audit log des prix calculés."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class PricingHistory(Base):
    __tablename__ = "pricing_history"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    restaurant_id = Column(String(120), nullable=False, index=True)
    zone_livraison = Column(String(120), nullable=False, index=True)
    distance_km = Column(Float, nullable=False)
    heure = Column(Float, nullable=False)
    type_commande = Column(String(20), nullable=False)
    base_fare = Column(Float, nullable=False)
    distance_cost = Column(Float, nullable=False)
    prep_time_cost = Column(Float, nullable=False)
    demand_multiplier = Column(Float, nullable=False)
    driver_availability_multiplier = Column(Float, nullable=False)
    restaurant_load_multiplier = Column(Float, nullable=False)
    traffic_multiplier = Column(Float, nullable=False)
    weather_multiplier = Column(Float, nullable=False)
    surge_multiplier = Column(Float, nullable=False)
    total = Column(Float, nullable=False)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("database tables ensured")


_AUDIT_FIELDS = {
    "base_fare", "distance_cost", "prep_time_cost", "demand_multiplier",
    "driver_availability_multiplier", "restaurant_load_multiplier",
    "traffic_multiplier", "weather_multiplier", "surge_multiplier", "total",
}


async def log_pricing(
    session: AsyncSession, req_data: dict, response_data: dict
) -> None:
    record = PricingHistory(
        restaurant_id=req_data["restaurant_id"],
        zone_livraison=req_data["zone_livraison"],
        distance_km=req_data["distance_km"],
        heure=req_data["heure"],
        type_commande=req_data["type_commande"],
        **{k: v for k, v in response_data.items() if k in _AUDIT_FIELDS},
    )
    session.add(record)
    await session.commit()
