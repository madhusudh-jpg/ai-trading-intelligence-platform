from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ict_detection import (
    DisplacementDetectionConfig,
    DisplacementDetectionService,
    DisplacementDirection,
)
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    Timeframe,
)
from app.market_data.services.timeframes import next_candle_open

START = datetime(2026, 1, 1, tzinfo=UTC)


def make_candle(
    index: int,
    *,
    open_price: str = "102",
    high: str = "110",
    low: str = "100",
    close: str = "105",
    complete: bool = True,
    symbol: str = "BTCUSDT",
    start_time: datetime = START,
) -> Candle:
    open_time = start_time + timedelta(hours=index)

    return Candle(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        open_time=open_time,
        close_time=next_candle_open(
            open_time,
            Timeframe.H1,
        ),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("10"),
        is_complete=complete,
        provider="binance",
    )


def baseline_candles() -> list[Candle]:
    """Three completed candles with a True Range of 10 each."""

    return [
        make_candle(index)
        for index in range(3)
    ]


def test_detects_bullish_displacement():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="132",
            low="99",
            close="130",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    events = service.detect(candles)

    assert len(events) == 1

    event = events[0]

    assert event.direction == DisplacementDirection.BULLISH
    assert event.atr_value == Decimal("10")
    assert event.true_range == Decimal("33")
    assert event.range_expansion_atr == Decimal("3.3")
    assert event.confirmed_at == candles[-1].close_time


def test_detects_bearish_displacement():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="130",
            high="131",
            low="98",
            close="99",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    events = service.detect(candles)

    assert len(events) == 1
    assert events[0].direction == DisplacementDirection.BEARISH


def test_rejects_small_candle_body():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="120",
            low="80",
            close="112",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == []


def test_rejects_insufficient_range_expansion():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="110",
            low="99",
            close="109.5",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == []


def test_rejects_weak_directional_close():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="90.5",
            high="110",
            low="90",
            close="105.5",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(
            atr_period=3,
            max_opposing_wick_ratio=Decimal("0.50"),
        )
    )

    assert service.detect(candles) == []


def test_rejects_large_opposing_wick():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="130",
            low="90",
            close="128",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == []


def test_atr_excludes_candidate_candle():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="132",
            low="99",
            close="130",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    events = service.detect(candles)

    assert len(events) == 1
    assert events[0].atr_value == Decimal("10")


def test_incomplete_candle_cannot_confirm_displacement():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="132",
            low="99",
            close="130",
            complete=False,
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == []


def test_missing_interval_resets_atr_history():
    candles = baseline_candles()

    # Skip the fourth hourly opening.
    candles.append(
        make_candle(
            4,
            open_price="100",
            high="132",
            low="99",
            close="130",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == []


def test_insufficient_atr_history_returns_no_events():
    candles = baseline_candles()[:2]
    candles.append(
        make_candle(
            2,
            open_price="100",
            high="132",
            low="99",
            close="130",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == []


def test_future_candle_does_not_change_prior_event():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="132",
            low="99",
            close="130",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    original_events = service.detect(candles)

    extended_candles = [
        *candles,
        make_candle(
            4,
            open_price="130",
            high="140",
            low="129",
            close="139",
        ),
    ]

    extended_events = service.detect(extended_candles)

    assert original_events[0] == extended_events[0]


def test_sorts_unordered_input():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="132",
            low="99",
            close="130",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    assert service.detect(candles) == service.detect(
        list(reversed(candles))
    )


def test_rejects_duplicate_candle_timestamps():
    candles = baseline_candles()

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    with pytest.raises(ValueError, match="Duplicate candle"):
        service.detect([*candles, candles[0]])


def test_rejects_mixed_symbols():
    candles = baseline_candles()
    candles.append(
        make_candle(
            3,
            open_price="100",
            high="132",
            low="99",
            close="130",
            symbol="ETHUSDT",
        )
    )

    service = DisplacementDetectionService(
        DisplacementDetectionConfig(atr_period=3)
    )

    with pytest.raises(ValueError, match="same symbol"):
        service.detect(candles)


def test_empty_input_returns_empty_list():
    service = DisplacementDetectionService()

    assert service.detect([]) == []


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        DisplacementDetectionConfig(atr_period=0)

    with pytest.raises(ValueError):
        DisplacementDetectionConfig(
            min_body_ratio=Decimal("1.5")
        )

    with pytest.raises(ValueError):
        DisplacementDetectionConfig(
            min_range_expansion_atr=Decimal("0")
        )