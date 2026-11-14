from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.ict_detection.schemas import SwingPoint, SwingTier, SwingType
from app.market_data.schemas.market_data import AssetClass, Timeframe


class StructureScope(StrEnum):
    INTERNAL = "internal"
    INTERMEDIATE = "intermediate"
    EXTERNAL = "external"


class SwingClassification(StrEnum):
    INITIAL = "initial"
    HH = "hh"
    HL = "hl"
    LH = "lh"
    LL = "ll"
    EQH = "eqh"
    EQL = "eql"


class MarketTrend(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    TRANSITIONAL = "transitional"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MarketStructureConfig:
    """Configuration for swing comparison and structure analysis."""

    price_tolerance: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        try:
            tolerance = Decimal(str(self.price_tolerance))
        except Exception as exc:
            raise ValueError("price_tolerance must be a valid decimal") from exc

        if not tolerance.is_finite() or tolerance < 0:
            raise ValueError("price_tolerance must be finite and non-negative")

        object.__setattr__(self, "price_tolerance", tolerance)


class ClassifiedSwing(BaseModel):
    """A confirmed swing with its structural classification."""

    model_config = ConfigDict(frozen=True)

    swing: SwingPoint
    scope: StructureScope
    classification: SwingClassification

    previous_comparable_price: Decimal | None = None
    price_difference: Decimal | None = None


class StructureLevel(BaseModel):
    """A compact representation of a classified structural level."""

    model_config = ConfigDict(frozen=True)

    price: Decimal
    pivot_time: datetime
    pivot_index: int
    segment_id: int

    swing_type: SwingType
    tier: SwingTier
    classification: SwingClassification


class StructureState(BaseModel):
    """Current structural interpretation for one hierarchy tier."""

    model_config = ConfigDict(frozen=True)

    scope: StructureScope
    segment_id: int | None = None
    trend: MarketTrend = MarketTrend.UNKNOWN

    latest_high: StructureLevel | None = None
    latest_low: StructureLevel | None = None

    high_count: int = 0
    low_count: int = 0

    # These levels are candidates until BOS/MSS confirmation.
    protected_high_candidate: StructureLevel | None = None
    protected_low_candidate: StructureLevel | None = None

    strong_high_candidate: StructureLevel | None = None
    strong_low_candidate: StructureLevel | None = None

    weak_high_candidate: StructureLevel | None = None
    weak_low_candidate: StructureLevel | None = None


class MarketStructureResult(BaseModel):
    """Complete multi-tier market structure result for one instrument."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    classified_swings: list[ClassifiedSwing]

    internal: StructureState
    intermediate: StructureState
    external: StructureState


__all__ = [
    "ClassifiedSwing",
    "MarketStructureConfig",
    "MarketStructureResult",
    "MarketTrend",
    "StructureLevel",
    "StructureScope",
    "StructureState",
    "SwingClassification",
]
