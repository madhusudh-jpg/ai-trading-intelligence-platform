
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from app.ict_detection.structure_break_schemas import StructureEventType


class OrderBlockDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class OrderBlockStatus(StrEnum):
    ACTIVE = "active"
    MITIGATED = "mitigated"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


@dataclass(frozen=True)
class OrderBlockDetectionConfig:
    """Configuration for deterministic order block detection."""

    max_origin_lookback_bars: int = 10
    invalidation_buffer: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.max_origin_lookback_bars < 1:
            raise ValueError("max_origin_lookback_bars must be at least 1.")

        if not self.invalidation_buffer.is_finite():
            raise ValueError("invalidation_buffer must be finite.")

        if self.invalidation_buffer < 0:
            raise ValueError("invalidation_buffer cannot be negative.")


class OrderBlock(BaseModel):
    """A confirmed bullish or bearish order block."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: str
    timeframe: str
    provider: str

    direction: OrderBlockDirection

    origin_candle_index: int
    segment_id: int
    origin_open_time: datetime
    origin_close_time: datetime

    lower_bound: Decimal
    upper_bound: Decimal

    displacement_candle_index: int
    displacement_open_time: datetime
    displacement_confirmed_at: datetime

    structure_break_type: StructureEventType
    broken_level: Decimal
    structure_break_open_time: datetime
    structure_break_confirmed_at: datetime

    confirmed_at: datetime

    status: OrderBlockStatus = OrderBlockStatus.ACTIVE
    mitigated_at: datetime | None = None
    invalidated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_order_block(self) -> "OrderBlock":
        timestamps = (
            self.origin_open_time,
            self.origin_close_time,
            self.displacement_open_time,
            self.displacement_confirmed_at,
            self.structure_break_open_time,
            self.structure_break_confirmed_at,
            self.confirmed_at,
        )

        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None
            for timestamp in timestamps
        ):
            raise ValueError("All order block timestamps must be timezone-aware.")

        if self.origin_candle_index < 0:
            raise ValueError("origin_candle_index cannot be negative.")

        if self.displacement_candle_index <= self.origin_candle_index:
            raise ValueError("Displacement must follow the origin candle.")

        if self.segment_id < 0:
            raise ValueError("segment_id cannot be negative.")

        if self.origin_close_time <= self.origin_open_time:
            raise ValueError("Origin candle close must follow its open.")

        if self.lower_bound <= 0 or self.upper_bound <= 0:
            raise ValueError("Order block prices must be positive.")

        if self.lower_bound >= self.upper_bound:
            raise ValueError("lower_bound must be below upper_bound.")

        if self.broken_level <= 0:
            raise ValueError("broken_level must be positive.")

        if self.displacement_open_time < self.origin_close_time:
            raise ValueError("Displacement must occur after the origin candle.")

        if self.structure_break_open_time != self.displacement_open_time:
            raise ValueError(
                "Structure break and qualifying displacement must use the same candle."
            )

        if self.structure_break_confirmed_at != self.displacement_confirmed_at:
            raise ValueError(
                "Structure break and displacement confirmation times must match."
            )

        if self.confirmed_at != self.structure_break_confirmed_at:
            raise ValueError(
                "Order block confirmation must match structural break confirmation."
            )

        if self.mitigated_at is not None:
            if (
                self.mitigated_at.tzinfo is None
                or self.mitigated_at.utcoffset() is None
            ):
                raise ValueError("mitigated_at must be timezone-aware.")

            if self.mitigated_at < self.confirmed_at:
                raise ValueError(
                    "Mitigation cannot precede order block confirmation."
                )

        if self.invalidated_at is not None:
            if (
                self.invalidated_at.tzinfo is None
                or self.invalidated_at.utcoffset() is None
            ):
                raise ValueError("invalidated_at must be timezone-aware.")

            if self.invalidated_at < self.confirmed_at:
                raise ValueError(
                    "Invalidation cannot precede order block confirmation."
                )

        return self


__all__ = [
    "OrderBlock",
    "OrderBlockDetectionConfig",
    "OrderBlockDirection",
    "OrderBlockStatus",
]
