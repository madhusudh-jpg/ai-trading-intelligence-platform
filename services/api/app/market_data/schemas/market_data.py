
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class AssetClass(StrEnum):
    FOREX = "forex"
    CRYPTO = "crypto"
    US_STOCKS = "us_stocks"
    INDICES = "indices"
    NSE_BSE = "nse_bse"


class DataStatus(StrEnum):
    REALTIME = "realtime"
    DELAYED = "delayed"
    STALE = "stale"
    HISTORICAL = "historical"
    UNAVAILABLE = "unavailable"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MN1 = "1mo"


PositivePrice = Annotated[Decimal, Field(gt=0)]
NonNegativeVolume = Annotated[Decimal, Field(ge=0)]


class Candle(BaseModel):
    """Standardized OHLCV candle with strict data validation."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=100)
    asset_class: AssetClass
    timeframe: Timeframe

    open_time: datetime
    close_time: datetime

    open: PositivePrice
    high: PositivePrice
    low: PositivePrice
    close: PositivePrice

    volume: NonNegativeVolume | None = None

    is_complete: bool = True
    provider: str = Field(min_length=1, max_length=50)

    @field_validator("open_time", "close_time")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must be timezone-aware")

        return value.astimezone(UTC)

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def validate_finite_values(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("OHLCV values must be finite")

        return value

    @model_validator(mode="after")
    def validate_candle(self):
        from app.market_data.services.timeframes import (
            is_candle_open_aligned,
            next_candle_open,
        )

        if self.close_time <= self.open_time:
            raise ValueError("close_time must be later than open_time")

        if not is_candle_open_aligned(
            self.open_time,
            self.timeframe,
        ):
            raise ValueError(
                "open_time must align with the candle timeframe"
            )

        expected_close_time = next_candle_open(
            self.open_time,
            self.timeframe,
        )

        if self.close_time != expected_close_time:
            raise ValueError(
                "close_time must equal the next candle opening boundary"
            )

        if self.high < max(self.open, self.close, self.low):
            raise ValueError("Invalid candle high")

        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Invalid candle low")

        return self


class CandleQuery(BaseModel):
    """Parameters for requesting historical market candles."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=100)
    asset_class: AssetClass
    timeframe: Timeframe

    start_time: datetime
    end_time: datetime

    limit: int = Field(default=1000, ge=1, le=100000)

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Query timestamps must be timezone-aware")

        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")

        return self


class ProviderStatus(BaseModel):
    """Connection and data availability information for a provider."""

    provider: str
    configured: bool
    connected: bool = False

    supported_asset_classes: list[AssetClass] = Field(
        default_factory=list
    )

    data_status: DataStatus = DataStatus.UNAVAILABLE
    message: str | None = None
