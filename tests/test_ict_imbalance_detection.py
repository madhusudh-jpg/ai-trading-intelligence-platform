
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ict_detection.imbalance_schemas import (
    ImbalanceDirection,
    ImbalanceStatus,
)
from app.ict_detection.services.imbalance_detection_service import (
    ImbalanceDetectionService,
)
from app.market_data.schemas.market_data import Candle

BASE_TIME = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=15)


def make_candle(
    index: int,
    open_price: str,
    high: str,
    low: str,
    close: str,
    *,
    is_complete: bool = True,
) -> Candle:
    open_time = BASE_TIME + index * INTERVAL

    return Candle(
        symbol="BTCUSDT",
        asset_class="crypto",
        timeframe="15m",
        open_time=open_time,
        close_time=open_time + INTERVAL,
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        is_complete=is_complete,
        provider="binance",
    )


def bullish_fvg_candles() -> list[Candle]:
    return [
        make_candle(0, "100", "105", "98", "103"),
        make_candle(1, "103", "110", "102", "109"),
        make_candle(2, "109", "115", "106", "113"),
    ]


def bearish_fvg_candles() -> list[Candle]:
    return [
        make_candle(0, "110", "112", "105", "107"),
        make_candle(1, "107", "108", "98", "99"),
        make_candle(2, "99", "104", "95", "97"),
    ]


def overlapping_fvg_candles() -> list[Candle]:
    return [
        make_candle(0, "100", "105", "98", "103"),
        make_candle(1, "103", "110", "102", "109"),
        make_candle(2, "109", "115", "106", "113"),
        make_candle(3, "113", "114", "106.5", "110"),
        make_candle(4, "110", "112", "100", "102"),
        make_candle(5, "102", "105.5", "99", "104"),
    ]


@pytest.fixture
def service() -> ImbalanceDetectionService:
    return ImbalanceDetectionService()


def test_detects_bullish_fvg(service):
    fvgs = service.detect_fvgs(bullish_fvg_candles())

    assert len(fvgs) == 1

    fvg = fvgs[0]

    assert fvg.direction == ImbalanceDirection.BULLISH
    assert fvg.lower_bound == Decimal("105")
    assert fvg.upper_bound == Decimal("106")
    assert fvg.gap_size == Decimal("1")
    assert fvg.consequent_encroachment == Decimal("105.5")


def test_detects_bearish_fvg(service):
    fvgs = service.detect_fvgs(bearish_fvg_candles())

    assert len(fvgs) == 1

    fvg = fvgs[0]

    assert fvg.direction == ImbalanceDirection.BEARISH
    assert fvg.lower_bound == Decimal("104")
    assert fvg.upper_bound == Decimal("105")
    assert fvg.gap_size == Decimal("1")
    assert fvg.consequent_encroachment == Decimal("104.5")


def test_does_not_detect_fvg_when_boundaries_touch(service):
    candles = [
        make_candle(0, "100", "105", "98", "103"),
        make_candle(1, "103", "108", "102", "107"),
        make_candle(2, "107", "112", "105", "110"),
    ]

    fvgs = service.detect_fvgs(candles)

    assert fvgs == []


def test_ignores_fvg_below_minimum_gap_size():
    from app.ict_detection.imbalance_schemas import (
        ImbalanceDetectionConfig,
    )

    config = ImbalanceDetectionConfig(
        minimum_gap_size=Decimal("2"),
    )
    service = ImbalanceDetectionService(config=config)

    fvgs = service.detect_fvgs(bullish_fvg_candles())

    assert fvgs == []


def test_ignores_incomplete_candles(service):
    candles = [
        make_candle(0, "100", "105", "98", "103"),
        make_candle(1, "103", "110", "102", "109"),
        make_candle(
            2,
            "109",
            "115",
            "106",
            "113",
            is_complete=False,
        ),
    ]

    assert service.detect_fvgs(candles) == []


def test_candle_gap_breaks_fvg_sequence(service):
    candles = [
        make_candle(0, "100", "105", "98", "103"),
        make_candle(1, "103", "110", "102", "109"),
        make_candle(3, "109", "115", "106", "113"),
    ]

    assert service.detect_fvgs(candles) == []


def test_rejects_duplicate_candle_timestamps(service):
    candles = bullish_fvg_candles()
    candles.append(candles[-1])

    with pytest.raises(ValueError):
        service.detect_fvgs(candles)


def test_detects_bearish_ifvg_after_bullish_fvg(service):
    candles = bullish_fvg_candles()
    candles.append(
        make_candle(3, "106", "107", "103", "104")
    )

    fvgs = service.detect_fvgs(candles)
    ifvgs = service.detect_ifvgs(candles, fvgs)

    assert len(fvgs) == 1
    assert len(ifvgs) == 1
    assert ifvgs[0].inverse_direction == ImbalanceDirection.BEARISH


def test_detects_bullish_ifvg_after_bearish_fvg(service):
    candles = bearish_fvg_candles()
    candles.append(
        make_candle(3, "104", "106", "103", "106")
    )

    fvgs = service.detect_fvgs(candles)
    ifvgs = service.detect_ifvgs(candles, fvgs)

    assert len(fvgs) == 1
    assert len(ifvgs) == 1
    assert ifvgs[0].inverse_direction == ImbalanceDirection.BULLISH


def test_wick_only_breach_does_not_confirm_ifvg(service):
    candles = bullish_fvg_candles()
    candles.append(
        make_candle(3, "106", "107", "103", "106")
    )

    fvgs = service.detect_fvgs(candles)
    ifvgs = service.detect_ifvgs(candles, fvgs)

    assert len(fvgs) == 1
    assert ifvgs == []


def test_detects_bpr_from_overlapping_opposite_fvgs(service):
    candles = overlapping_fvg_candles()

    fvgs = service.detect_fvgs(candles)
    bprs = service.detect_bprs(fvgs)

    assert len(fvgs) == 2
    assert len(bprs) == 1

    bpr = bprs[0]

    assert bpr.lower_bound == Decimal("105.5")
    assert bpr.upper_bound == Decimal("106")
    assert bpr.overlap_size == Decimal("0.5")
    assert bpr.consequent_encroachment == Decimal("105.75")


def test_does_not_detect_bpr_without_overlap(service):
    candles = [
        make_candle(0, "100", "105", "98", "103"),
        make_candle(1, "103", "110", "102", "109"),
        make_candle(2, "109", "115", "106", "113"),
        make_candle(3, "113", "114", "104", "105"),
        make_candle(4, "105", "108", "95", "97"),
        make_candle(5, "97", "102", "90", "95"),
    ]

    fvgs = service.detect_fvgs(candles)
    bprs = service.detect_bprs(fvgs)

    assert bprs == []


def test_fvg_confirmation_occurs_at_third_candle_close(service):
    candles = bullish_fvg_candles()

    fvgs = service.detect_fvgs(candles)

    assert len(fvgs) == 1
    assert fvgs[0].confirmed_at == candles[2].close_time


def test_fvg_has_active_initial_status(service):
    fvgs = service.detect_fvgs(bullish_fvg_candles())

    assert len(fvgs) == 1
    assert fvgs[0].status == ImbalanceStatus.ACTIVE


def test_detect_returns_all_three_imbalance_results(service):
    candles = overlapping_fvg_candles()

    fvgs, ifvgs, bprs = service.detect(candles)

    assert len(fvgs) == 2
    assert isinstance(ifvgs, list)
    assert len(bprs) == 1
