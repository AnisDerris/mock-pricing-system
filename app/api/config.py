"""Application configuration (12-factor: env vars only)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Pricing — food delivery
    base_fare: float = 1.50           # lower base than VTC
    per_km: float = 0.75
    per_min_prep: float = 0.10        # cost per minute of restaurant prep time
    surge_min: float = 1.0
    surge_max: float = 2.5            # softer cap vs VTC

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    demand_ttl_seconds: int = 300

    # Kafka
    kafka_bootstrap: str = "kafka:9092"

    # PostgreSQL (audit log)
    database_url: str = "postgresql+asyncpg://pricing:pricing@postgres:5432/foodpricing"

    # Weather (Open-Meteo, no key required)
    weather_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 1.5

    # Service
    service_name: str = "food-pricing-api"
    log_level: str = "INFO"


settings = Settings()
