
import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.instrument import Instrument
from app.db.models.instrument_provider_symbol import (
    InstrumentProviderSymbol,
)
from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import (
    AssetClass,
    CandleQuery,
    Timeframe,
)
from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)
from app.market_data.services.historical_recovery_service import (
    HistoricalRecoveryService,
)
from app.market_data.services.market_data_service import MarketDataService
from app.market_data.services.timeframes import FIXED_INTERVALS

logger = logging.getLogger(__name__)

INITIAL_RESTART_DELAY_SECONDS = 5
MAX_RESTART_DELAY_SECONDS = 60

RECOVERY_INTERVAL_SECONDS = 300

RECOVERY_LOOKBACK_DAYS_BY_TIMEFRAME = {
    Timeframe.M15: 30,
    Timeframe.H1: 90,
    Timeframe.H4: 180,
    Timeframe.D1: 365,
}

LIVE_TIMEFRAMES = (
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
)


class LiveIngestionWorker:
    """Manages live streams, feed monitoring, and historical recovery."""

    def __init__(
        self,
        registry: ProviderRegistry,
        session_factory: Callable[[], Session] | None = None,
        health_tracker: FeedHealthTracker | None = None,
        watchdog_interval_seconds: float = 10,
    ) -> None:
        if watchdog_interval_seconds <= 0:
            raise ValueError(
                "Watchdog interval must be greater than zero."
            )

        self.registry = registry
        self.session_factory = session_factory or SessionLocal
        self.health_tracker = health_tracker or FeedHealthTracker()
        self.watchdog_interval_seconds = watchdog_interval_seconds

        self.market_data_service = MarketDataService(
            registry=registry,
            session_factory=self.session_factory,
        )

        self.recovery_service = HistoricalRecoveryService(registry)

        self._tasks: list[asyncio.Task] = []
        self._last_health_status = {}

    @property
    def running(self) -> bool:
        return any(not task.done() for task in self._tasks)

    async def _load_stream_targets(self) -> list[tuple[str, AssetClass]]:
        """Find active Binance mappings for active crypto instruments."""

        def load() -> list[tuple[str, AssetClass]]:
            db = self.session_factory()

            try:
                statement = (
                    select(InstrumentProviderSymbol, Instrument)
                    .join(
                        Instrument,
                        Instrument.id
                        == InstrumentProviderSymbol.instrument_id,
                    )
                    .where(
                        InstrumentProviderSymbol.provider == "binance",
                        InstrumentProviderSymbol.is_active.is_(True),
                        Instrument.is_active.is_(True),
                        Instrument.asset_class == AssetClass.CRYPTO.value,
                    )
                    .order_by(Instrument.symbol.asc())
                )

                rows = db.execute(statement).all()

                return [
                    (
                        mapping.provider_symbol,
                        AssetClass(instrument.asset_class),
                    )
                    for mapping, instrument in rows
                ]

            finally:
                db.close()

        return await asyncio.to_thread(load)

    @staticmethod
    def _build_recovery_query(
        symbol: str,
        asset_class: AssetClass,
        timeframe: Timeframe,
    ) -> CandleQuery:
        """Build a UTC-aligned historical recovery window."""

        interval = FIXED_INTERVALS.get(timeframe)

        if interval is None:
            raise ValueError(
                f"Automatic recovery does not support {timeframe.value}."
            )

        lookback_days = RECOVERY_LOOKBACK_DAYS_BY_TIMEFRAME.get(timeframe)

        if lookback_days is None:
            raise ValueError(
                f"No recovery lookback configured for {timeframe.value}."
            )

        now = datetime.now(UTC)
        epoch = datetime(1970, 1, 1, tzinfo=UTC)

        elapsed = now - epoch
        completed_intervals = elapsed // interval
        end_time = epoch + completed_intervals * interval

        start_time = end_time - timedelta(days=lookback_days)

        candle_count = int(
            (end_time - start_time) / interval
        )

        return CandleQuery(
            symbol=symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            limit=candle_count,
        )

    async def _recover_target(
        self,
        symbol: str,
        asset_class: AssetClass,
        timeframe: Timeframe,
    ) -> None:
        """Detect and recover missing completed candles."""

        query = self._build_recovery_query(
            symbol,
            asset_class,
            timeframe,
        )

        db = self.session_factory()

        try:
            report = await self.recovery_service.recover_missing_candles(
                db=db,
                provider_name="binance",
                query=query,
            )

            logger.info(
                "Recovery for %s %s: missing=%s, received=%s, "
                "upserted=%s, remaining=%s",
                symbol,
                timeframe.value,
                report["initial_missing_count"],
                report["received"],
                report["upserted"],
                report["remaining_missing_count"],
            )

        finally:
            db.close()

    async def _run_recovery(
        self,
        symbol: str,
        asset_class: AssetClass,
        timeframe: Timeframe,
    ) -> None:
        """Run recovery immediately and then periodically."""

        while True:
            try:
                await self._recover_target(
                    symbol,
                    asset_class,
                    timeframe,
                )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Historical recovery failed for %s %s.",
                    symbol,
                    timeframe.value,
                )

            await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)

    async def _run_feed_health_watchdog(self) -> None:
        """Evaluate feed freshness and log health-state transitions."""

        while True:
            await asyncio.sleep(self.watchdog_interval_seconds)

            try:
                feeds = self.health_tracker.evaluate_all()

                for feed in feeds:
                    key = (
                        feed.provider,
                        feed.symbol,
                        feed.timeframe,
                    )
                    previous_status = self._last_health_status.get(key)
                    current_status = feed.data_status

                    if previous_status == current_status:
                        continue

                    self._last_health_status[key] = current_status

                    if current_status.value == "realtime":
                        logger.info(
                            "Feed recovered: %s %s is realtime.",
                            feed.symbol,
                            feed.timeframe,
                        )
                    else:
                        logger.warning(
                            "Feed health changed: provider=%s, "
                            "symbol=%s, timeframe=%s, status=%s, "
                            "message=%s",
                            feed.provider,
                            feed.symbol,
                            feed.timeframe,
                            current_status.value,
                            feed.message,
                        )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception("Feed-health watchdog failed.")

    async def start(self) -> int:
        """Discover instruments and start all live and recovery tasks."""

        if self._tasks:
            return sum(
                1
                for task in self._tasks
                if task.get_name().startswith("live-")
            )

        if "binance" not in self.registry.names():
            logger.warning(
                "Live ingestion not started: Binance is not registered."
            )
            return 0

        provider = self.registry.get("binance")

        if not provider.capabilities.live_streaming:
            logger.warning(
                "Live ingestion not started: Binance streaming "
                "is not supported."
            )
            return 0

        targets = await self._load_stream_targets()
        live_stream_count = 0

        for symbol, asset_class in targets:
            for timeframe in LIVE_TIMEFRAMES:
                query = self._build_recovery_query(
                    symbol,
                    asset_class,
                    timeframe,
                )

                stream_task = asyncio.create_task(
                    self._run_stream(query),
                    name=f"live-binance-{symbol}-{timeframe.value}",
                )

                recovery_task = asyncio.create_task(
                    self._run_recovery(
                        symbol,
                        asset_class,
                        timeframe,
                    ),
                    name=f"recovery-binance-{symbol}-{timeframe.value}",
                )

                self._tasks.extend(
                    [stream_task, recovery_task]
                )

                live_stream_count += 1

        if live_stream_count:
            watchdog_task = asyncio.create_task(
                self._run_feed_health_watchdog(),
                name="feed-health-watchdog",
            )
            self._tasks.append(watchdog_task)

        logger.info(
            "Started %s live streams, %s recovery tasks, "
            "and %s feed-health watchdogs.",
            live_stream_count,
            live_stream_count,
            1 if live_stream_count else 0,
        )

        return live_stream_count

    async def _run_stream(self, query: CandleQuery) -> None:
        """Supervise a live stream and restart after failures."""

        delay = INITIAL_RESTART_DELAY_SECONDS

        while True:
            try:
                async for _ in (
                    self.market_data_service.stream_and_persist_candles(
                        "binance",
                        query,
                    )
                ):
                    delay = INITIAL_RESTART_DELAY_SECONDS

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Live ingestion failed for Binance %s %s. "
                    "Restarting in %s seconds.",
                    query.symbol,
                    query.timeframe.value,
                    delay,
                )

            else:
                logger.warning(
                    "Binance stream ended for %s %s. Restarting.",
                    query.symbol,
                    query.timeframe.value,
                )

            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RESTART_DELAY_SECONDS)

    async def stop(self) -> None:
        """Cancel all streams, recovery jobs, and watchdog tasks."""

        tasks = list(self._tasks)
        self._tasks.clear()

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._last_health_status.clear()

        logger.info("Live-ingestion worker stopped.")
