"""Application configuration (12-factor: env vars only)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Pricing
    base_fare: float = 2.50
    per_km: float = 0.90
    per_min: float = 0.25
    surge_min: float = 1.0
    surge_max: float = 3.0

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    demand_ttl_seconds: int = 300

    # Weather (Open-Meteo, no key required)
    weather_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 1.5

    # Service
    service_name: str = "mock-pricing-api"
    log_level: str = "INFO"


settings = Settings()
