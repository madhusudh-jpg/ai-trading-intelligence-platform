
import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.market_data.providers.binance import BinanceProvider
from app.market_data.schemas.market_data import (
    AssetClass,
    CandleQuery,
    Timeframe,
)


def aligned_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def make_kline_row(
    open_time: datetime,
    close_time: datetime,
) -> list:
    return [
        int(open_time.timestamp() * 1000),
        "75000.00",
        "75100.00",
        "74900.00",
        "75050.00",
        "10.50",
        int(close_time.timestamp() * 1000) - 1,
    ]


def test_completed_candle_is_marked_complete() -> None:
    provider = BinanceProvider()
    now = datetime.now(UTC)
    open_time = aligned_hour(now) - timedelta(hours=2)
    close_time = open_time + timedelta(hours=1)

    row = make_kline_row(open_time, close_time)

    candle = provider._parse_candle(
        "BTCUSDT",
        Timeframe.H1,
        row,
    )

    assert candle.is_complete is True


def test_forming_candle_is_marked_incomplete() -> None:
    provider = BinanceProvider()
    now = datetime.now(UTC)
    open_time = aligned_hour(now)
    close_time = open_time + timedelta(hours=1)

    row = make_kline_row(open_time, close_time)

    candle = provider._parse_candle(
        "BTCUSDT",
        Timeframe.H1,
        row,
    )

    assert candle.is_complete is False


def test_historical_request_uses_exclusive_end_time(
    monkeypatch,
) -> None:
    provider = BinanceProvider()

    start_time = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    end_time = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)

    captured_params = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            captured_params.update(params)
            return FakeResponse()

    monkeypatch.setattr(
        "app.market_data.providers.binance.httpx.AsyncClient",
        FakeAsyncClient,
    )

    query = CandleQuery(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        start_time=start_time,
        end_time=end_time,
        limit=10,
    )

    asyncio.run(provider.get_historical_candles(query))

    expected_end_time = (
        int(end_time.timestamp() * 1000) - 1
    )

    assert captured_params["endTime"] == expected_end_time


def test_historical_request_excludes_candle_at_end_boundary(
    monkeypatch,
) -> None:
    provider = BinanceProvider()

    start_time = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    end_time = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)

    valid_row = make_kline_row(
        open_time=start_time,
        close_time=end_time,
    )

    out_of_range_row = make_kline_row(
        open_time=end_time,
        close_time=end_time + timedelta(hours=1),
    )

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [valid_row, out_of_range_row]

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            return FakeResponse()

    monkeypatch.setattr(
        "app.market_data.providers.binance.httpx.AsyncClient",
        FakeAsyncClient,
    )

    query = CandleQuery(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        start_time=start_time,
        end_time=end_time,
        limit=10,
    )

    candles = asyncio.run(
        provider.get_historical_candles(query)
    )

    assert len(candles) == 1
    assert candles[0].open_time == start_time
    assert candles[0].close_time == end_time


def test_websocket_reconnects_after_connection_failure(
    monkeypatch,
) -> None:
    provider = BinanceProvider()

    now = datetime.now(UTC)
    open_time = aligned_hour(now)
    close_time = open_time + timedelta(hours=1)

    query = CandleQuery(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        limit=10,
    )

    attempts = []
    sleep_delays = []

    timestamp = int(open_time.timestamp() * 1000)

    message = json.dumps(
        {
            "k": {
                "t": timestamp,
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
        def __aiter__(self):
            self.messages = iter([message])
            return self

        async def __anext__(self):
            try:
                return next(self.messages)
            except StopIteration:
                raise StopAsyncIteration from None

    class FakeConnection:
        async def __aenter__(self):
            return FakeWebSocket()

        async def __aexit__(self, *args):
            return False

    def fake_connect(*args, **kwargs):
        attempts.append(True)

        if len(attempts) == 1:
            raise OSError("Simulated connection failure")

        return FakeConnection()

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(
        "app.market_data.providers.binance.websockets.connect",
        fake_connect,
    )

    monkeypatch.setattr(
        "app.market_data.providers.binance.asyncio.sleep",
        fake_sleep,
    )

    async def run_test():
        stream = provider.stream_candles(query)

        try:
            candle = await anext(stream)
        finally:
            await stream.aclose()

        return candle

    candle = asyncio.run(run_test())

    assert len(attempts) == 2
    assert sleep_delays == [1]
    assert candle.symbol == "BTCUSDT"
    assert candle.provider == "binance"
    assert candle.is_complete is False
