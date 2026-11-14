from decimal import Decimal

from app.ict_detection.displacement_schemas import (
    DisplacementDirection,
    DisplacementEvent,
)
from app.market_data.schemas.market_data import AssetClass, Timeframe
from datetime import datetime, timezone

from app.ict_detection.analysis_schemas import ICTAnalysisResult
from app.ict_detection.confluence_schemas import (
    ConfluenceStatus,
)
from app.ict_detection.market_structure_schemas import (
    MarketStructureResult,
    StructureScope,
    StructureState,
)
from app.ict_detection.services.confluence_service import ConfluenceService


def create_market_structure() -> MarketStructureResult:
    return MarketStructureResult(
        symbol="BTCUSDT",
        asset_class="crypto",
        timeframe="1h",
        provider="test",
        classified_swings=[],
        internal=StructureState(scope=StructureScope.INTERNAL),
        intermediate=StructureState(scope=StructureScope.INTERMEDIATE),
        external=StructureState(scope=StructureScope.EXTERNAL),
    )


def create_analysis(**overrides) -> ICTAnalysisResult:
    data = {
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "timeframe": "1h",
        "provider": "test",
        "analyzed_at": datetime.now(timezone.utc),
        "market_structure": create_market_structure(),
    }
    data.update(overrides)
    return ICTAnalysisResult(**data)

def create_displacement(
    candle_index: int,
    direction: DisplacementDirection = DisplacementDirection.BULLISH,
) -> DisplacementEvent:
    open_time = datetime(2026, 1, 1, 10 + candle_index, tzinfo=timezone.utc)
    close_time = open_time.replace(minute=59)

    return DisplacementEvent(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        provider="test",
        direction=direction,
        candle_index=candle_index,
        segment_id=0,
        open_time=open_time,
        close_time=close_time,
        confirmed_at=close_time,
        open_price=Decimal("100"),
        close_price=Decimal("105"),
        high_price=Decimal("106"),
        low_price=Decimal("99"),
        true_range=Decimal("7"),
        atr_value=Decimal("5"),
        body_ratio=Decimal("0.80"),
        range_expansion_atr=Decimal("1.5"),
        directional_close_location=Decimal("0.90"),
        opposing_wick_ratio=Decimal("0.10"),
    )


def test_empty_analysis_returns_insufficient_evidence():
    result = ConfluenceService().analyze(create_analysis())

    assert result.status == ConfluenceStatus.INSUFFICIENT_EVIDENCE
    assert result.bullish_evidence_count == 0
    assert result.bearish_evidence_count == 0
    assert result.evidence == ()


def test_single_bullish_displacement_is_insufficient_evidence():
    analysis = create_analysis(
        displacements=(create_displacement(1),),
    )

    result = ConfluenceService().analyze(analysis)

    assert result.status == ConfluenceStatus.INSUFFICIENT_EVIDENCE
    assert result.bullish_evidence_count == 1
    assert result.bearish_evidence_count == 0


def test_two_independent_bullish_displacements_produce_bullish_alignment():
    analysis = create_analysis(
        displacements=(
            create_displacement(1),
            create_displacement(2),
        ),
    )

    result = ConfluenceService().analyze(analysis)

    assert result.status == ConfluenceStatus.BULLISH_ALIGNMENT
    assert result.bullish_evidence_count == 2
    assert result.bearish_evidence_count == 0