
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class MarketDataSettings(BaseSettings):
    """Configuration for all market-data providers."""

    market_data_provider: str | None = None
    market_data_api_key: SecretStr | None = None

    # Binance
    binance_enabled: bool = False

    # Twelve Data
    twelve_data_enabled: bool = False
    twelve_data_api_key: SecretStr | None = None
    twelve_data_requests_per_minute: int = 8
    twelve_data_requests_per_day: int = 800

    # Massive
    massive_enabled: bool = False
    massive_api_key: SecretStr | None = None
    massive_requests_per_minute: int = 5

    # Ingestion settings
    historical_backfill_enabled: bool = True
    live_data_enabled: bool = True
    live_ingestion_enabled: bool = False
    preserve_historical_data: bool = True

    # Feed-health monitoring
    feed_health_check_interval_seconds: int = Field(default=10, gt=0)
    feed_delayed_after_seconds: int = Field(default=30, gt=0)
    feed_stale_after_seconds: int = Field(default=60, gt=0)
    feed_message_timeout_seconds: int = Field(default=90, gt=0)

    @model_validator(mode="after")
    def validate_feed_health_thresholds(self):
        if (
            self.feed_stale_after_seconds
            <= self.feed_delayed_after_seconds
        ):
            raise ValueError(
                "Feed stale threshold must exceed delayed threshold."
            )

        if (
            self.feed_message_timeout_seconds
            <= self.feed_stale_after_seconds
        ):
            raise ValueError(
                "Feed message timeout must exceed stale threshold."
            )

        return self

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )


market_data_settings = MarketDataSettings()
