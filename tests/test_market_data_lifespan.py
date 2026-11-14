
from unittest.mock import AsyncMock

from fastapi import FastAPI

import app.main as main
from app.market_data.providers.binance import BinanceProvider
from app.market_data.providers.registry import ProviderRegistry


def configure_settings(
    monkeypatch,
    *,
    binance_enabled=True,
    live_data_enabled=True,
    live_ingestion_enabled=True,
):
    monkeypatch.setattr(
        main.market_data_settings,
        "binance_enabled",
        binance_enabled,
    )
    monkeypatch.setattr(
        main.market_data_settings,
        "live_data_enabled",
        live_data_enabled,
    )
    monkeypatch.setattr(
        main.market_data_settings,
        "live_ingestion_enabled",
        live_ingestion_enabled,
    )
    monkeypatch.setattr(
        main.market_data_settings,
        "feed_delayed_after_seconds",
        30,
    )
    monkeypatch.setattr(
        main.market_data_settings,
        "feed_stale_after_seconds",
        60,
    )
    monkeypatch.setattr(
        main.market_data_settings,
        "feed_message_timeout_seconds",
        90,
    )
    monkeypatch.setattr(
        main.market_data_settings,
        "feed_health_check_interval_seconds",
        10,
    )


def test_lifespan_registers_binance_and_creates_shared_tracker(
    monkeypatch,
):
    async def run_test():
        configure_settings(monkeypatch)

        registry = ProviderRegistry()
        monkeypatch.setattr(main, "provider_registry", registry)

        worker_instance = None

        class FakeWorker:
            def __init__(self, **kwargs):
                nonlocal worker_instance
                self.kwargs = kwargs
                self.start = AsyncMock(return_value=1)
                self.stop = AsyncMock()
                worker_instance = self

        monkeypatch.setattr(main, "LiveIngestionWorker", FakeWorker)

        application = FastAPI()

        async with main.lifespan(application):
            tracker = application.state.feed_health_tracker

            assert tracker is not None
            assert tracker.delayed_after_seconds == 30
            assert tracker.stale_after_seconds == 60

            assert "binance" in registry.names()

            provider = registry.get("binance")

            assert isinstance(provider, BinanceProvider)
            assert provider.health_tracker is tracker
            assert provider.message_timeout_seconds == 90

            assert application.state.provider_registry is registry

            assert worker_instance is not None
            assert worker_instance.kwargs["health_tracker"] is tracker
            assert (
                worker_instance.kwargs["watchdog_interval_seconds"]
                == 10
            )
            worker_instance.start.assert_awaited_once()

        worker_instance.stop.assert_awaited_once()

    import asyncio

    asyncio.run(run_test())


def test_lifespan_does_not_start_worker_when_ingestion_disabled(
    monkeypatch,
):
    async def run_test():
        configure_settings(
            monkeypatch,
            binance_enabled=True,
            live_data_enabled=True,
            live_ingestion_enabled=False,
        )

        registry = ProviderRegistry()
        monkeypatch.setattr(main, "provider_registry", registry)

        worker_constructor = AsyncMock()
        monkeypatch.setattr(
            main,
            "LiveIngestionWorker",
            worker_constructor,
        )

        application = FastAPI()

        async with main.lifespan(application):
            assert "binance" in registry.names()
            assert application.state.feed_health_tracker is not None
            worker_constructor.assert_not_called()

    import asyncio

    asyncio.run(run_test())


def test_lifespan_does_not_register_binance_when_disabled(
    monkeypatch,
):
    async def run_test():
        configure_settings(
            monkeypatch,
            binance_enabled=False,
            live_data_enabled=True,
            live_ingestion_enabled=True,
        )

        registry = ProviderRegistry()
        monkeypatch.setattr(main, "provider_registry", registry)

        worker_constructor = AsyncMock()
        monkeypatch.setattr(
            main,
            "LiveIngestionWorker",
            worker_constructor,
        )

        application = FastAPI()

        async with main.lifespan(application):
            assert "binance" not in registry.names()
            assert application.state.feed_health_tracker is not None
            worker_constructor.assert_not_called()

    import asyncio

    asyncio.run(run_test())
