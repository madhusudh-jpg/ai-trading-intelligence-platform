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


class SwingType(StrEnum):
    HIGH = "high"
    LOW = "low"


class SwingTier(StrEnum):
    SHORT_TERM = "short_term"
    INTERMEDIATE_TERM = "intermediate_term"
    LONG_TERM = "long_term"


class SwingConfirmationBasis(StrEnum):
    FRACTAL = "fractal"
    NESTED_HIERARCHY = "nested_hierarchy"


@dataclass(frozen=True, slots=True)
class SwingDetectionConfig:
    """Configuration for confirmed swing detection."""

    left_bars: int = 2
    right_bars: int = 2
    include_hierarchy: bool = True

    def __post_init__(self) -> None:
        if type(self.left_bars) is not int or self.left_bars < 1:
            raise ValueError("left_bars must be a positive integer")

        if type(self.right_bars) is not int or self.right_bars < 1:
            raise ValueError("right_bars must be a positive integer")

        if type(self.include_hierarchy) is not bool:
            raise ValueError("include_hierarchy must be a boolean")


class SwingPoint(BaseModel):
    """A confirmed price swing with its detection evidence."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=100)
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str = Field(min_length=1, max_length=50)

    swing_type: SwingType
    tier: SwingTier

    price: Decimal = Field(gt=0)

    pivot_time: datetime
    confirmed_at: datetime

    pivot_index: int = Field(ge=0)
    segment_id: int = Field(ge=0)

    left_bars: int = Field(ge=1)
    right_bars: int = Field(ge=1)

    hierarchy_left_points: int = Field(default=0, ge=0)
    hierarchy_right_points: int = Field(default=0, ge=0)

    confirmation_basis: SwingConfirmationBasis

    @field_validator("pivot_time", "confirmed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Swing timestamps must be timezone-aware")

        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.confirmed_at <= self.pivot_time:
            raise ValueError("confirmed_at must be later than pivot_time")

        return self


__all__ = [
    "SwingConfirmationBasis",
    "SwingDetectionConfig",
    "SwingPoint",
    "SwingTier",
    "SwingType",
]
