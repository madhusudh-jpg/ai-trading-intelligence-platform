
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle as CandleModel
from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import AssetClass, Candle, Timeframe
from app.market_data.services.candle_ingestion_service import (
    CandleIngestionService,
)

BASE_TIME = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
CLOSE_TIME = datetime(2026, 1, 1, 1, 0, tzinfo=UTC)


class FakeProvider:
    name = "binance"


def build_service() -> CandleIngestionService:
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    return CandleIngestionService(registry)


def make_candle(
    symbol: str,
    close: str = "105",
    is_complete: bool = False,
) -> Candle:
    return Candle(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        open_time=BASE_TIME,
        close_time=CLOSE_TIME,
        open="100",
        high="110",
        low="90",
        close=close,
        volume="10",
        is_complete=is_complete,
        provider="binance",
    )


def get_stored_candle(
    db: Session,
    mapping_id,
) -> CandleModel:
    return db.scalar(
        select(CandleModel).where(
            CandleModel.instrument_provider_symbol_id == mapping_id,
            CandleModel.timeframe == Timeframe.H1.value,
            CandleModel.open_time == BASE_TIME,
        )
    )


def test_identical_duplicate_is_skipped(
    db_session: Session,
    binance_mapping,
):
    service = build_service()
    candle = make_candle(binance_mapping.provider_symbol)

    first_result = service.ingest_live_candle(
        db_session,
        "binance",
        candle,
    )

    db_session.expire_all()
    original = get_stored_candle(db_session, binance_mapping.id)
    original_updated_at = original.source_updated_at

    second_result = service.ingest_live_candle(
        db_session,
        "binance",
        candle,
    )

    db_session.expire_all()
    stored = get_stored_candle(db_session, binance_mapping.id)

    assert first_result["upserted"] == 1
    assert second_result["upserted"] == 0
    assert second_result["skipped"] == 1
    assert stored.source_updated_at == original_updated_at
    assert stored.close == Decimal("105")


def test_changed_incomplete_candle_is_updated(
    db_session: Session,
    binance_mapping,
):
    service = build_service()

    service.ingest_live_candle(
        db_session,
        "binance",
        make_candle(binance_mapping.provider_symbol, close="105"),
    )

    result = service.ingest_live_candle(
        db_session,
        "binance",
        make_candle(binance_mapping.provider_symbol, close="107"),
    )

    db_session.expire_all()
    stored = get_stored_candle(db_session, binance_mapping.id)

    assert result["upserted"] == 1
    assert result["skipped"] == 0
    assert stored.close == Decimal("107")
    assert stored.is_complete is False


def test_incomplete_candle_can_be_finalized(
    db_session: Session,
    binance_mapping,
):
    service = build_service()

    service.ingest_live_candle(
        db_session,
        "binance",
        make_candle(
            binance_mapping.provider_symbol,
            close="105",
            is_complete=False,
        ),
    )

    result = service.ingest_live_candle(
        db_session,
        "binance",
        make_candle(
            binance_mapping.provider_symbol,
            close="106",
            is_complete=True,
        ),
    )

    db_session.expire_all()
    stored = get_stored_candle(db_session, binance_mapping.id)

    assert result["upserted"] == 1
    assert stored.close == Decimal("106")
    assert stored.is_complete is True


@pytest.mark.parametrize(
    "incoming_complete",
    [False, True],
)
def test_completed_candle_cannot_be_overwritten(
    db_session: Session,
    binance_mapping,
    incoming_complete: bool,
):
    service = build_service()

    service.ingest_live_candle(
        db_session,
        "binance",
        make_candle(
            binance_mapping.provider_symbol,
            close="105",
            is_complete=True,
        ),
    )

    result = service.ingest_live_candle(
        db_session,
        "binance",
        make_candle(
            binance_mapping.provider_symbol,
            close="107",
            is_complete=incoming_complete,
        ),
    )

    db_session.expire_all()
    stored = get_stored_candle(db_session, binance_mapping.id)

    assert result["upserted"] == 0
    assert result["skipped"] == 1
    assert stored.close == Decimal("105")
    assert stored.is_complete is True
