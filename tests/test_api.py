
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="module")
def client():
    """Run application startup and shutdown for API tests."""

    with TestClient(app) as test_client:
        yield test_client


class FakeScalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeDatabase:
    def __init__(self, instrument, mapping, candles):
        self.instrument = instrument
        self.mapping = mapping
        self.candles = candles
        self.query_count = 0

    def scalars(self, query):
        self.query_count += 1

        if self.query_count == 1:
            return FakeScalars(
                [self.instrument] if self.instrument else []
            )

        if self.query_count == 2:
            return FakeScalars(
                [self.mapping] if self.mapping else []
            )

        return FakeScalars(self.candles)


class FakeInstrumentDatabase:
    def __init__(self, instruments, mappings):
        self.instruments = instruments
        self.mappings = mappings
        self.query_count = 0

    def scalars(self, query):
        self.query_count += 1

        if self.query_count == 1:
            return FakeScalars(self.instruments)

        return FakeScalars(self.mappings)


def make_instrument():
    instrument_id = uuid4()

    return SimpleNamespace(
        id=instrument_id,
        symbol="BTCUSDT",
        name="Bitcoin / Tether",
        asset_class="crypto",
        exchange="BINANCE",
        base_currency="BTC",
        quote_currency="USDT",
        is_active=True,
    )


def make_mapping(instrument):
    return SimpleNamespace(
        id=uuid4(),
        instrument_id=instrument.id,
        provider="binance",
        provider_symbol="BTCUSDT",
        provider_exchange="SPOT",
        is_active=True,
    )


def make_candle():
    return SimpleNamespace(
        open_time=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
        close_time=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        open=Decimal("100000.00"),
        high=Decimal("101000.00"),
        low=Decimal("99000.00"),
        close=Decimal("100500.00"),
        volume=Decimal("12.50"),
        is_complete=True,
    )


def override_database(fake_db):
    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_platform_overview_endpoint(client):
    response = client.get("/api/v1/")

    assert response.status_code == 200

    data = response.json()

    assert data["name"] == "AI Trading Intelligence Platform"
    assert data["execution_mode"] == "analysis_only"
    assert len(data["modules"]) == 10


def test_supported_markets_endpoint(client):
    response = client.get("/api/v1/markets")

    assert response.status_code == 200

    data = response.json()

    assert set(data["markets"]) == {
        "forex",
        "crypto",
        "us_stocks",
        "indices",
        "nse_bse",
    }


def test_candles_endpoint_returns_stored_candles(client):
    instrument = make_instrument()
    mapping = make_mapping(instrument)

    fake_db = FakeDatabase(
        instrument=instrument,
        mapping=mapping,
        candles=[make_candle()],
    )

    override_database(fake_db)

    try:
        response = client.get(
            "/api/v1/market-data/candles",
            params={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "limit": 500,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200

    data = response.json()

    assert data["instrument_id"] == str(instrument.id)
    assert data["symbol"] == "BTCUSDT"
    assert data["asset_class"] == "crypto"
    assert data["provider"] == "binance"
    assert data["provider_symbol"] == "BTCUSDT"
    assert data["timeframe"] == "1h"
    assert data["count"] == 1
    assert data["candles"][0]["open"] == "100000.00"
    assert data["candles"][0]["volume"] == "12.50"
    assert data["candles"][0]["is_complete"] is True


def test_candles_endpoint_accepts_instrument_id(client):
    instrument = make_instrument()
    mapping = make_mapping(instrument)

    fake_db = FakeDatabase(
        instrument=instrument,
        mapping=mapping,
        candles=[make_candle()],
    )

    override_database(fake_db)

    try:
        response = client.get(
            "/api/v1/market-data/candles",
            params={
                "instrument_id": str(instrument.id),
                "timeframe": "1h",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["instrument_id"] == str(instrument.id)


def test_candles_endpoint_requires_instrument_identifier(client):
    response = client.get(
        "/api/v1/market-data/candles",
        params={"timeframe": "1h"},
    )

    assert response.status_code == 422


def test_candles_endpoint_rejects_both_identifiers(client):
    response = client.get(
        "/api/v1/market-data/candles",
        params={
            "instrument_id": str(uuid4()),
            "symbol": "BTCUSDT",
            "timeframe": "1h",
        },
    )

    assert response.status_code == 422


def test_candles_endpoint_rejects_invalid_time_range(client):
    response = client.get(
        "/api/v1/market-data/candles",
        params={
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "start_time": "2026-11-10T10:00:00Z",
            "end_time": "2026-11-10T09:00:00Z",
        },
    )

    assert response.status_code == 422


def test_candles_endpoint_rejects_invalid_timeframe(client):
    response = client.get(
        "/api/v1/market-data/candles",
        params={
            "symbol": "BTCUSDT",
            "timeframe": "invalid",
        },
    )

    assert response.status_code == 422


def test_candles_endpoint_rejects_missing_instrument(client):
    fake_db = FakeDatabase(
        instrument=None,
        mapping=None,
        candles=[],
    )

    override_database(fake_db)

    try:
        response = client.get(
            "/api/v1/market-data/candles",
            params={
                "symbol": "UNKNOWN",
                "timeframe": "1h",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


def test_candles_endpoint_rejects_missing_provider_mapping(client):
    instrument = make_instrument()

    fake_db = FakeDatabase(
        instrument=instrument,
        mapping=None,
        candles=[],
    )

    override_database(fake_db)

    try:
        response = client.get(
            "/api/v1/market-data/candles",
            params={
                "instrument_id": str(instrument.id),
                "timeframe": "1h",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


def test_instruments_endpoint_returns_catalogue(client):
    instrument = make_instrument()
    mapping = make_mapping(instrument)

    fake_db = FakeInstrumentDatabase(
        instruments=[instrument],
        mappings=[mapping],
    )

    override_database(fake_db)

    try:
        response = client.get("/api/v1/instruments")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 1
    assert data["instruments"][0]["symbol"] == "BTCUSDT"
    assert data["instruments"][0]["asset_class"] == "crypto"
    assert data["instruments"][0]["provider_mappings"][0] == {
        "provider": "binance",
        "provider_symbol": "BTCUSDT",
        "provider_exchange": "SPOT",
    }


def test_instruments_endpoint_returns_empty_catalogue(client):
    fake_db = FakeInstrumentDatabase(
        instruments=[],
        mappings=[],
    )

    override_database(fake_db)

    try:
        response = client.get(
            "/api/v1/instruments",
            params={"asset_class": "forex"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "instruments": [],
    }
