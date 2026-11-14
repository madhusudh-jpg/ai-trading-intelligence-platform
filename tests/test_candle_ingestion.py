
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    CandleQuery,
    Timeframe,
)
from app.market_data.services.candle_ingestion_service import (
    CandleIngestionService,
)

BASE_TIME = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


class FakeProvider:
    name = "binance"

    async def get_historical_candles(self, query):
        return [
            Candle(
                symbol="BTCUSDT",
                asset_class=AssetClass.CRYPTO,
                timeframe=Timeframe.H1,
                open_time=BASE_TIME,
                close_time=datetime(
                    2026, 1, 1, 1, 0, tzinfo=UTC
                ),
                open="100",
                high="110",
                low="90",
                close="105",
                volume="10",
                is_complete=True,
                provider="binance",
            )
        ]


def build_service():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    return CandleIngestionService(registry)


def make_live_candle(
    is_complete=False,
    close="105",
):
    return Candle(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        open_time=BASE_TIME,
        close_time=datetime(
            2026, 1, 1, 1, 0, tzinfo=UTC
        ),
        open="100",
        high="110",
        low="90",
        close=close,
        volume="10",
        is_complete=is_complete,
        provider="binance",
    )


def configure_database(db):
    mapping = SimpleNamespace(
        id=uuid4(),
        instrument_id=uuid4(),
    )
    instrument = SimpleNamespace(asset_class="crypto")

    db.scalars.return_value.all.return_value = [mapping]
    db.get.return_value = instrument

    return mapping


def test_upsert_protects_finalized_candles():
    async def run_test():
        service = build_service()
        db = MagicMock()

        configure_database(db)

        query = CandleQuery(
            symbol="BTCUSDT",
            asset_class=AssetClass.CRYPTO,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=datetime(
                2026, 1, 1, 2, 0, tzinfo=UTC
            ),
            limit=10,
        )

        await service.ingest_historical_candles(
            db=db,
            provider_name="binance",
            query=query,
        )

        statement = db.execute.call_args.args[0]
        compiled = str(
            statement.compile(dialect=postgresql.dialect())
        )

        assert "ON CONFLICT" in compiled
        assert "DO UPDATE" in compiled
        assert "WHERE" in compiled
        assert "candles.is_complete IS false" in compiled
        assert "IS DISTINCT FROM" in compiled

    asyncio.run(run_test())


def test_missing_range_rejects_naive_datetime():
    async def run_test():
        service = build_service()
        db = MagicMock()

        query = CandleQuery(
            symbol="BTCUSDT",
            asset_class=AssetClass.CRYPTO,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=datetime(
                2026, 1, 1, 2, 0, tzinfo=UTC
            ),
            limit=10,
        )

        with pytest.raises(ValueError, match="timezone-aware"):
            await service.ingest_missing_range(
                db=db,
                provider_name="binance",
                query=query,
                start_time=datetime(2026, 1, 1, 0, 0),
                end_time=datetime(
                    2026, 1, 1, 1, 0, tzinfo=UTC
                ),
            )

        db.scalars.assert_not_called()

    asyncio.run(run_test())


def test_missing_range_rejects_misaligned_start():
    async def run_test():
        service = build_service()
        db = MagicMock()

        query = CandleQuery(
            symbol="BTCUSDT",
            asset_class=AssetClass.CRYPTO,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=datetime(
                2026, 1, 1, 2, 0, tzinfo=UTC
            ),
            limit=10,
        )

        with pytest.raises(ValueError, match="aligned"):
            await service.ingest_missing_range(
                db=db,
                provider_name="binance",
                query=query,
                start_time=datetime(
                    2026, 1, 1, 0, 30, tzinfo=UTC
                ),
                end_time=datetime(
                    2026, 1, 1, 1, 0, tzinfo=UTC
                ),
            )

        db.scalars.assert_not_called()

    asyncio.run(run_test())


def test_ingestion_reports_skipped_finalized_candle():
    async def run_test():
        service = build_service()
        db = MagicMock()

        configure_database(db)

        db.execute.return_value.scalars.return_value.all.return_value = []

        query = CandleQuery(
            symbol="BTCUSDT",
            asset_class=AssetClass.CRYPTO,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=datetime(
                2026, 1, 1, 2, 0, tzinfo=UTC
            ),
            limit=10,
        )

        result = await service.ingest_historical_candles(
            db=db,
            provider_name="binance",
            query=query,
        )

        assert result["received"] == 1
        assert result["upserted"] == 0
        assert result["skipped"] == 1

    asyncio.run(run_test())


def test_live_candle_is_inserted():
    service = build_service()
    db = MagicMock()

    configure_database(db)
    db.execute.return_value.scalars.return_value.all.return_value = [
        uuid4()
    ]

    result = service.ingest_live_candle(
        db=db,
        provider_name="binance",
        candle=make_live_candle(),
    )

    statement = db.execute.call_args.args[0]
    compiled = str(
        statement.compile(dialect=postgresql.dialect())
    )

    assert result["received"] == 1
    assert result["upserted"] == 1
    assert result["skipped"] == 0
    assert "ON CONFLICT" in compiled
    assert "source_updated_at" in compiled
    db.commit.assert_called_once()


def test_live_candle_update_uses_same_conflict_key():
    service = build_service()
    db = MagicMock()

    configure_database(db)

    db.execute.return_value.scalars.return_value.all.side_effect = [
        [uuid4()],
        [uuid4()],
    ]

    first_result = service.ingest_live_candle(
        db=db,
        provider_name="binance",
        candle=make_live_candle(close="105"),
    )

    second_result = service.ingest_live_candle(
        db=db,
        provider_name="binance",
        candle=make_live_candle(close="107"),
    )

    first_statement = db.execute.call_args_list[0].args[0]
    second_statement = db.execute.call_args_list[1].args[0]

    assert first_result["upserted"] == 1
    assert second_result["upserted"] == 1

    assert first_statement._post_values_clause is not None
    assert second_statement._post_values_clause is not None

    assert db.commit.call_count == 2


def test_live_candle_rejects_unknown_mapping():
    service = build_service()
    db = MagicMock()

    db.scalars.return_value.all.return_value = []

    with pytest.raises(ValueError, match="No active instrument mapping"):
        service.ingest_live_candle(
            db=db,
            provider_name="binance",
            candle=make_live_candle(),
        )

    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    db.execute.assert_not_called()


def test_live_candle_rejects_provider_mismatch():
    service = build_service()
    db = MagicMock()

    candle = make_live_candle()
    candle = candle.model_copy(update={"provider": "other_provider"})

    with pytest.raises(ValueError, match="provider does not match"):
        service.ingest_live_candle(
            db=db,
            provider_name="binance",
            candle=candle,
        )

    db.execute.assert_not_called()
    db.rollback.assert_called_once()
