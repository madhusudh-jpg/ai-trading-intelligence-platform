
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.ict_detection.displacement_schemas import DisplacementEvent
from app.ict_detection.imbalance_schemas import (
    BalancedPriceRange,
    FairValueGap,
    InverseFairValueGap,
)
from app.ict_detection.liquidity_schemas import LiquidityPool
from app.ict_detection.market_structure_schemas import MarketStructureResult
from app.ict_detection.order_block_schemas import OrderBlock
from app.ict_detection.schemas import SwingPoint
from app.ict_detection.structure_break_schemas import (
    LiquiditySweepEvidence,
    StructureBreakEvent,
)


class ICTAnalysisResult(BaseModel):
    """Combined ICT detection results for one market-data timeframe."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: str
    timeframe: str
    provider: str

    analyzed_at: datetime

    swings: tuple[SwingPoint, ...] = ()
    market_structure: MarketStructureResult

    displacements: tuple[DisplacementEvent, ...] = ()
    structure_breaks: tuple[StructureBreakEvent, ...] = ()

    liquidity_pools: tuple[LiquidityPool, ...] = ()
    liquidity_sweeps: tuple[LiquiditySweepEvidence, ...] = ()

    fair_value_gaps: tuple[FairValueGap, ...] = ()
    inverse_fair_value_gaps: tuple[InverseFairValueGap, ...] = ()
    balanced_price_ranges: tuple[BalancedPriceRange, ...] = ()

    order_blocks: tuple[OrderBlock, ...] = ()

    @model_validator(mode="after")
    def validate_analysis(self) -> "ICTAnalysisResult":
        if self.analyzed_at.tzinfo is None or self.analyzed_at.utcoffset() is None:
            raise ValueError("analyzed_at must be timezone-aware.")

        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty.")

        if not self.provider.strip():
            raise ValueError("provider cannot be empty.")

        if not self.asset_class.strip():
            raise ValueError("asset_class cannot be empty.")

        if not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty.")

        return self


__all__ = ["ICTAnalysisResult"]
