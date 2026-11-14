
import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import websockets

from app.market_data.providers.capabilities import ProviderCapabilities
from app.market_data.schemas.market_data import (
    AssetClass,
    Candle,
    CandleQuery,
    DataStatus,
    ProviderStatus,
    Timeframe,
)
from app.market_data.services.feed_health_service import (
    FeedHealthTracker,
)


class BinanceProvider:
    """Binance public Spot market-data adapter."""

    name = "binance"

    REST_URL = "https://data-api.binance.vision"
    WEBSOCKET_URL = "wss://stream.binance.com:9443/ws"

    RECONNECT_INITIAL_DELAY_SECONDS = 1
    RECONNECT_MAX_DELAY_SECONDS = 30

    INTERVAL_MAP = {
        Timeframe.M1: "1m",
        Timeframe.M5: "5m",
        Timeframe.M15: "15m",
        Timeframe.M30: "30m",
        Timeframe.H1: "1h",
        Timeframe.H4: "4h",
        Timeframe.D1: "1d",
        Timeframe.W1: "1w",
        Timeframe.MN1: "1M",
    }

    def __init__(
        self,
        health_tracker: FeedHealthTracker | None = None,
        message_timeout_seconds: float = 90,
    ) -> None:
        if message_timeout_seconds <= 0:
            raise ValueError("Message timeout must be positive.")

        self.health_tracker = health_tracker or FeedHealthTracker()
        self.message_timeout_seconds = message_timeout_seconds

    def configure_feed_health(
        self,
        health_tracker: FeedHealthTracker,
        message_timeout_seconds: float,
    ) -> None:
        """Inject the application-wide feed tracker and timeout."""

        if message_timeout_seconds <= 0:
            raise ValueError("Message timeout must be positive.")

        self.health_tracker = health_tracker
        self.message_timeout_seconds = message_timeout_seconds

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            supported_asset_classes=[AssetClass.CRYPTO],
            supported_timeframes=list(self.INTERVAL_MAP),
            historical_data=True,
            live_streaming=True,
            requires_api_key=False,
            notes="Public Binance Spot market data.",
        )

    @staticmethod
    def _validate_query(query: CandleQuery) -> None:
        if query.asset_class != AssetClass.CRYPTO:
            raise ValueError(
                "Binance Spot adapter supports crypto only."
            )

    @staticmethod
    def _to_milliseconds(value: datetime) -> int:
        return int(value.timestamp() * 1000)

    def _parse_candle(
        self,
        symbol: str,
        timeframe: Timeframe,
        row: list,
    ) -> Candle:
        open_time = datetime.fromtimestamp(
            row[0] / 1000,
            tz=UTC,
        )

        close_time = datetime.fromtimestamp(
            (row[6] + 1) / 1000,
            tz=UTC,
        )

        return Candle(
            symbol=symbol.upper(),
            asset_class=AssetClass.CRYPTO,
            timeframe=timeframe,
            open_time=open_time,
            close_time=close_time,
            open=Decimal(row[1]),
            high=Decimal(row[2]),
            low=Decimal(row[3]),
            close=Decimal(row[4]),
            volume=Decimal(row[5]),
            is_complete=close_time <= datetime.now(UTC),
            provider=self.name,
        )

    @staticmethod
    def _parse_websocket_candle(
        symbol: str,
        timeframe: Timeframe,
        message: str,
    ) -> Candle | None:
        try:
            payload = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(payload, dict):
            return None

        kline = payload.get("k")

        if not isinstance(kline, dict):
            return None

        try:
            return Candle(
                symbol=symbol.upper(),
                asset_class=AssetClass.CRYPTO,
                timeframe=timeframe,
                open_time=datetime.fromtimestamp(
                    kline["t"] / 1000,
                    tz=UTC,
                ),
                close_time=datetime.fromtimestamp(
                    (kline["T"] + 1) / 1000,
                    tz=UTC,
                ),
                open=Decimal(kline["o"]),
                high=Decimal(kline["h"]),
                low=Decimal(kline["l"]),
                close=Decimal(kline["c"]),
                volume=Decimal(kline["v"]),
                is_complete=kline["x"],
                provider=BinanceProvider.name,
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def get_status(self) -> ProviderStatus:
        """Report REST reachability separately from live feed health."""

        rest_connected = False
        rest_message = ""

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.REST_URL}/api/v3/ping"
                )
                response.raise_for_status()

            rest_connected = True
            rest_message = "Binance REST API is reachable."

        except (httpx.HTTPError, ValueError) as exc:
            rest_message = (
                f"Binance REST API unavailable: {type(exc).__name__}."
            )

        feeds = [
            feed
            for feed in self.health_tracker.evaluate_all()
            if feed.provider == self.name
        ]

        if not feeds:
            return ProviderStatus(
                provider=self.name,
                configured=True,
                connected=rest_connected,
                supported_asset_classes=[AssetClass.CRYPTO],
                data_status=(
                    DataStatus.HISTORICAL
                    if rest_connected
                    else DataStatus.UNAVAILABLE
                ),
                message=(
                    f"{rest_message} No live WebSocket feeds are tracked."
                ),
            )

        status_priority = {
            DataStatus.UNAVAILABLE: 0,
            DataStatus.STALE: 1,
            DataStatus.DELAYED: 2,
            DataStatus.REALTIME: 3,
        }

        feed_status = min(
            (feed.data_status for feed in feeds),
            key=lambda status: status_priority[status],
        )

        status_counts = {
            status.value: sum(
                feed.data_status == status
                for feed in feeds
            )
            for status in status_priority
        }

        return ProviderStatus(
            provider=self.name,
            configured=True,
            connected=rest_connected,
            supported_asset_classes=[AssetClass.CRYPTO],
            data_status=feed_status,
            message=(
                f"{rest_message} "
                f"Tracked WebSocket feeds: {len(feeds)}; "
                f"realtime={status_counts['realtime']}, "
                f"delayed={status_counts['delayed']}, "
                f"stale={status_counts['stale']}, "
                f"unavailable={status_counts['unavailable']}."
            ),
        )

    async def get_historical_candles(
        self,
        query: CandleQuery,
    ) -> list[Candle]:
        """Fetch historical candles using an exclusive end-time boundary."""

        self._validate_query(query)

        interval = self.INTERVAL_MAP[query.timeframe]

        start_time_ms = self._to_milliseconds(query.start_time)
        end_time_exclusive_ms = self._to_milliseconds(query.end_time)

        if end_time_exclusive_ms <= start_time_ms:
            raise ValueError(
                "The requested range must contain at least "
                "one millisecond."
            )

        end_time_inclusive_ms = end_time_exclusive_ms - 1

        candles: list[Candle] = []
        remaining = query.limit
        request_start_ms = start_time_ms

        async with httpx.AsyncClient(
            base_url=self.REST_URL,
            timeout=20,
        ) as client:
            while remaining > 0:
                batch_limit = min(remaining, 1000)

                response = await client.get(
                    "/api/v3/klines",
                    params={
                        "symbol": query.symbol.upper(),
                        "interval": interval,
                        "startTime": request_start_ms,
                        "endTime": end_time_inclusive_ms,
                        "limit": batch_limit,
                    },
                )
                response.raise_for_status()

                rows = response.json()

                if not rows:
                    break

                valid_rows = [
                    row
                    for row in rows
                    if (
                        start_time_ms
                        <= row[0]
                        < end_time_exclusive_ms
                    )
                ]

                candles.extend(
                    self._parse_candle(
                        query.symbol,
                        query.timeframe,
                        row,
                    )
                    for row in valid_rows[:remaining]
                )

                remaining = query.limit - len(candles)

                last_open_time_ms = rows[-1][0]
                next_start_ms = last_open_time_ms + 1

                if next_start_ms <= request_start_ms:
                    raise RuntimeError(
                        "Binance returned a non-advancing candle page."
                    )

                if last_open_time_ms >= end_time_exclusive_ms:
                    break

                request_start_ms = next_start_ms

                if len(rows) < batch_limit:
                    break

        return candles

    async def stream_candles(
        self,
        query: CandleQuery,
    ) -> AsyncIterator[Candle]:
        """Stream Binance candles with health tracking and reconnection."""

        self._validate_query(query)

        interval = self.INTERVAL_MAP[query.timeframe]
        stream_name = f"{query.symbol.lower()}@kline_{interval}"
        websocket_url = f"{self.WEBSOCKET_URL}/{stream_name}"

        retry_delay = self.RECONNECT_INITIAL_DELAY_SECONDS

        while True:
            try:
                async with websockets.connect(
                    websocket_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                ) as websocket:
                    self.health_tracker.mark_connected(
                        self.name,
                        query.symbol,
                        query.timeframe.value,
                    )

                    retry_delay = self.RECONNECT_INITIAL_DELAY_SECONDS

                    try:
                        message_iterator = websocket.__aiter__()

                        while True:
                            try:
                                message = await asyncio.wait_for(
                                    message_iterator.__anext__(),
                                    timeout=self.message_timeout_seconds,
                                )
                            except StopAsyncIteration:
                                break
                            except TimeoutError as exc:
                                raise TimeoutError(
                                    "Binance WebSocket message timeout."
                                ) from exc

                            received_at = datetime.now(UTC)

                            # Record every incoming message, even if it
                            # does not contain a valid candle.
                            self.health_tracker.record_message(
                                self.name,
                                query.symbol,
                                query.timeframe.value,
                                received_at=received_at,
                            )

                            candle = self._parse_websocket_candle(
                                query.symbol,
                                query.timeframe,
                                message,
                            )

                            if candle is not None:
                                self.health_tracker.record_candle(
                                    candle,
                                    received_at=received_at,
                                )

                                yield candle

                    finally:
                        self.health_tracker.mark_disconnected(
                            self.name,
                            query.symbol,
                            query.timeframe.value,
                        )

            except (
                TimeoutError,
                OSError,
                websockets.exceptions.WebSocketException,
            ):
                self.health_tracker.mark_disconnected(
                    self.name,
                    query.symbol,
                    query.timeframe.value,
                )

            await asyncio.sleep(retry_delay)

            retry_delay = min(
                retry_delay * 2,
                self.RECONNECT_MAX_DELAY_SECONDS,
            )


binance_provider = BinanceProvider()
