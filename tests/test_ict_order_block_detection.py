
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ict_detection.displacement_schemas import (
    DisplacementDirection,
    DisplacementEvent,
)
from app.ict_detection.market_structure_schemas import (
    MarketTrend,
    StructureScope,
)
from app.ict_detection.order_block_schemas import (
    OrderBlockDetectionConfig,
    OrderBlockDirection,
    OrderBlockStatus,
)
from app.ict_detection.schemas import SwingTier, SwingType
from app.ict_detection.services.order_block_detection_service import (
    OrderBlockDetectionService,
)
from app.ict_detection.structure_break_schemas import (
    BreakDirection,
    StructureBreakEvent,
    StructureBreakProfile,
    StructureEventType,
)
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    Timeframe,
)

BASE_TIME = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

SYMBOL = "TEST"
PROVIDER = "test_provider"


def make_candle(
    index: int,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    *,
    is_complete: bool = True,
) -> Candle:
    open_time = BASE_TIME + timedelta(hours=index)

    return Candle(
        symbol=SYMBOL,
        asset_class=AssetClass.US_STOCKS,
        timeframe=Timeframe.H1,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=Decimal(open_price),
        high=Decimal(high_price),
        low=Decimal(low_price),
        close=Decimal(close_price),
        volume=Decimal("1000"),
        is_complete=is_complete,
        provider=PROVIDER,
    )


def make_bullish_candles(
    *,
    subsequent_candles: list[Candle] | None = None,
) -> list[Candle]:
    candles = [
        make_candle(0, "100", "106", "99", "104"),
        make_candle(1, "104", "108", "103", "106"),
        # Last bearish candle: bullish order block origin.
        make_candle(2, "105", "106", "100", "102"),
        # Bullish displacement and structure break.
        make_candle(3, "103", "111", "102", "110"),
    ]

    if subsequent_candles:
        candles.extend(subsequent_candles)

    return candles


def make_bearish_candles() -> list[Candle]:
    return [
        make_candle(0, "105", "107", "100", "102"),
        make_candle(1, "102", "104", "98", "100"),
        # Last bullish candle: bearish order block origin.
        make_candle(2, "102", "106", "101", "105"),
        # Bearish displacement and structure break.
        make_candle(3, "104", "105", "96", "97"),
    ]


def make_displacement(
    candles: list[Candle],
    direction: DisplacementDirection,
) -> DisplacementEvent:
    candle = candles[3]

    return DisplacementEvent(
        symbol=SYMBOL,
        asset_class=AssetClass.US_STOCKS,
        timeframe=Timeframe.H1,
        provider=PROVIDER,
        direction=direction,
        candle_index=3,
        segment_id=0,
        open_time=candle.open_time,
        close_time=candle.close_time,
        confirmed_at=candle.close_time,
        open_price=candle.open,
        close_price=candle.close,
        high_price=candle.high,
        low_price=candle.low,
        true_range=candle.high - candle.low,
        atr_value=Decimal("5"),
        body_ratio=Decimal("0.80"),
        range_expansion_atr=Decimal("1.5"),
        directional_close_location=Decimal("0.90"),
        opposing_wick_ratio=Decimal("0.10"),
    )


def make_structure_break(
    candles: list[Candle],
    direction: BreakDirection,
) -> StructureBreakEvent:
    pivot_candle = candles[0]
    confirmation_candle = candles[1]
    break_candle = candles[3]

    bullish = direction == BreakDirection.BULLISH

    swing_type = (
        SwingType.HIGH if bullish else SwingType.LOW
    )

    broken_level = (
        Decimal("105") if bullish else Decimal("100")
    )

    return StructureBreakEvent(
        symbol=SYMBOL,
        asset_class=AssetClass.US_STOCKS,
        timeframe=Timeframe.H1,
        provider=PROVIDER,
        event_type=StructureEventType.BOS,
        direction=direction,
        scope=next(iter(StructureScope)),
        profile=StructureBreakProfile.STANDARD,
        broken_swing_type=swing_type,
        broken_swing_tier=next(iter(SwingTier)),
        broken_level=broken_level,
        pivot_time=pivot_candle.open_time,
        pivot_confirmed_at=confirmation_candle.close_time,
        break_open_time=break_candle.open_time,
        break_close_time=break_candle.close_time,
        confirmed_at=break_candle.close_time,
        break_close=break_candle.close,
        break_buffer=Decimal("0"),
        prior_trend=next(iter(MarketTrend)),
        displacement_confirmed=True,
    )


def test_detects_bullish_order_block():
    candles = make_bullish_candles()

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [displacement],
        [structure_break],
    )

    assert len(result) == 1

    order_block = result[0]

    assert order_block.direction == OrderBlockDirection.BULLISH
    assert order_block.origin_candle_index == 2
    assert order_block.lower_bound == Decimal("100")
    assert order_block.upper_bound == Decimal("106")
    assert order_block.status == OrderBlockStatus.ACTIVE


def test_detects_bearish_order_block():
    candles = make_bearish_candles()

    displacement = make_displacement(
        candles,
        DisplacementDirection.BEARISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BEARISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [displacement],
        [structure_break],
    )

    assert len(result) == 1

    order_block = result[0]

    assert order_block.direction == OrderBlockDirection.BEARISH
    assert order_block.origin_candle_index == 2
    assert order_block.lower_bound == Decimal("101")
    assert order_block.upper_bound == Decimal("106")
    assert order_block.status == OrderBlockStatus.ACTIVE


def test_bullish_order_block_becomes_mitigated():
    mitigation_candle = make_candle(
        4,
        "105",
        "107",
        "103",
        "105",
    )

    candles = make_bullish_candles(
        subsequent_candles=[mitigation_candle],
    )

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [displacement],
        [structure_break],
    )

    assert len(result) == 1

    order_block = result[0]

    assert order_block.status == OrderBlockStatus.MITIGATED
    assert order_block.mitigated_at == mitigation_candle.close_time
    assert order_block.invalidated_at is None


def test_bullish_order_block_becomes_invalidated():
    mitigation_candle = make_candle(
        4,
        "105",
        "107",
        "103",
        "105",
    )

    invalidation_candle = make_candle(
        5,
        "104",
        "105",
        "98",
        "99",
    )

    candles = make_bullish_candles(
        subsequent_candles=[
            mitigation_candle,
            invalidation_candle,
        ],
    )

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [displacement],
        [structure_break],
    )

    assert len(result) == 1

    order_block = result[0]

    assert order_block.status == OrderBlockStatus.INVALIDATED
    assert order_block.mitigated_at == mitigation_candle.close_time
    assert order_block.invalidated_at == invalidation_candle.close_time


def test_does_not_detect_order_block_without_displacement():
    candles = make_bullish_candles()

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [],
        [structure_break],
    )

    assert result == []


def test_does_not_detect_order_block_without_structure_break():
    candles = make_bullish_candles()

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [displacement],
        [],
    )

    assert result == []


def test_does_not_detect_order_block_when_directions_conflict():
    candles = make_bullish_candles()

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BEARISH,
    )

    service = OrderBlockDetectionService()

    result = service.detect(
        candles,
        [displacement],
        [structure_break],
    )

    assert result == []


def test_does_not_use_forming_candle_as_order_block_origin():
    candles = make_bullish_candles()

    candles[2] = make_candle(
        2,
        "105",
        "106",
        "100",
        "102",
        is_complete=False,
    )

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    # The incomplete candle is excluded from the completed stream.
    # The displacement candle therefore has a new index and segment.
    displacement = displacement.model_copy(
        update={
            "candle_index": 2,
            "segment_id": 1,
        }
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    # The structure-break evidence references a pivot before the gap
    # and a break after the gap, so it must be rejected.
    with pytest.raises(
        ValueError,
        match="cannot cross data gaps",
    ):
        service.detect(
            candles,
            [displacement],
            [structure_break],
        )


def test_rejects_duplicate_displacement_events():
    candles = make_bullish_candles()

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    with pytest.raises(ValueError, match="Duplicate displacement"):
        service.detect(
            candles,
            [displacement, displacement],
            [structure_break],
        )


def test_rejects_displacement_evidence_with_wrong_candle_index():
    candles = make_bullish_candles()

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    invalid_displacement = displacement.model_copy(
        update={"candle_index": 2}
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService()

    with pytest.raises(
        ValueError,
        match="does not match its candle",
    ):
        service.detect(
            candles,
            [invalid_displacement],
            [structure_break],
        )


def test_empty_candle_input_returns_empty_list():
    service = OrderBlockDetectionService()

    result = service.detect(
        [],
        [],
        [],
    )

    assert result == []


def test_custom_invalidation_buffer_is_applied():
    candles = make_bullish_candles(
        subsequent_candles=[
            make_candle(
                4,
                "99.1",
                "99.4",
                "98.8",
                "99.2",
            )
        ],
    )

    displacement = make_displacement(
        candles,
        DisplacementDirection.BULLISH,
    )

    structure_break = make_structure_break(
        candles,
        BreakDirection.BULLISH,
    )

    service = OrderBlockDetectionService(
        OrderBlockDetectionConfig(
            invalidation_buffer=Decimal("1"),
        )
    )

    result = service.detect(
        candles,
        [displacement],
        [structure_break],
    )

    assert len(result) == 1
    assert result[0].status == OrderBlockStatus.ACTIVE
