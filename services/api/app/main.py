
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market_data_monitoring import (
    router as market_data_monitoring_router,
)
from app.api.routes import router
from app.core.config import settings
from app.market_data.config import market_data_settings
from app.market_data.providers.binance import (
    BinanceProvider,
    binance_provider,
)
from app.market_data.providers.registry import provider_registry
from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)
from app.market_data.services.live_ingestion_worker import (
    LiveIngestionWorker,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize providers and manage live-ingestion tasks."""

    health_tracker = FeedHealthTracker(
        delayed_after_seconds=(
            market_data_settings.feed_delayed_after_seconds
        ),
        stale_after_seconds=(
            market_data_settings.feed_stale_after_seconds
        ),
    )

    application.state.feed_health_tracker = health_tracker
    application.state.provider_registry = provider_registry

    worker = None

    try:
        if market_data_settings.binance_enabled:
            if "binance" not in provider_registry.names():
                binance_provider.configure_feed_health(
                    health_tracker,
                    market_data_settings.feed_message_timeout_seconds,
                )
                provider_registry.register(binance_provider)

            else:
                registered_provider = provider_registry.get("binance")

                if isinstance(registered_provider, BinanceProvider):
                    registered_provider.configure_feed_health(
                        health_tracker,
                        market_data_settings.feed_message_timeout_seconds,
                    )

        if (
            market_data_settings.binance_enabled
            and market_data_settings.live_data_enabled
            and market_data_settings.live_ingestion_enabled
        ):
            worker = LiveIngestionWorker(
                registry=provider_registry,
                health_tracker=health_tracker,
                watchdog_interval_seconds=(
                    market_data_settings.feed_health_check_interval_seconds
                ),
            )

            application.state.live_ingestion_worker = worker
            await worker.start()

        yield

    finally:
        if worker is not None:
            await worker.stop()


app = FastAPI(
    title="AI Trading Intelligence API",
    version="0.1.0",
    description=(
        "Multi-asset charting and ICT-based analysis API. "
        "Analysis-only: this API does not execute broker orders."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(
    market_data_monitoring_router,
    prefix="/api/v1",
)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "api"}
