
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    CandleQuery,
    Timeframe,
)
from app.market_data.services.market_data_service import (
    MarketDataService,
)

OPEN_TIME = datetime(2026, 11, 3, 0, 0, tzinfo=UTC)


def make_candle() -> Candle:
    return Candle(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        open_time=OPEN_TIME,
        close_time=datetime(2026, 11, 3, 1, 0, tzinfo=UTC),
        open=Decimal("76816.01"),
        high=Decimal("77253.58"),
        low=Decimal("76663.90"),
        close=Decimal("77128.01"),
        volume=Decimal("500.66789"),
        is_complete=False,
        provider="binance",
    )


def make_query() -> CandleQuery:
    return CandleQuery(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        start_time=OPEN_TIME,
        end_time=datetime(2026, 11, 3, 1, 0, tzinfo=UTC),
        limit=1,
    )


class FakeProvider:
    name = "binance"

    def __init__(self, candles):
        self.candles = candles
        self.events = []
        self.stream_closed = False

    async def get_status(self):
        raise NotImplementedError

    async def get_historical_candles(self, query):
        return self.candles

    async def stream_candles(self, query):
        try:
            for candle in self.candles:
                self.events.append("provider")
                yield candle
        finally:
            self.stream_closed = True
            self.events.append("stream_closed")


class FakeIngestionService:
    def __init__(self, events, should_fail=False):
        self.events = events
        self.should_fail = should_fail
        self.persisted = []

    def ingest_live_candle(self, db, provider_name, candle):
        self.events.append("persist")
        self.persisted.append((provider_name, candle))

        if self.should_fail:
            raise RuntimeError("Simulated database failure")

        return {
            "provider": provider_name,
            "received": 1,
            "upserted": 1,
            "skipped": 0,
        }


def build_service(provider, session_factory):
    registry = ProviderRegistry()
    registry.register(provider)

    return MarketDataService(
        registry=registry,
        session_factory=session_factory,
    )


def test_candle_is_persisted_before_being_yielded():
    async def run_test():
        candle = make_candle()
        events = []

        provider = FakeProvider([candle])
        provider.events = events

        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        service = build_service(provider, session_factory)
        service.ingestion_service = FakeIngestionService(events)

        received = []

        async for item in service.stream_and_persist_candles(
            "binance", make_query()
        ):
            events.append("consumer")
            received.append(item)

        assert received == [candle]
        assert events.index("persist") < events.index("consumer")
        assert provider.stream_closed is True
        db.close.assert_called_once()

    asyncio.run(run_test())


def test_database_session_closes_when_ingestion_fails():
    async def run_test():
        provider = FakeProvider([make_candle()])

        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        service = build_service(provider, session_factory)
        service.ingestion_service = FakeIngestionService(
            [], should_fail=True
        )

        with pytest.raises(RuntimeError, match="Simulated database failure"):
            async for _ in service.stream_and_persist_candles(
                "binance", make_query()
            ):
                pass

        db.close.assert_called_once()
        assert provider.stream_closed is True

    asyncio.run(run_test())


def test_provider_stream_closes_when_consumer_stops_early():
    async def run_test():
        provider = FakeProvider([make_candle(), make_candle()])

        db = MagicMock()
        session_factory = MagicMock(return_value=db)

        service = build_service(provider, session_factory)
        service.ingestion_service = FakeIngestionService([])

        stream = service.stream_and_persist_candles(
            "binance", make_query()
        )

        first = await anext(stream)

        assert first == make_candle()
        assert provider.stream_closed is False

        await stream.aclose()

        assert provider.stream_closed is True
        db.close.assert_called_once()

    asyncio.run(run_test())


def test_transient_database_failure_retries_with_fresh_sessions(
    monkeypatch,
):
    provider = FakeProvider([])
    sessions = [MagicMock(), MagicMock(), MagicMock()]
    session_factory = MagicMock(side_effect=sessions)

    service = build_service(provider, session_factory)

    class RecoveringIngestionService:
        def __init__(self):
            self.attempts = 0

        def ingest_live_candle(self, db, provider_name, candle):
            self.attempts += 1

            if self.attempts < 3:
                raise OperationalError(
                    "INSERT",
                    {},
                    Exception("Temporary database connection failure"),
                )

            return {
                "provider": provider_name,
                "received": 1,
                "upserted": 1,
                "skipped": 0,
            }

    service.ingestion_service = RecoveringIngestionService()

    delays = []
    monkeypatch.setattr(
        "app.market_data.services.market_data_service.time.sleep",
        delays.append,
    )

    result = service._persist_live_candle(
        "binance",
        make_candle(),
    )

    assert result["upserted"] == 1
    assert session_factory.call_count == 3
    assert delays == [1, 2]

    for session in sessions:
        session.close.assert_called_once()


def test_database_retry_stops_after_maximum_attempts(monkeypatch):
    provider = FakeProvider([])
    sessions = [MagicMock() for _ in range(4)]
    session_factory = MagicMock(side_effect=sessions)

    service = build_service(provider, session_factory)

    class FailingIngestionService:
        def ingest_live_candle(self, db, provider_name, candle):
            raise OperationalError(
                "INSERT",
                {},
                Exception("Database unavailable"),
            )

    service.ingestion_service = FailingIngestionService()

    delays = []
    monkeypatch.setattr(
        "app.market_data.services.market_data_service.time.sleep",
        delays.append,
    )

    with pytest.raises(OperationalError):
        service._persist_live_candle(
            "binance",
            make_candle(),
        )

    assert session_factory.call_count == 4
    assert delays == [1, 2, 4]

    for session in sessions:
        session.close.assert_called_once()
