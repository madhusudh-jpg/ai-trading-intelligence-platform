from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ict_detection import (
    SwingDetectionConfig,
    SwingDetectionService,
    SwingTier,
    SwingType,
)
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    Timeframe,
)
from app.market_data.services.timeframes import next_candle_open


def make_candles(
    highs: list[int],
    lows: list[int] | None = None,
    *,
    timeframe: Timeframe = Timeframe.H1,
    incomplete_indices: set[int] | None = None,
    open_times: list[datetime] | None = None,
    start_time: datetime | None = None,
) -> list[Candle]:
    """Build valid synthetic candles for unit tests."""

    if lows is None:
        lows = [5] * len(highs)

    if len(highs) != len(lows):
        raise ValueError("highs and lows must have equal lengths")

    if start_time is None:
        start_time = datetime(2026, 1, 1, tzinfo=UTC)

    if open_times is None:
        generated_times = []
        current_time = start_time

        for _ in highs:
            generated_times.append(current_time)
            current_time = next_candle_open(
                current_time,
                timeframe,
            )

        open_times = generated_times

    if len(open_times) != len(highs):
        raise ValueError(
            "open_times and highs must have equal lengths"
        )

    incomplete_indices = incomplete_indices or set()

    candles = []

    for index, (high_value, low_value) in enumerate(
        zip(highs, lows, strict=True)
    ):
        high = Decimal(high_value)
        low = Decimal(low_value)

        if high <= low:
            raise ValueError("Every test high must exceed its low")

        middle = (high + low) / Decimal("2")
        open_time = open_times[index]

        candles.append(
            Candle(
                symbol="BTCUSDT",
                asset_class=AssetClass.CRYPTO,
                timeframe=timeframe,
                open_time=open_time,
                close_time=next_candle_open(
                    open_time,
                    timeframe,
                ),
                open=middle,
                high=high,
                low=low,
                close=middle,
                volume=Decimal("10"),
                is_complete=index not in incomplete_indices,
                provider="binance",
            )
        )

    return candles


def filter_points(
    points,
    swing_type: SwingType,
    tier: SwingTier = SwingTier.SHORT_TERM,
):
    return [
        point
        for point in points
        if point.swing_type == swing_type
        and point.tier == tier
    ]


def test_detects_confirmed_swing_high():
    candles = make_candles(
        highs=[10, 11, 15, 12, 11],
        lows=[5, 6, 7, 6, 5],
    )

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=2,
            right_bars=2,
            include_hierarchy=False,
        )
    )

    points = service.detect(candles)

    swing_highs = filter_points(
        points,
        SwingType.HIGH,
    )

    assert len(swing_highs) == 1

    swing = swing_highs[0]

    assert swing.price == Decimal("15")
    assert swing.pivot_index == 2
    assert swing.pivot_time == candles[2].open_time
    assert swing.confirmed_at == candles[4].close_time
    assert swing.tier == SwingTier.SHORT_TERM


def test_detects_confirmed_swing_low():
    candles = make_candles(
        highs=[18, 17, 16, 17, 18],
        lows=[7, 6, 2, 5, 6],
    )

    service = SwingDetectionService(
        SwingDetectionConfig(include_hierarchy=False)
    )

    points = service.detect(candles)

    swing_lows = filter_points(
        points,
        SwingType.LOW,
    )

    assert len(swing_lows) == 1

    swing = swing_lows[0]

    assert swing.price == Decimal("2")
    assert swing.pivot_index == 2
    assert swing.confirmed_at == candles[4].close_time


def test_does_not_confirm_pivot_without_enough_right_candles():
    candles = make_candles(
        highs=[10, 11, 15, 12],
    )

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=2,
            right_bars=2,
            include_hierarchy=False,
        )
    )

    points = service.detect(candles)

    assert filter_points(
        points,
        SwingType.HIGH,
    ) == []


def test_forming_candle_cannot_confirm_swing():
    candles = make_candles(
        highs=[10, 11, 15, 12, 11],
        incomplete_indices={4},
    )

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=2,
            right_bars=2,
            include_hierarchy=False,
        )
    )

    points = service.detect(candles)

    assert filter_points(
        points,
        SwingType.HIGH,
    ) == []


def test_does_not_detect_pivot_across_missing_candle_gap():
    start = datetime(2026, 1, 1, tzinfo=UTC)

    open_times = [
        start,
        start.replace(hour=1),
        start.replace(hour=2),
        start.replace(hour=4),
        start.replace(hour=5),
    ]

    candles = make_candles(
        highs=[10, 11, 20, 12, 10],
        open_times=open_times,
    )

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=2,
            right_bars=2,
            include_hierarchy=False,
        )
    )

    points = service.detect(candles)

    assert filter_points(
        points,
        SwingType.HIGH,
    ) == []


def test_equal_adjacent_highs_do_not_create_strict_pivot():
    candles = make_candles(
        highs=[10, 15, 15, 12, 10],
    )

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=1,
            right_bars=1,
            include_hierarchy=False,
        )
    )

    points = service.detect(candles)

    assert filter_points(
        points,
        SwingType.HIGH,
    ) == []


def test_rejects_duplicate_candle_timestamps():
    candles = make_candles(
        highs=[10, 12, 10],
    )

    service = SwingDetectionService()

    with pytest.raises(
        ValueError,
        match="Duplicate candle",
    ):
        service.detect([*candles, candles[0]])


def test_rejects_mixed_timeframes():
    hourly = make_candles(
        highs=[10],
        timeframe=Timeframe.H1,
    )

    quarter_hour = make_candles(
        highs=[12],
        timeframe=Timeframe.M15,
        start_time=datetime(
            2026,
            1,
            1,
            0,
            15,
            tzinfo=UTC,
        ),
    )

    service = SwingDetectionService()

    with pytest.raises(
        ValueError,
        match="same symbol",
    ):
        service.detect([*hourly, *quarter_hour])


def test_sorts_unordered_input_before_detection():
    candles = make_candles(
        highs=[10, 11, 15, 12, 11],
    )

    service = SwingDetectionService(
        SwingDetectionConfig(include_hierarchy=False)
    )

    ordered_result = service.detect(candles)
    unordered_result = service.detect(list(reversed(candles)))

    assert ordered_result == unordered_result


def test_derives_intermediate_and_long_term_swings():
    swing_peaks = [
        12, 11, 14, 11, 13, 11, 16,
        11, 14, 11, 15, 11, 12,
    ]

    highs = [9]

    for peak in swing_peaks:
        highs.extend([peak, 8])

    candles = make_candles(highs=highs)

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=1,
            right_bars=1,
            include_hierarchy=True,
        )
    )

    points = service.detect(candles)

    short_highs = filter_points(
        points,
        SwingType.HIGH,
        SwingTier.SHORT_TERM,
    )

    intermediate_highs = filter_points(
        points,
        SwingType.HIGH,
        SwingTier.INTERMEDIATE_TERM,
    )

    long_highs = filter_points(
        points,
        SwingType.HIGH,
        SwingTier.LONG_TERM,
    )

    assert len(short_highs) == len(swing_peaks)

    assert [
        point.price for point in intermediate_highs
    ] == [
        Decimal("14"),
        Decimal("13"),
        Decimal("16"),
        Decimal("14"),
        Decimal("15"),
    ]

    assert len(long_highs) == 1

    long_swing = long_highs[0]

    assert long_swing.price == Decimal("16")
    assert long_swing.pivot_index == 13

    # The long-term swing must wait for its neighbouring
    # intermediate-term swings to be confirmed.
    assert long_swing.confirmed_at == candles[20].close_time


def test_can_disable_hierarchical_swings():
    candles = make_candles(
        highs=[10, 11, 15, 12, 11],
    )

    service = SwingDetectionService(
        SwingDetectionConfig(
            left_bars=2,
            right_bars=2,
            include_hierarchy=False,
        )
    )

    points = service.detect(candles)

    assert all(
        point.tier == SwingTier.SHORT_TERM
        for point in points
    )


def test_empty_candle_input_returns_empty_result():
    service = SwingDetectionService()

    assert service.detect([]) == []


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        SwingDetectionConfig(left_bars=0)

    with pytest.raises(ValueError):
        SwingDetectionConfig(right_bars=-1)