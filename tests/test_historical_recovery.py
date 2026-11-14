
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.market_data.schemas.market_data import (
    AssetClass,
    CandleQuery,
    Timeframe,
)
from app.market_data.services.historical_recovery_service import (
    HistoricalRecoveryService,
)

BASE_TIME = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
PROVIDER_SYMBOL_ID = uuid4()


def make_query():
    return CandleQuery(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        start_time=BASE_TIME,
        end_time=BASE_TIME + timedelta(hours=5),
        limit=100,
    )


def make_database():
    mapping = SimpleNamespace(id=PROVIDER_SYMBOL_ID)

    db = MagicMock()
    db.scalars.return_value.all.return_value = [mapping]

    return db


def make_service():
    service = HistoricalRecoveryService(MagicMock())

    service.gap_detector.find_missing_candles = MagicMock()
    service.ingestion_service.ingest_missing_range = AsyncMock()

    return service


def run_recovery(service, db, query):
    return asyncio.run(
        service.recover_missing_candles(
            db=db,
            provider_name="binance",
            query=query,
            as_of=BASE_TIME + timedelta(hours=6),
        )
    )


def test_no_gaps_does_not_trigger_ingestion():
    service = make_service()
    db = make_database()
    query = make_query()

    report = {
        "missing_count": 0,
        "missing_ranges": [],
    }

    service.gap_detector.find_missing_candles.return_value = report

    result = run_recovery(service, db, query)

    assert result["initial_missing_count"] == 0
    assert result["ranges_attempted"] == 0
    assert result["received"] == 0
    assert result["upserted"] == 0
    assert result["remaining_missing_count"] == 0
    assert result["recovery_complete"] is True

    service.ingestion_service.ingest_missing_range.assert_not_called()


def test_single_missing_range_is_recovered():
    service = make_service()
    db = make_database()
    query = make_query()

    missing_range = {
        "start_time": BASE_TIME + timedelta(hours=2),
        "end_time": BASE_TIME + timedelta(hours=3),
    }

    service.gap_detector.find_missing_candles.side_effect = [
        {
            "missing_count": 1,
            "missing_ranges": [missing_range],
        },
        {
            "missing_count": 0,
            "missing_ranges": [],
        },
    ]

    service.ingestion_service.ingest_missing_range.return_value = {
        "provider": "binance",
        "received": 1,
        "upserted": 1,
    }

    result = run_recovery(service, db, query)

    assert result["initial_missing_count"] == 1
    assert result["ranges_attempted"] == 1
    assert result["received"] == 1
    assert result["upserted"] == 1
    assert result["remaining_missing_count"] == 0
    assert result["recovery_complete"] is True

    service.ingestion_service.ingest_missing_range.assert_awaited_once_with(
        db=db,
        provider_name="binance",
        query=query,
        start_time=missing_range["start_time"],
        end_time=missing_range["end_time"],
    )


def test_multiple_missing_ranges_are_recovered():
    service = make_service()
    db = make_database()
    query = make_query()

    first_range = {
        "start_time": BASE_TIME + timedelta(hours=1),
        "end_time": BASE_TIME + timedelta(hours=2),
    }

    second_range = {
        "start_time": BASE_TIME + timedelta(hours=3),
        "end_time": BASE_TIME + timedelta(hours=4),
    }

    service.gap_detector.find_missing_candles.side_effect = [
        {
            "missing_count": 2,
            "missing_ranges": [first_range, second_range],
        },
        {
            "missing_count": 0,
            "missing_ranges": [],
        },
    ]

    service.ingestion_service.ingest_missing_range.side_effect = [
        {
            "provider": "binance",
            "received": 1,
            "upserted": 1,
        },
        {
            "provider": "binance",
            "received": 1,
            "upserted": 1,
        },
    ]

    result = run_recovery(service, db, query)

    assert result["initial_missing_count"] == 2
    assert result["ranges_attempted"] == 2
    assert result["received"] == 2
    assert result["upserted"] == 2
    assert result["remaining_missing_count"] == 0
    assert result["recovery_complete"] is True

    assert (
        service.ingestion_service.ingest_missing_range.await_count
        == 2
    )


def test_remaining_gaps_are_reported():
    service = make_service()
    db = make_database()
    query = make_query()

    missing_range = {
        "start_time": BASE_TIME + timedelta(hours=2),
        "end_time": BASE_TIME + timedelta(hours=3),
    }

    remaining_range = {
        "start_time": BASE_TIME + timedelta(hours=2),
        "end_time": BASE_TIME + timedelta(hours=3),
    }

    service.gap_detector.find_missing_candles.side_effect = [
        {
            "missing_count": 1,
            "missing_ranges": [missing_range],
        },
        {
            "missing_count": 1,
            "missing_ranges": [remaining_range],
        },
    ]

    service.ingestion_service.ingest_missing_range.return_value = {
        "provider": "binance",
        "received": 0,
        "upserted": 0,
    }

    result = run_recovery(service, db, query)

    assert result["initial_missing_count"] == 1
    assert result["remaining_missing_count"] == 1
    assert result["recovery_complete"] is False
    assert result["remaining_missing_ranges"] == [remaining_range]


def test_unsupported_provider_is_rejected():
    service = make_service()
    db = make_database()
    query = make_query()

    with pytest.raises(ValueError, match="Binance only"):
        asyncio.run(
            service.recover_missing_candles(
                db=db,
                provider_name="other_provider",
                query=query,
            )
        )

    db.scalars.assert_not_called()
    service.ingestion_service.ingest_missing_range.assert_not_called()
