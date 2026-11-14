
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.market_data.providers.capabilities import ProviderCapabilities
from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import (
    AssetClass,
    Timeframe,
)
from app.market_data.services.live_ingestion_worker import (
    LIVE_TIMEFRAMES,
    LiveIngestionWorker,
)


class FakeProvider:
    name = "binance"

    @property
    def capabilities(self):
        return ProviderCapabilities(
            provider_name="binance",
            supported_asset_classes=[AssetClass.CRYPTO],
            supported_timeframes=[
                Timeframe.M15,
                Timeframe.H1,
                Timeframe.H4,
                Timeframe.D1,
            ],
            live_streaming=True,
            requires_api_key=False,
        )


def make_worker(session_factory):
    registry = ProviderRegistry()
    registry.register(FakeProvider())

    return LiveIngestionWorker(
        registry=registry,
        session_factory=session_factory,
    )


def test_worker_discovers_active_stream_targets():
    async def run_test():
        mapping = SimpleNamespace(provider_symbol="BTCUSDT")
        instrument = SimpleNamespace(asset_class="crypto")

        db = MagicMock()
        db.execute.return_value.all.return_value = [
            (mapping, instrument)
        ]

        worker = make_worker(MagicMock(return_value=db))

        targets = await worker._load_stream_targets()

        assert targets == [("BTCUSDT", AssetClass.CRYPTO)]
        db.close.assert_called_once()

    asyncio.run(run_test())


def test_worker_supports_four_live_timeframes():
    assert LIVE_TIMEFRAMES == (
        Timeframe.M15,
        Timeframe.H1,
        Timeframe.H4,
        Timeframe.D1,
    )


def test_worker_start_creates_stream_recovery_and_watchdog_tasks():
    async def run_test():
        db = MagicMock()
        mapping = SimpleNamespace(provider_symbol="BTCUSDT")
        instrument = SimpleNamespace(asset_class="crypto")

        db.execute.return_value.all.return_value = [
            (mapping, instrument)
        ]

        worker = make_worker(MagicMock(return_value=db))

        worker.recovery_service.recover_missing_candles = AsyncMock(
            return_value={
                "initial_missing_count": 0,
                "received": 0,
                "upserted": 0,
                "remaining_missing_count": 0,
            }
        )

        async def fake_stream(*args):
            await asyncio.Event().wait()
            yield None

        worker.market_data_service.stream_and_persist_candles = fake_stream

        count = await worker.start()

        task_names = {task.get_name() for task in worker._tasks}

        expected_timeframes = {"15m", "1h", "4h", "1d"}

        expected_live_tasks = {
            f"live-binance-BTCUSDT-{timeframe}"
            for timeframe in expected_timeframes
        }

        expected_recovery_tasks = {
            f"recovery-binance-BTCUSDT-{timeframe}"
            for timeframe in expected_timeframes
        }

        assert count == 4
        assert len(worker._tasks) == 9
        assert expected_live_tasks.issubset(task_names)
        assert expected_recovery_tasks.issubset(task_names)
        assert "feed-health-watchdog" in task_names
        assert worker.running is True

        await worker.stop()

        assert worker.running is False
        assert worker._tasks == []

    asyncio.run(run_test())


def test_worker_does_not_start_without_binance():
    async def run_test():
        worker = LiveIngestionWorker(ProviderRegistry())

        count = await worker.start()

        assert count == 0
        assert worker.running is False

    asyncio.run(run_test())
