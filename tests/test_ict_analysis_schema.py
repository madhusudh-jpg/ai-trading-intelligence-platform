
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.ict_detection.analysis_schemas import ICTAnalysisResult
from app.ict_detection.market_structure_schemas import (
    MarketStructureResult,
    StructureScope,
    StructureState,
)
from app.market_data.schemas.market_data import AssetClass, Timeframe


def create_market_structure() -> MarketStructureResult:
    return MarketStructureResult(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
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


def test_analysis_accepts_valid_metadata():
    result = create_analysis()

    assert result.symbol == "BTCUSDT"
    assert result.timeframe == "1h"
    assert result.market_structure.symbol == "BTCUSDT"


def test_analysis_rejects_naive_analyzed_at():
    with pytest.raises(ValidationError):
        create_analysis(analyzed_at=datetime(2026, 1, 1))


@pytest.mark.parametrize(
    "field",
    ["symbol", "asset_class", "timeframe", "provider"],
)
def test_analysis_rejects_empty_metadata(field):
    with pytest.raises(ValidationError):
        create_analysis(**{field: "   "})


def test_analysis_collections_default_to_empty_tuples():
    result = create_analysis()

    assert result.swings == ()
    assert result.displacements == ()
    assert result.structure_breaks == ()
    assert result.liquidity_pools == ()
    assert result.liquidity_sweeps == ()
    assert result.fair_value_gaps == ()
    assert result.inverse_fair_value_gaps == ()
    assert result.balanced_price_ranges == ()
    assert result.order_blocks == ()


def test_analysis_result_is_immutable():
    result = create_analysis()

    with pytest.raises(ValidationError):
        result.symbol = "ETHUSDT"
