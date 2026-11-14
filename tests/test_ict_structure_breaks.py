from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ict_detection import (
    DisplacementDirection,
    StructureBreakConfig,
    StructureBreakProfile,
    StructureBreakService,
    StructureEventType,
)
from app.ict_detection.displacement_schemas import DisplacementEvent
from app.ict_detection.schemas import SwingPoint, SwingTier, SwingType
from app.ict_detection.structure_break_schemas import (
    BreakDirection,
    LiquiditySide,
    LiquiditySweepEvidence,
)
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    Timeframe,
)
from app.market_data.services.timeframes import next_candle_open

START = datetime(2026, 1, 1, tzinfo=UTC)


def make_candles(
    count: int,
    overrides: dict[int, tuple[str, str, str, str]] | None = None,
) -> list[Candle]:
    """Create chronological hourly candles."""

    overrides = overrides or {}
    candles = []

    for index in range(count):
        values = overrides.get(
            index,
            ("102", "103", "101", "102"),
        )

        open_price, high, low, close = map(
            Decimal,
            values,
        )

        open_time = START + timedelta(hours=index)

        candles.append(
            Candle(
                symbol="BTCUSDT",
                asset_class=AssetClass.CRYPTO,
                timeframe=Timeframe.H1,
                open_time=open_time,
                close_time=next_candle_open(
                    open_time,
                    Timeframe.H1,
                ),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=Decimal("10"),
                is_complete=True,
                provider="binance",
            )
        )

    return candles


def make_swing(
    candles: list[Candle],
    pivot_index: int,
    confirmation_index: int,
    swing_type: SwingType,
    *,
    tier: SwingTier = SwingTier.SHORT_TERM,
) -> SwingPoint:
    candle = candles[pivot_index]

    price = candle.high if swing_type == SwingType.HIGH else candle.low

    return SwingPoint(
        symbol=candle.symbol,
        asset_class=candle.asset_class,
        timeframe=candle.timeframe,
        provider=candle.provider,
        swing_type=swing_type,
        tier=tier,
        price=price,
        pivot_time=candle.open_time,
        confirmed_at=candles[confirmation_index].close_time,
        pivot_index=pivot_index,
        segment_id=0,
        left_bars=2,
        right_bars=2,
        confirmation_basis="fractal",
    )


def bearish_structure_setup(
    *,
    break_index: int = 14,
    break_close: str = "112",
    include_recent_internal_high: bool = False,
) -> tuple[list[Candle], list[SwingPoint]]:
    """Create lower-high/lower-low structure."""

    overrides = {
        2: ("105", "110", "104", "106"),
        5: ("103", "104", "100", "101"),
        8: ("102", "105", "98", "103"),
        11: ("100", "103", "95", "99"),
        13: ("102", "103", "97", "102"),
    }

    if include_recent_internal_high:
        overrides[14] = ("102", "104", "101", "103")
        break_index = 17

    if Decimal(break_close) > Decimal("100"):
        overrides[break_index] = (
            "102",
            "116",
            "101",
            break_close,
        )
    else:
        overrides[break_index] = (
            "102",
            "103",
            "87",
            break_close,
        )

    candles = make_candles(20, overrides)

    swings = [
        make_swing(candles, 2, 4, SwingType.HIGH),
        make_swing(candles, 5, 7, SwingType.LOW),
        make_swing(candles, 8, 10, SwingType.HIGH),
        make_swing(candles, 11, 13, SwingType.LOW),
    ]

    if include_recent_internal_high:
        swings.append(make_swing(candles, 14, 16, SwingType.HIGH))

    return candles, swings


def bullish_structure_setup() -> tuple[list[Candle], list[SwingPoint]]:
    """Create HH/HL structure followed by a bullish continuation."""

    overrides = {
        0: ("98", "99", "97", "98"),
        1: ("98", "99", "97", "98"),
        2: ("99", "100", "96", "98"),
        3: ("98", "99", "96", "98"),
        4: ("98", "99", "96", "98"),
        5: ("92", "95", "90", "91"),
        8: ("105", "110", "98", "108"),
        11: ("100", "104", "95", "101"),
        14: ("112", "115", "106", "114"),
        17: ("102", "121", "101", "120"),
    }

    candles = make_candles(20, overrides)

    swings = [
        make_swing(candles, 2, 4, SwingType.HIGH),
        make_swing(candles, 5, 7, SwingType.LOW),
        make_swing(candles, 8, 10, SwingType.HIGH),
        make_swing(candles, 11, 13, SwingType.LOW),
        make_swing(candles, 14, 16, SwingType.HIGH),
    ]

    return candles, swings


def make_displacement(
    candle: Candle,
    candle_index: int,
    *,
    direction: DisplacementDirection,
) -> DisplacementEvent:
    candle_range = candle.high - candle.low
    body = abs(candle.close - candle.open)

    if direction == DisplacementDirection.BULLISH:
        close_location = (candle.close - candle.low) / candle_range
        opposing_wick = (candle.open - candle.low) / candle_range
    else:
        close_location = (candle.high - candle.close) / candle_range
        opposing_wick = (candle.high - candle.open) / candle_range

    return DisplacementEvent(
        symbol=candle.symbol,
        asset_class=candle.asset_class,
        timeframe=candle.timeframe,
        provider=candle.provider,
        direction=direction,
        candle_index=candle_index,
        segment_id=0,
        open_time=candle.open_time,
        close_time=candle.close_time,
        confirmed_at=candle.close_time,
        open_price=candle.open,
        close_price=candle.close,
        high_price=candle.high,
        low_price=candle.low,
        true_range=candle_range,
        atr_value=Decimal("10"),
        body_ratio=body / candle_range,
        range_expansion_atr=candle_range / Decimal("10"),
        directional_close_location=close_location,
        opposing_wick_ratio=opposing_wick,
    )


def make_sell_side_sweep(
    candle: Candle,
) -> LiquiditySweepEvidence:
    return LiquiditySweepEvidence(
        symbol=candle.symbol,
        asset_class=candle.asset_class,
        timeframe=candle.timeframe,
        provider=candle.provider,
        liquidity_side=LiquiditySide.SELL_SIDE,
        segment_id=0,
        pool_price=Decimal("98"),
        swept_price=Decimal("97.5"),
        sweep_time=candle.open_time,
        confirmed_at=candle.close_time,
    )


def test_detects_bullish_bos():
    candles, swings = bullish_structure_setup()

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
    )

    # The earliest bullish break occurs before enough structure exists to
    # establish a trend, so it must remain unclassified.
    assert any(
        item.direction == BreakDirection.BULLISH
        and item.event_type == StructureEventType.UNCLASSIFIED_BREAK
        for item in events
    )

    # Select the latest confirmed bullish BOS, not the earlier unclassified
    # break or the first continuation BOS at the lower swing level.
    event = next(
        item
        for item in reversed(events)
        if item.direction == BreakDirection.BULLISH
        and item.event_type == StructureEventType.BOS
    )

    assert event.prior_trend == "bullish"
    assert event.broken_level == Decimal("115")


def test_detects_bearish_bos():
    candles, swings = bearish_structure_setup(
        break_close="88",
    )

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
    )

    # The earliest bearish break occurs before enough structure exists to
    # establish a trend, so it must remain unclassified.
    assert any(
        item.direction == BreakDirection.BEARISH
        and item.event_type == StructureEventType.UNCLASSIFIED_BREAK
        for item in events
    )

    # Select the confirmed bearish BOS after the lower-high/lower-low
    # sequence has established a bearish trend.
    event = next(
        item
        for item in events
        if item.direction == BreakDirection.BEARISH
        and item.event_type == StructureEventType.BOS
    )

    assert event.prior_trend == "bearish"
    assert event.broken_level == Decimal("95")


def test_detects_standard_bullish_mss():
    candles, swings = bearish_structure_setup()

    displacement = make_displacement(
        candles[14],
        14,
        direction=DisplacementDirection.BULLISH,
    )

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
        displacements=[displacement],
    )

    event = next(item for item in events if item.direction == BreakDirection.BULLISH)

    assert event.event_type == StructureEventType.MSS
    assert event.displacement_confirmed is True
    assert event.broken_level == Decimal("105")


def test_strict_mss_requires_preceding_sell_side_sweep():
    candles, swings = bearish_structure_setup()

    displacement = make_displacement(
        candles[14],
        14,
        direction=DisplacementDirection.BULLISH,
    )

    sweep = make_sell_side_sweep(candles[13])

    service = StructureBreakService(
        StructureBreakConfig(profile=StructureBreakProfile.STRICT_ICT_2022)
    )

    events = service.detect(
        candles=candles,
        swings=swings,
        displacements=[displacement],
        liquidity_sweeps=[sweep],
    )

    event = next(item for item in events if item.direction == BreakDirection.BULLISH)

    assert event.event_type == StructureEventType.MSS
    assert event.liquidity_sweep_preceded is True
    assert event.liquidity_side == LiquiditySide.SELL_SIDE


def test_strict_profile_without_sweep_downgrades_to_choch():
    candles, swings = bearish_structure_setup()

    displacement = make_displacement(
        candles[14],
        14,
        direction=DisplacementDirection.BULLISH,
    )

    service = StructureBreakService(
        StructureBreakConfig(profile=StructureBreakProfile.STRICT_ICT_2022)
    )

    events = service.detect(
        candles=candles,
        swings=swings,
        displacements=[displacement],
    )

    event = next(item for item in events if item.direction == BreakDirection.BULLISH)

    assert event.event_type == StructureEventType.CHOCH
    assert event.displacement_confirmed is True
    assert event.liquidity_sweep_preceded is False


def test_protected_level_break_without_displacement_is_choch():
    candles, swings = bearish_structure_setup()

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
    )

    event = next(item for item in events if item.direction == BreakDirection.BULLISH)

    assert event.event_type == StructureEventType.CHOCH
    assert event.displacement_confirmed is False


def test_non_protected_internal_break_is_choch():
    candles, swings = bearish_structure_setup(
        break_close="104.5",
        include_recent_internal_high=True,
    )

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
    )

    event = next(
        item for item in events if item.break_open_time == candles[17].open_time
    )

    assert event.event_type == StructureEventType.CHOCH
    assert event.broken_level == Decimal("104")


def test_wick_only_break_is_not_confirmed():
    candles, swings = bearish_structure_setup(
        break_close="104",
    )

    candles[14] = candles[14].model_copy(
        update={
            "open": Decimal("102"),
            "high": Decimal("116"),
            "low": Decimal("101"),
            "close": Decimal("104"),
        }
    )

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
    )

    assert not [event for event in events if event.direction == BreakDirection.BULLISH]


def test_insufficient_prior_structure_is_unclassified():
    candles, _ = bearish_structure_setup()

    swing = make_swing(
        candles,
        8,
        10,
        SwingType.HIGH,
    )

    events = StructureBreakService().detect(
        candles=candles,
        swings=[swing],
    )

    event = next(item for item in events if item.direction == BreakDirection.BULLISH)

    assert event.event_type == StructureEventType.UNCLASSIFIED_BREAK


def test_future_swings_do_not_change_past_mss_classification():
    candles, swings = bearish_structure_setup()

    # Add a future swing after the MSS candle.
    future_candle = candles[17].model_copy(
        update={
            "open": Decimal("110"),
            "high": Decimal("120"),
            "low": Decimal("109"),
            "close": Decimal("115"),
        }
    )
    candles[17] = future_candle

    future_swing = make_swing(
        candles,
        17,
        19,
        SwingType.HIGH,
    )

    displacement = make_displacement(
        candles[14],
        14,
        direction=DisplacementDirection.BULLISH,
    )

    original = StructureBreakService().detect(
        candles=candles,
        swings=swings,
        displacements=[displacement],
    )

    extended = StructureBreakService().detect(
        candles=candles,
        swings=[*swings, future_swing],
        displacements=[displacement],
    )

    original_event = next(
        event
        for event in original
        if event.break_open_time == candles[14].open_time
        and event.direction == BreakDirection.BULLISH
    )

    extended_event = next(
        event
        for event in extended
        if event.break_open_time == candles[14].open_time
        and event.direction == BreakDirection.BULLISH
    )

    assert original_event.event_type == StructureEventType.MSS
    assert extended_event.event_type == original_event.event_type
    assert extended_event.prior_trend == original_event.prior_trend


def test_forming_break_candle_cannot_confirm_event():
    candles, swings = bearish_structure_setup()

    candles[14] = candles[14].model_copy(update={"is_complete": False})

    events = StructureBreakService().detect(
        candles=candles,
        swings=swings,
    )

    assert not [event for event in events if event.direction == BreakDirection.BULLISH]


def test_break_buffer_is_applied():
    candles, swings = bearish_structure_setup(
        break_close="106",
    )

    service = StructureBreakService(StructureBreakConfig(break_buffer=Decimal("2")))

    events = service.detect(
        candles=candles,
        swings=swings,
    )

    assert not [event for event in events if event.direction == BreakDirection.BULLISH]


def test_rejects_swing_price_not_matching_pivot_candle():
    candles, swings = bearish_structure_setup()

    swings[2] = swings[2].model_copy(update={"price": Decimal("106")})

    with pytest.raises(ValueError, match="does not match"):
        StructureBreakService().detect(
            candles=candles,
            swings=swings,
        )


def test_rejects_duplicate_swing_input():
    candles, swings = bearish_structure_setup()

    with pytest.raises(ValueError, match="Duplicate swing"):
        StructureBreakService().detect(
            candles=candles,
            swings=[*swings, swings[0]],
        )


def test_rejects_duplicate_candle_timestamps():
    candles, swings = bearish_structure_setup()

    with pytest.raises(ValueError, match="Duplicate candle"):
        StructureBreakService().detect(
            candles=[*candles, candles[0]],
            swings=swings,
        )
