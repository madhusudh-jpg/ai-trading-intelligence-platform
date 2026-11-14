
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    Timeframe,
)


def make_candle(**overrides) -> Candle:
    open_time = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    values = {
        "symbol": "BTCUSDT",
        "asset_class": AssetClass.CRYPTO,
        "timeframe": Timeframe.H1,
        "open_time": open_time,
        "close_time": open_time + timedelta(hours=1),
        "open": Decimal("75000"),
        "high": Decimal("75100"),
        "low": Decimal("74900"),
        "close": Decimal("75050"),
        "volume": Decimal("10.5"),
        "is_complete": True,
        "provider": "binance",
    }

    values.update(overrides)

    return Candle(**values)


def test_valid_hourly_candle_is_accepted():
    candle = make_candle()

    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == Timeframe.H1


def test_misaligned_open_time_is_rejected():
    with pytest.raises(ValidationError, match="align"):
        make_candle(
            open_time=datetime(
                2026, 11, 12, 9, 15, tzinfo=UTC
            )
        )


def test_incorrect_close_boundary_is_rejected():
    with pytest.raises(ValidationError, match="next candle"):
        make_candle(
            close_time=datetime(
                2026, 11, 12, 9, 59, tzinfo=UTC
            )
        )


@pytest.mark.parametrize(
    "field",
    ["open", "high", "low", "close", "volume"],
)
@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_non_finite_ohlcv_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        make_candle(**{field: value})


def test_forming_candle_with_future_close_boundary_is_accepted():
    open_time = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    candle = make_candle(
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        is_complete=False,
    )

    assert candle.is_complete is False


def test_monthly_candle_uses_calendar_boundary():
    open_time = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)

    candle = make_candle(
        timeframe=Timeframe.MN1,
        open_time=open_time,
        close_time=datetime(
            2026, 12, 1, 0, 0, tzinfo=UTC
        ),
    )

    assert candle.timeframe == Timeframe.MN1


def test_weekly_candle_uses_monday_boundary():
    open_time = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)

    candle = make_candle(
        timeframe=Timeframe.W1,
        open_time=open_time,
        close_time=open_time + timedelta(weeks=1),
    )

    assert candle.timeframe == Timeframe.W1
