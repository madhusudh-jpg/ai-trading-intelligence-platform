
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.market_data_monitoring import router
from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)


def create_test_app(tracker=None):
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")

    if tracker is not None:
        application.state.feed_health_tracker = tracker

    return application


def test_feeds_endpoint_returns_tracked_feed():
    tracker = FeedHealthTracker()
    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    client = TestClient(create_test_app(tracker))

    response = client.get("/api/v1/market-data/feeds")

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 1

    feed = data["feeds"][0]

    assert feed["provider"] == "binance"
    assert feed["symbol"] == "BTCUSDT"
    assert feed["timeframe"] == "1h"
    assert feed["connected"] is True
    assert feed["data_status"] == "realtime"
    assert feed["last_message_at"] is not None


def test_feeds_endpoint_returns_empty_list_when_no_feeds_exist():
    tracker = FeedHealthTracker()
    client = TestClient(create_test_app(tracker))

    response = client.get("/api/v1/market-data/feeds")

    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "feeds": [],
    }


def test_feeds_endpoint_returns_503_without_tracker():
    client = TestClient(create_test_app())

    response = client.get("/api/v1/market-data/feeds")

    assert response.status_code == 503


def test_symbol_endpoint_returns_all_tracked_timeframes():
    tracker = FeedHealthTracker()

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    tracker.mark_connected("binance", "BTCUSDT", "4h")
    tracker.record_message("binance", "BTCUSDT", "4h")

    client = TestClient(create_test_app(tracker))

    response = client.get(
        "/api/v1/market-data/feeds/BTCUSDT"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["symbol"] == "BTCUSDT"
    assert data["count"] == 2

    timeframes = {
        feed["timeframe"]
        for feed in data["feeds"]
    }

    assert timeframes == {"1h", "4h"}


def test_symbol_endpoint_normalizes_symbol():
    tracker = FeedHealthTracker()
    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    client = TestClient(create_test_app(tracker))

    response = client.get(
        "/api/v1/market-data/feeds/btcusdt"
    )

    assert response.status_code == 200
    assert response.json()["symbol"] == "BTCUSDT"


def test_symbol_endpoint_filters_by_provider():
    tracker = FeedHealthTracker()

    tracker.mark_connected("binance", "BTCUSDT", "1h")
    tracker.record_message("binance", "BTCUSDT", "1h")

    client = TestClient(create_test_app(tracker))

    response = client.get(
        "/api/v1/market-data/feeds/BTCUSDT?provider=binance"
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_symbol_endpoint_returns_404_for_unknown_symbol():
    tracker = FeedHealthTracker()
    client = TestClient(create_test_app(tracker))

    response = client.get(
        "/api/v1/market-data/feeds/UNKNOWN"
    )

    assert response.status_code == 404
