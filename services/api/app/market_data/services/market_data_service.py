
import asyncio
import time
from collections.abc import AsyncIterator, Callable

from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import (
    Candle,
    CandleQuery,
    ProviderStatus,
)
from app.market_data.services.candle_ingestion_service import (
    CandleIngestionService,
)

MAX_DATABASE_ATTEMPTS = 4
INITIAL_RETRY_DELAY_SECONDS = 1
MAX_RETRY_DELAY_SECONDS = 4


class MarketDataService:
    """Coordinates historical and live market-data operations."""

    def __init__(
        self,
        registry: ProviderRegistry,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.registry = registry
        self.session_factory = session_factory or SessionLocal
        self.ingestion_service = CandleIngestionService(registry)

    async def provider_statuses(self) -> list[ProviderStatus]:
        statuses: list[ProviderStatus] = []

        for provider in self.registry.list_providers():
            try:
                status = await provider.get_status()
                statuses.append(status)

            except Exception as exc:
                statuses.append(
                    ProviderStatus(
                        provider=provider.name,
                        configured=True,
                        connected=False,
                        message=f"Status check failed: {type(exc).__name__}",
                    )
                )

        return statuses

    async def historical_candles(
        self,
        provider_name: str,
        query: CandleQuery,
    ) -> list[Candle]:
        provider = self.registry.get(provider_name)

        candles = await provider.get_historical_candles(query)

        return sorted(
            candles,
            key=lambda candle: candle.open_time,
        )

    def _persist_live_candle(
        self,
        provider_name: str,
        candle: Candle,
    ) -> dict[str, int | str]:
        """Persist a candle with bounded retries for transient DB failures."""

        retry_delay = INITIAL_RETRY_DELAY_SECONDS

        for attempt in range(1, MAX_DATABASE_ATTEMPTS + 1):
            db = self.session_factory()
            delay_before_retry: int | None = None

            try:
                return self.ingestion_service.ingest_live_candle(
                    db=db,
                    provider_name=provider_name,
                    candle=candle,
                )

            except TimeoutError:
                if attempt == MAX_DATABASE_ATTEMPTS:
                    raise

                delay_before_retry = retry_delay

            except DBAPIError as exc:
                retryable = (
                    isinstance(exc, OperationalError)
                    or exc.connection_invalidated
                )

                if not retryable or attempt == MAX_DATABASE_ATTEMPTS:
                    raise

                delay_before_retry = retry_delay

            finally:
                db.close()

            if delay_before_retry is not None:
                time.sleep(delay_before_retry)
                retry_delay = min(
                    retry_delay * 2,
                    MAX_RETRY_DELAY_SECONDS,
                )

        raise RuntimeError("Database retry loop ended unexpectedly.")

    async def stream_and_persist_candles(
        self,
        provider_name: str,
        query: CandleQuery,
    ) -> AsyncIterator[Candle]:
        """Stream provider candles, persist each update, then yield it."""

        provider_name = provider_name.strip().lower()
        provider = self.registry.get(provider_name)

        stream = provider.stream_candles(query)

        try:
            async for candle in stream:
                await asyncio.to_thread(
                    self._persist_live_candle,
                    provider_name,
                    candle,
                )

                yield candle

        finally:
            close_stream = getattr(stream, "aclose", None)

            if close_stream is not None:
                await close_stream()
