
from pydantic import BaseModel, ConfigDict, Field

from app.market_data.schemas.market_data import (
    AssetClass,
    DataStatus,
    Timeframe,
)


class ProviderCapabilities(BaseModel):
    """Describes the verified capabilities of a market-data provider."""

    model_config = ConfigDict(frozen=True)

    provider_name: str

    supported_asset_classes: list[AssetClass] = Field(
        default_factory=list
    )

    supported_timeframes: list[Timeframe] = Field(
        default_factory=list
    )

    historical_data: bool = False
    live_streaming: bool = False
    delayed_data: bool = False
    end_of_day_data: bool = False

    data_status: DataStatus = DataStatus.UNAVAILABLE

    max_requests_per_minute: int | None = Field(
        default=None,
        ge=1,
    )

    max_requests_per_day: int | None = Field(
        default=None,
        ge=1,
    )

    requires_api_key: bool = True

    notes: str | None = None
