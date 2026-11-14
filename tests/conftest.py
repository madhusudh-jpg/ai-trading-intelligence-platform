
import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.models.instrument import Instrument
from app.db.models.instrument_provider_symbol import InstrumentProviderSymbol


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated transaction against the dedicated test database."""

    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        pytest.fail(
            "TEST_DATABASE_URL is required for PostgreSQL integration tests."
        )

    database_name = make_url(database_url).database

    if database_name != "trading_test":
        pytest.fail(
            "Integration tests may only connect to the 'trading_test' database."
        )

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        connection = engine.connect()
        transaction = connection.begin()

        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        )

        try:
            yield session
        finally:
            session.close()

            if transaction.is_active:
                transaction.rollback()

            connection.close()
    finally:
        engine.dispose()


@pytest.fixture
def binance_mapping(
    db_session: Session,
) -> InstrumentProviderSymbol:
    """Create a unique instrument and Binance mapping for one test."""

    from uuid import uuid4

    suffix = uuid4().hex[:12].upper()
    symbol = f"TEST{suffix}USDT"

    instrument = Instrument(
        symbol=symbol,
        name=f"Integration Test Instrument {suffix}",
        asset_class="crypto",
        exchange="TEST_EXCHANGE",
        base_currency="TEST",
        quote_currency="USDT",
        is_active=True,
    )

    db_session.add(instrument)
    db_session.flush()

    mapping = InstrumentProviderSymbol(
        instrument_id=instrument.id,
        provider="binance",
        provider_symbol=symbol,
        provider_exchange="SPOT",
        is_active=True,
    )

    db_session.add(mapping)
    db_session.flush()

    return mapping
