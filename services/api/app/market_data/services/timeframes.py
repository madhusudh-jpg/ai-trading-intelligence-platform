

from datetime import UTC, datetime, timedelta

from app.market_data.schemas.market_data import Timeframe

FIXED_INTERVALS = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
}


def is_candle_open_aligned(
    open_time: datetime,
    timeframe: Timeframe,
) -> bool:
    """Check whether a timestamp is a valid UTC candle opening."""

    if open_time.tzinfo is None or open_time.utcoffset() is None:
        raise ValueError("open_time must be timezone-aware")

    value = open_time.astimezone(UTC)

    if timeframe == Timeframe.MN1:
        return (
            value.day == 1
            and value.hour == 0
            and value.minute == 0
            and value.second == 0
            and value.microsecond == 0
        )

    if timeframe == Timeframe.W1:
        return (
            value.weekday() == 0
            and value.hour == 0
            and value.minute == 0
            and value.second == 0
            and value.microsecond == 0
        )

    interval = FIXED_INTERVALS.get(timeframe)

    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (value - epoch) % interval == timedelta(0)


def next_candle_open(
    open_time: datetime,
    timeframe: Timeframe,
) -> datetime:
    """Calculate the next candle opening in UTC."""

    if open_time.tzinfo is None or open_time.utcoffset() is None:
        raise ValueError("open_time must be timezone-aware")

    utc_time = open_time.astimezone(UTC)

    if timeframe in FIXED_INTERVALS:
        return utc_time + FIXED_INTERVALS[timeframe]

    if timeframe == Timeframe.MN1:
        if utc_time.month == 12:
            return utc_time.replace(
                year=utc_time.year + 1,
                month=1,
                day=1,
            )

        return utc_time.replace(
            month=utc_time.month + 1,
            day=1,
        )

    raise ValueError(f"Unsupported timeframe: {timeframe}")
