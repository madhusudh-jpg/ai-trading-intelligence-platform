
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ict_detection.liquidity_schemas import (
    LiquidityDetectionConfig,
    LiquidityPoolStatus,
    LiquidityPoolType,
)
from app.ict_detection.schemas import (
    SwingConfirmationBasis,
    SwingPoint,
    SwingTier,
    SwingType,
)
from app.ict_detection.services.liquidity_detection_service import (
    LiquidityDetectionService,
)
from app.ict_detection.structure_break_schemas import LiquiditySide
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    Timeframe,
)

BASE_TIME = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)


def make_swing(
    swing_type: SwingType,
    price: str,
    pivot_minutes: int,
    segment_id: int = 0,
) -> SwingPoint:
    pivot_time = BASE_TIME + timedelta(minutes=pivot_minutes)

    return SwingPoint(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.M15,
        provider="binance",
        swing_type=swing_type,
        tier=SwingTier.SHORT_TERM,
        price=Decimal(price),
        pivot_time=pivot_time,
        confirmed_at=pivot_time + timedelta(minutes=30),
        pivot_index=pivot_minutes // 15,
        segment_id=segment_id,
        left_bars=2,
        right_bars=2,
        hierarchy_count=1,
        confirmation_basis=SwingConfirmationBasis.FRACTAL,
    )


def make_candle(
    open_minutes: int,
    high: str,
    low: str,
    close: str,
    is_complete: bool = True,
) -> Candle:
    open_time = BASE_TIME + timedelta(minutes=open_minutes)

    return Candle(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.M15,
        provider="binance",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=15),
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("10"),
        is_complete=is_complete,
    )


def make_service() -> LiquidityDetectionService:
    return LiquidityDetectionService(
        LiquidityDetectionConfig(
            price_tolerance=Decimal("0.10"),
            minimum_touches=2,
        )
    )


def test_detects_equal_highs():
    service = make_service()

    swings = [
        make_swing(SwingType.HIGH, "100.00", 0),
        make_swing(SwingType.HIGH, "100.05", 60),
    ]

    pools = service.detect_pools(swings)

    assert len(pools) == 1

    pool = pools[0]

    assert pool.pool_type == LiquidityPoolType.EQUAL_HIGHS
    assert pool.liquidity_side == LiquiditySide.BUY_SIDE
    assert pool.swing_type == SwingType.HIGH
    assert pool.status == LiquidityPoolStatus.CONFIRMED
    assert len(pool.swing_points) == 2


def test_detects_equal_lows():
    service = make_service()

    swings = [
        make_swing(SwingType.LOW, "90.00", 0),
        make_swing(SwingType.LOW, "90.05", 60),
    ]

    pools = service.detect_pools(swings)

    assert len(pools) == 1

    pool = pools[0]

    assert pool.pool_type == LiquidityPoolType.EQUAL_LOWS
    assert pool.liquidity_side == LiquiditySide.SELL_SIDE
    assert pool.swing_type == SwingType.LOW
    assert pool.status == LiquidityPoolStatus.CONFIRMED
    assert len(pool.swing_points) == 2


def test_single_swing_creates_candidate_pool():
    service = make_service()

    swings = [
        make_swing(SwingType.HIGH, "100.00", 0),
    ]

    pools = service.detect_pools(swings)

    assert len(pools) == 1
    assert pools[0].status == LiquidityPoolStatus.CANDIDATE
    assert pools[0].confirmed_at is None


def test_swings_outside_tolerance_form_separate_pools():
    service = make_service()

    swings = [
        make_swing(SwingType.HIGH, "100.00", 0),
        make_swing(SwingType.HIGH, "101.00", 60),
    ]

    pools = service.detect_pools(swings)

    assert len(pools) == 2
    assert all(
        pool.status == LiquidityPoolStatus.CANDIDATE
        for pool in pools
    )


def test_detects_bullish_sweep_of_sell_side_liquidity():
    service = make_service()

    swings = [
        make_swing(SwingType.LOW, "90.00", 0),
        make_swing(SwingType.LOW, "90.05", 60),
    ]

    pools = service.detect_pools(swings)

    candle = make_candle(
        open_minutes=120,
        high="92.00",
        low="89.00",
        close="91.00",
    )

    events = service.detect_sweeps([candle], pools)

    assert len(events) == 1
    assert events[0].liquidity_side == LiquiditySide.SELL_SIDE
    assert events[0].swept_price == Decimal("89.00")


def test_detects_bearish_sweep_of_buy_side_liquidity():
    service = make_service()

    swings = [
        make_swing(SwingType.HIGH, "100.00", 0),
        make_swing(SwingType.HIGH, "100.05", 60),
    ]

    pools = service.detect_pools(swings)

    candle = make_candle(
        open_minutes=120,
        high="101.00",
        low="98.00",
        close="99.00",
    )

    events = service.detect_sweeps([candle], pools)

    assert len(events) == 1
    assert events[0].liquidity_side == LiquiditySide.BUY_SIDE
    assert events[0].swept_price == Decimal("101.00")


def test_ignores_incomplete_sweep_candle():
    service = make_service()

    swings = [
        make_swing(SwingType.LOW, "90.00", 0),
        make_swing(SwingType.LOW, "90.05", 60),
    ]

    pools = service.detect_pools(swings)

    candle = make_candle(
        open_minutes=120,
        high="92.00",
        low="89.00",
        close="91.00",
        is_complete=False,
    )

    events = service.detect_sweeps([candle], pools)

    assert events == []


def test_ignores_candle_before_pool_confirmation():
    service = make_service()

    swings = [
        make_swing(SwingType.LOW, "90.00", 0),
        make_swing(SwingType.LOW, "90.05", 60),
    ]

    pools = service.detect_pools(swings)

    candle = make_candle(
        open_minutes=75,
        high="92.00",
        low="89.00",
        close="91.00",
    )

    events = service.detect_sweeps([candle], pools)

    assert events == []


def test_rejects_duplicate_candle_timestamps():
    service = make_service()

    candle = make_candle(
        open_minutes=120,
        high="92.00",
        low="89.00",
        close="91.00",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate candle timestamps",
    ):
        service.detect_sweeps([candle, candle], [])


def test_rejects_mixed_swing_market_streams():
    service = make_service()

    first = make_swing(SwingType.HIGH, "100.00", 0)
    second = make_swing(
        SwingType.HIGH,
        "100.05",
        60,
    ).model_copy(
        update={"symbol": "ETHUSDT"}
    )

    with pytest.raises(
        ValueError,
        match="same market stream",
    ):
        service.detect_pools([first, second])
