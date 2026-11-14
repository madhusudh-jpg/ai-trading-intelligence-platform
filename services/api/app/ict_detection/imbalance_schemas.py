
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


class ImbalanceDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ImbalanceStatus(StrEnum):
    ACTIVE = "active"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class InverseFVGStatus(StrEnum):
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class ImbalanceDetectionConfig(BaseModel):
    """Configuration for fair value gap and imbalance detection."""

    model_config = ConfigDict(frozen=True)

    minimum_gap_size: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )
    minimum_overlap_size: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )
    maximum_age_bars: int = Field(default=200, ge=1)

    @field_validator("minimum_gap_size", "minimum_overlap_size")
    @classmethod
    def validate_thresholds(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Imbalance thresholds must be finite.")
        return value


class FairValueGap(BaseModel):
    """A three-candle fair value gap confirmed at the third candle close."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    direction: ImbalanceDirection

    first_candle_time: datetime
    middle_candle_time: datetime
    confirmation_time: datetime
    confirmed_at: datetime

    first_candle_index: int = Field(ge=0)
    middle_candle_index: int = Field(ge=1)
    confirmation_candle_index: int = Field(ge=2)
    segment_id: int = Field(ge=0)

    lower_bound: Decimal = Field(gt=0)
    upper_bound: Decimal = Field(gt=0)
    gap_size: Decimal = Field(gt=0)
    consequent_encroachment: Decimal = Field(gt=0)

    status: ImbalanceStatus = ImbalanceStatus.ACTIVE

    @field_validator(
        "first_candle_time",
        "middle_candle_time",
        "confirmation_time",
        "confirmed_at",
    )
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Imbalance timestamps must be timezone-aware.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_gap(self):
        if not (
            self.first_candle_time
            < self.middle_candle_time
            < self.confirmation_time
        ):
            raise ValueError("FVG candle timestamps must be chronological.")

        if self.confirmed_at != self.confirmation_time:
            raise ValueError("FVG must be confirmed at the third candle close.")

        if self.middle_candle_index <= self.first_candle_index:
            raise ValueError("Middle candle index must follow first candle.")

        if self.confirmation_candle_index <= self.middle_candle_index:
            raise ValueError("Confirmation candle must follow middle candle.")

        if self.lower_bound >= self.upper_bound:
            raise ValueError("FVG lower bound must be below upper bound.")

        expected_size = self.upper_bound - self.lower_bound
        if self.gap_size != expected_size:
            raise ValueError("FVG gap_size must match its price boundaries.")

        expected_ce = (self.lower_bound + self.upper_bound) / Decimal("2")
        if self.consequent_encroachment != expected_ce:
            raise ValueError("Consequent encroachment must be the gap midpoint.")

        return self


class InverseFairValueGap(BaseModel):
    """An FVG whose boundary has been invalidated and reversed in role."""

    model_config = ConfigDict(frozen=True)

    original_fvg: FairValueGap

    inverse_direction: ImbalanceDirection
    status: InverseFVGStatus = InverseFVGStatus.CONFIRMED

    invalidation_candle_time: datetime
    confirmed_at: datetime

    invalidation_candle_index: int = Field(ge=0)

    @field_validator("invalidation_candle_time", "confirmed_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("IFVG timestamps must be timezone-aware.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_inverse(self):
        if self.confirmed_at <= self.original_fvg.confirmed_at:
            raise ValueError("IFVG must form after its original FVG.")

        if self.invalidation_candle_time > self.confirmed_at:
            raise ValueError("Invalidation cannot occur after confirmation.")

        expected_direction = (
            ImbalanceDirection.BEARISH
            if self.original_fvg.direction == ImbalanceDirection.BULLISH
            else ImbalanceDirection.BULLISH
        )

        if self.inverse_direction != expected_direction:
            raise ValueError("IFVG direction must reverse the original FVG.")

        return self


class BalancedPriceRange(BaseModel):
    """An overlap between a bullish and bearish fair value gap."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    bullish_fvg: FairValueGap
    bearish_fvg: FairValueGap

    lower_bound: Decimal = Field(gt=0)
    upper_bound: Decimal = Field(gt=0)
    overlap_size: Decimal = Field(gt=0)
    consequent_encroachment: Decimal = Field(gt=0)

    confirmed_at: datetime
    segment_id: int = Field(ge=0)

    @field_validator("confirmed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("BPR timestamp must be timezone-aware.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_bpr(self):
        if self.bullish_fvg.direction != ImbalanceDirection.BULLISH:
            raise ValueError("BPR requires a bullish FVG.")

        if self.bearish_fvg.direction != ImbalanceDirection.BEARISH:
            raise ValueError("BPR requires a bearish FVG.")

        streams = (
            self.bullish_fvg.symbol == self.symbol,
            self.bearish_fvg.symbol == self.symbol,
            self.bullish_fvg.asset_class == self.asset_class,
            self.bearish_fvg.asset_class == self.asset_class,
            self.bullish_fvg.timeframe == self.timeframe,
            self.bearish_fvg.timeframe == self.timeframe,
            self.bullish_fvg.provider == self.provider,
            self.bearish_fvg.provider == self.provider,
            self.bullish_fvg.segment_id == self.segment_id,
            self.bearish_fvg.segment_id == self.segment_id,
        )

        if not all(streams):
            raise ValueError("BPR FVGs must belong to the same market stream.")

        if self.confirmed_at < max(
            self.bullish_fvg.confirmed_at,
            self.bearish_fvg.confirmed_at,
        ):
            raise ValueError("BPR cannot precede confirmation of either FVG.")

        if self.lower_bound >= self.upper_bound:
            raise ValueError("BPR lower bound must be below upper bound.")

        if self.overlap_size != self.upper_bound - self.lower_bound:
            raise ValueError("BPR overlap size does not match its boundaries.")

        expected_ce = (self.lower_bound + self.upper_bound) / Decimal("2")
        if self.consequent_encroachment != expected_ce:
            raise ValueError("BPR consequent encroachment must be its midpoint.")

        return self


__all__ = [
    "BalancedPriceRange",
    "FairValueGap",
    "InverseFVGStatus",
    "ImbalanceDetectionConfig",
    "ImbalanceDirection",
    "ImbalanceStatus",
    "InverseFairValueGap",
    "InverseFVGStatus",

]
