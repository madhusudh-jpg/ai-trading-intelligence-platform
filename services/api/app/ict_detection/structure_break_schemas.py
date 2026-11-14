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

from app.ict_detection.market_structure_schemas import (
    MarketTrend,
    StructureScope,
)
from app.ict_detection.schemas import SwingTier, SwingType
from app.market_data.schemas.market_data import AssetClass, Timeframe


class StructureBreakProfile(StrEnum):
    STANDARD = "standard"
    STRICT_ICT_2022 = "strict_ict_2022"


class StructureEventType(StrEnum):
    BOS = "bos"
    CHOCH = "choch"
    MSS = "mss"
    UNCLASSIFIED_BREAK = "unclassified_break"


class BreakDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class LiquiditySide(StrEnum):
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"


@dataclass(frozen=True, slots=True)
class StructureBreakConfig:
    """Configuration for structural break confirmation."""

    profile: StructureBreakProfile = StructureBreakProfile.STANDARD
    break_buffer: Decimal = Decimal("0")
    structure_tolerance: Decimal = Decimal("0")
    max_sweep_age_bars: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.profile, StructureBreakProfile):
            object.__setattr__(
                self,
                "profile",
                StructureBreakProfile(self.profile),
            )

        for name in ("break_buffer", "structure_tolerance"):
            try:
                value = Decimal(str(getattr(self, name)))
            except Exception as exc:
                raise ValueError(f"{name} must be a valid decimal") from exc

            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")

            object.__setattr__(self, name, value)

        if type(self.max_sweep_age_bars) is not int or self.max_sweep_age_bars < 1:
            raise ValueError("max_sweep_age_bars must be a positive integer")


class LiquiditySweepEvidence(BaseModel):
    """Input contract for confirmed liquidity sweep evidence."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    liquidity_side: LiquiditySide
    segment_id: int = Field(ge=0)

    pool_price: Decimal = Field(gt=0)
    swept_price: Decimal = Field(gt=0)

    sweep_time: datetime
    confirmed_at: datetime

    @field_validator("sweep_time", "confirmed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Sweep timestamps must be timezone-aware")

        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_sweep(self):
        if self.confirmed_at <= self.sweep_time:
            raise ValueError("Sweep confirmation must follow its sweep candle.")

        if self.liquidity_side == LiquiditySide.BUY_SIDE:
            if self.swept_price <= self.pool_price:
                raise ValueError("A buy-side sweep must trade above its pool.")
        elif self.swept_price >= self.pool_price:
            raise ValueError("A sell-side sweep must trade below its pool.")

        return self


class StructureBreakEvent(BaseModel):
    """A confirmed BOS, CHoCH, MSS or unclassified break."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    event_type: StructureEventType
    direction: BreakDirection
    scope: StructureScope
    profile: StructureBreakProfile

    broken_swing_type: SwingType
    broken_swing_tier: SwingTier

    broken_level: Decimal = Field(gt=0)
    pivot_time: datetime
    pivot_confirmed_at: datetime

    break_open_time: datetime
    break_close_time: datetime
    confirmed_at: datetime

    break_close: Decimal = Field(gt=0)
    break_buffer: Decimal = Field(ge=0)

    prior_trend: MarketTrend

    displacement_confirmed: bool

    liquidity_sweep_preceded: bool = False
    liquidity_side: LiquiditySide | None = None
    liquidity_sweep_time: datetime | None = None

    @field_validator(
        "pivot_time",
        "pivot_confirmed_at",
        "break_open_time",
        "break_close_time",
        "confirmed_at",
        "liquidity_sweep_time",
    )
    @classmethod
    def normalize_timestamp(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Event timestamps must be timezone-aware")

        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_event(self):
        if self.pivot_confirmed_at <= self.pivot_time:
            raise ValueError("The swing must be confirmed after its pivot.")

        if self.break_close_time <= self.break_open_time:
            raise ValueError("Break candle close must follow its open.")

        if self.confirmed_at != self.break_close_time:
            raise ValueError("Structural break is confirmed at candle close.")

        if self.break_open_time < self.pivot_confirmed_at:
            raise ValueError("A break cannot precede swing confirmation.")

        if self.liquidity_sweep_preceded:
            if self.liquidity_side is None or self.liquidity_sweep_time is None:
                raise ValueError("Sweep evidence requires its side and timestamp.")

            if self.liquidity_sweep_time >= self.break_open_time:
                raise ValueError("Liquidity sweep must precede the break candle.")
        elif self.liquidity_side is not None or self.liquidity_sweep_time is not None:
            raise ValueError("Sweep details cannot be supplied without a sweep.")

        expected_direction = (
            BreakDirection.BULLISH
            if self.broken_swing_type == SwingType.HIGH
            else BreakDirection.BEARISH
        )

        if self.direction != expected_direction:
            raise ValueError("Break direction must agree with the broken swing type.")

        if self.event_type == StructureEventType.MSS:
            if not self.displacement_confirmed:
                raise ValueError("MSS requires displacement confirmation.")

            if (
                self.profile == StructureBreakProfile.STRICT_ICT_2022
                and not self.liquidity_sweep_preceded
            ):
                raise ValueError("Strict MSS requires a preceding liquidity sweep.")

        return self


__all__ = [
    "BreakDirection",
    "LiquiditySide",
    "LiquiditySweepEvidence",
    "StructureBreakConfig",
    "StructureBreakEvent",
    "StructureBreakProfile",
    "StructureEventType",
]
