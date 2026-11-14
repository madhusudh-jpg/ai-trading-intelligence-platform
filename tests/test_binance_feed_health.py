
import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.market_data.providers.binance import BinanceProvider
from app.market_data.schemas.market_data import (
    AssetClass,
    CandleQuery,
    DataStatus,
    Timeframe,
)
from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)


def make_query() -> CandleQuery:
    now = datetime.now(UTC)
    open_time = now.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    return CandleQuery(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        start_time=open_time - timedelta(hours=1),
        end_time=open_time + timedelta(hours=1),
        limit=10,
    )


def make_message() -> str:
    now = datetime.now(UTC)
    open_time = now.replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    close_time = open_time + timedelta(hours=1)

    return json.dumps(
        {
            "k": {
                "t": int(open_time.timestamp() * 1000),
                "T": int(close_time.timestamp() * 1000) - 1,
                "o": "75000.00",
                "h": "75100.00",
                "l": "74900.00",
                "c": "75050.00",
                "v": "10.50",
                "x": False,
            }
        }
    )


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.messages)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeConnection:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, *args):
        return False


def test_websocket_records_candle_and_disconnects_on_close(
    monkeypatch,
):
    tracker = FeedHealthTracker()
    provider = BinanceProvider(
        health_tracker=tracker,
        message_timeout_seconds=5,
    )

    websocket = FakeWebSocket([make_message()])

    monkeypatch.setattr(
        "app.market_data.providers.binance.websockets.connect",
        lambda *args, **kwargs: FakeConnection(websocket),
    )

    async def run_test():
        stream = provider.stream_candles(make_query())

        try:
            candle = await anext(stream)
        finally:
            await stream.aclose()

        return candle

    candle = asyncio.run(run_test())

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert candle.symbol == "BTCUSDT"
    assert feed is not None
    assert feed.connected is False
    assert feed.last_message_at is not None
    assert feed.last_candle_at is not None
    assert feed.last_completed_candle_at is None
    assert feed.data_status == DataStatus.UNAVAILABLE


def test_silent_websocket_disconnects_and_triggers_retry(
    monkeypatch,
):
    tracker = FeedHealthTracker()
    provider = BinanceProvider(
        health_tracker=tracker,
        message_timeout_seconds=0.01,
    )

    attempts = []

    class SilentWebSocket:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()

    def fake_connect(*args, **kwargs):
        attempts.append(True)
        return FakeConnection(SilentWebSocket())

    async def fake_sleep(delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.market_data.providers.binance.websockets.connect",
        fake_connect,
    )

    monkeypatch.setattr(
        "app.market_data.providers.binance.asyncio.sleep",
        fake_sleep,
    )

    async def run_test():
        stream = provider.stream_candles(make_query())

        with pytest.raises(asyncio.CancelledError):
            await anext(stream)

    asyncio.run(run_test())

    feed = tracker.get_feed("binance", "BTCUSDT", "1h")

    assert len(attempts) == 1
    assert feed is not None
    assert feed.connected is False
    assert feed.data_status == DataStatus.UNAVAILABLE
