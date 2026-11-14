from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.market_data.schemas.market_data import AssetClass, Timeframe


class DisplacementDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True, slots=True)
class DisplacementDetectionConfig:
    """Configurable single-candle displacement thresholds."""

    atr_period: int = 20
    min_body_ratio: Decimal = Decimal("0.65")
    min_range_expansion_atr: Decimal = Decimal("1.20")
    min_directional_close_location: Decimal = Decimal("0.80")
    max_opposing_wick_ratio: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        if type(self.atr_period) is not int or self.atr_period < 1:
            raise ValueError("atr_period must be a positive integer")

        fields = (
            "min_body_ratio",
            "min_range_expansion_atr",
            "min_directional_close_location",
            "max_opposing_wick_ratio",
        )

        for name in fields:
            try:
                value = Decimal(str(getattr(self, name)))
            except Exception as exc:
                raise ValueError(f"{name} must be a valid decimal") from exc

            if not value.is_finite():
                raise ValueError(f"{name} must be finite")

            object.__setattr__(self, name, value)

        if not Decimal("0") < self.min_body_ratio <= Decimal("1"):
            raise ValueError("min_body_ratio must be in (0, 1]")

        if self.min_range_expansion_atr <= 0:
            raise ValueError("min_range_expansion_atr must be positive")

        if not (Decimal("0") < self.min_directional_close_location <= Decimal("1")):
            raise ValueError("min_directional_close_location must be in (0, 1]")

        if not Decimal("0") <= self.max_opposing_wick_ratio <= Decimal("1"):
            raise ValueError("max_opposing_wick_ratio must be between 0 and 1")


class DisplacementEvent(BaseModel):
    """A completed candle satisfying displacement criteria."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    direction: DisplacementDirection

    candle_index: int = Field(ge=0)
    segment_id: int = Field(ge=0)

    open_time: datetime
    close_time: datetime
    confirmed_at: datetime

    open_price: Decimal = Field(gt=0)
    close_price: Decimal = Field(gt=0)
    high_price: Decimal = Field(gt=0)
    low_price: Decimal = Field(gt=0)

    true_range: Decimal = Field(gt=0)
    atr_value: Decimal = Field(gt=0)

    body_ratio: Decimal = Field(ge=0, le=1)
    range_expansion_atr: Decimal = Field(gt=0)
    directional_close_location: Decimal = Field(ge=0, le=1)
    opposing_wick_ratio: Decimal = Field(ge=0, le=1)

    @field_validator("open_time", "close_time", "confirmed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Displacement timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_event(self):
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be later than open_time")

        if self.confirmed_at != self.close_time:
            raise ValueError("A single-candle event is confirmed at candle close.")

        if self.high_price < max(self.open_price, self.close_price):
            raise ValueError("Invalid displacement high")

        if self.low_price > min(self.open_price, self.close_price):
            raise ValueError("Invalid displacement low")

        if self.direction == DisplacementDirection.BULLISH:
            if self.close_price <= self.open_price:
                raise ValueError("Bullish displacement must close above its open.")
        elif self.close_price >= self.open_price:
            raise ValueError("Bearish displacement must close below its open.")

        return self


__all__ = [
    "DisplacementDetectionConfig",
    "DisplacementDirection",
    "DisplacementEvent",
]
