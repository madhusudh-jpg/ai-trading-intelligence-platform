
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    DataStatus,
    Timeframe,
)
from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, current_time: datetime):
        self.current_time = current_time

    def __call__(self) -> datetime:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += timedelta(seconds=seconds)


def make_candle(
    is_complete: bool = False,
) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        open_time=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
        close_time=datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("10"),
        is_complete=is_complete,
        provider="binance",
    )


def test_mark_connected_creates_feed():
    tracker = FeedHealthTracker()

    tracker.mark_connected("binance", "BTCUSDT", "1h")

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.connected is True
    assert feed.message == "Live stream connected."


def test_mark_disconnected_updates_feed():
    tracker = FeedHealthTracker()

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.mark_disconnected("binance", "BTCUSDT", "1h")

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.connected is False
    assert feed.data_status == DataStatus.UNAVAILABLE


def test_record_message_normalizes_timestamp_to_utc():
    tracker = FeedHealthTracker()

    tracker.record_message(
        "binance",
        "BTCUSDT",
        "1h",
        received_at=NOW,
    )

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.last_message_at == NOW


def test_record_message_rejects_naive_timestamp():
    tracker = FeedHealthTracker()

    with pytest.raises(ValueError, match="timezone-aware"):
        tracker.record_message(
            "binance",
            "BTCUSDT",
            "1h",
            received_at=datetime(2026, 11, 12, 10, 0),
        )


def test_record_candle_updates_message_and_candle_timestamps():
    tracker = FeedHealthTracker()
    candle = make_candle()

    tracker.record_candle(candle, received_at=NOW)

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.last_message_at == NOW
    assert feed.last_candle_at == NOW
    assert feed.last_completed_candle_at is None
    assert feed.data_status == DataStatus.REALTIME


def test_record_completed_candle_updates_completion_timestamp():
    tracker = FeedHealthTracker()
    candle = make_candle(is_complete=True)

    tracker.record_candle(candle, received_at=NOW)

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.last_completed_candle_at == candle.close_time


def test_feeds_are_tracked_independently():
    tracker = FeedHealthTracker()

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.mark_connected("binance", "ETHUSDT", "1h")

    btc_feed = tracker.get_feed("binance", "BTCUSDT", "1h")
    eth_feed = tracker.get_feed("binance", "ETHUSDT", "1h")

    assert btc_feed is not None
    assert eth_feed is not None
    assert btc_feed.symbol == "BTCUSDT"
    assert eth_feed.symbol == "ETHUSDT"


def test_provider_symbol_and_timeframe_are_normalized():
    tracker = FeedHealthTracker()

    tracker.mark_connected(" BINANCE ", "btcusdt", "1H")

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.provider == "binance"
    assert feed.symbol == "BTCUSDT"
    assert feed.timeframe == "1h"


def test_get_all_feeds_returns_tracked_feeds():
    tracker = FeedHealthTracker()

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.mark_connected("binance", "ETHUSDT", "1h")

    feeds = tracker.get_all_feeds()

    assert len(feeds) == 2
    assert {feed.symbol for feed in feeds} == {
        "BTCUSDT",
        "ETHUSDT",
    }


def test_evaluate_feed_reports_realtime():
    clock = FakeClock(NOW)
    tracker = FeedHealthTracker(clock=clock)

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    clock.advance(20)

    feed = tracker.evaluate_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.data_status == DataStatus.REALTIME


def test_evaluate_feed_reports_delayed():
    clock = FakeClock(NOW)
    tracker = FeedHealthTracker(clock=clock)

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    clock.advance(45)

    feed = tracker.evaluate_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.data_status == DataStatus.DELAYED


def test_evaluate_feed_reports_stale():
    clock = FakeClock(NOW)
    tracker = FeedHealthTracker(clock=clock)

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    clock.advance(90)

    feed = tracker.evaluate_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.data_status == DataStatus.STALE


def test_evaluate_feed_reports_unavailable_when_disconnected():
    clock = FakeClock(NOW)
    tracker = FeedHealthTracker(clock=clock)

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")
    tracker.mark_disconnected("binance", "BTCUSDT", "1h")

    feed = tracker.evaluate_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.data_status == DataStatus.UNAVAILABLE


def test_evaluate_feed_reports_unavailable_before_first_message():
    tracker = FeedHealthTracker(clock=FakeClock(NOW))

    tracker.mark_connected("binance", "BTCUSDT", "1h")

    feed = tracker.evaluate_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.data_status == DataStatus.UNAVAILABLE


def test_evaluate_feed_detects_future_message_timestamp():
    clock = FakeClock(NOW)
    tracker = FeedHealthTracker(clock=clock)

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message(
        "binance",
        "BTCUSDT",
        "1h",
        received_at=NOW + timedelta(seconds=10),
    )

    feed = tracker.evaluate_feed("binance", "BTCUSDT", "1h")

    assert feed is not None
    assert feed.data_status == DataStatus.UNAVAILABLE
    assert "future" in feed.message.lower()


def test_evaluate_all_checks_every_feed():
    clock = FakeClock(NOW)
    tracker = FeedHealthTracker(clock=clock)

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.mark_connected("binance", "ETHUSDT", "1h")

    tracker.record_message("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "ETHUSDT", "1h")

    clock.advance(90)

    feeds = tracker.evaluate_all()

    assert len(feeds) == 2
    assert all(feed.data_status == DataStatus.STALE for feed in feeds)


def test_tracker_rejects_invalid_thresholds():
    with pytest.raises(ValueError, match="Delayed threshold"):
        FeedHealthTracker(delayed_after_seconds=0)

    with pytest.raises(ValueError, match="Stale threshold"):
        FeedHealthTracker(
            delayed_after_seconds=60,
            stale_after_seconds=60,
        )


def test_tracker_rejects_naive_clock():
    tracker = FeedHealthTracker(
        clock=lambda: datetime(2026, 11, 12, 10, 0)
    )

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message(
        "binance",
        "BTCUSDT",
        "1h",
        received_at=NOW,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        tracker.evaluate_feed("binance", "BTCUSDT", "1h")