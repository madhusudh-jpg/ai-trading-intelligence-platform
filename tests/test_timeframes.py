
from datetime import UTC, datetime

from app.market_data.schemas.market_data import Timeframe
from app.market_data.services.timeframes import (
    is_candle_open_aligned,
    next_candle_open,
)


def test_hourly_interval():
    open_time = datetime(2027, 1, 1, 10, 0, tzinfo=UTC)

    assert next_candle_open(open_time, Timeframe.H1) == datetime(
        2027, 1, 1, 11, 0, tzinfo=UTC
    )


def test_monthly_interval_uses_calendar_boundary():
    open_time = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)

    assert next_candle_open(open_time, Timeframe.MN1) == datetime(
        2027, 2, 1, 0, 0, tzinfo=UTC
    )


def test_monthly_interval_handles_december():
    open_time = datetime(2027, 12, 1, 0, 0, tzinfo=UTC)

    assert next_candle_open(open_time, Timeframe.MN1) == datetime(
        2028, 1, 1, 0, 0, tzinfo=UTC
    )


def test_monthly_alignment():
    valid = datetime(2027, 2, 1, 0, 0, tzinfo=UTC)
    invalid = datetime(2027, 2, 28, 0, 0, tzinfo=UTC)

    assert is_candle_open_aligned(valid, Timeframe.MN1)
    assert not is_candle_open_aligned(invalid, Timeframe.MN1)


def test_hourly_alignment():
    valid = datetime(2027, 1, 1, 10, 0, tzinfo=UTC)
    invalid = datetime(2027, 1, 1, 10, 30, tzinfo=UTC)

    assert is_candle_open_aligned(valid, Timeframe.H1)
    assert not is_candle_open_aligned(invalid, Timeframe.H1)


def test_weekly_alignment():
    monday = datetime(2027, 1, 4, 0, 0, tzinfo=UTC)
    tuesday = datetime(2027, 1, 5, 0, 0, tzinfo=UTC)

    assert is_candle_open_aligned(monday, Timeframe.W1)
    assert not is_candle_open_aligned(tuesday, Timeframe.W1)
