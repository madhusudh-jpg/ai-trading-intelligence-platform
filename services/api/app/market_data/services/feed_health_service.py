
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.market_data.schemas.market_data import (
    Candle,
    DataStatus,
)


@dataclass
class FeedHealth:
    """Runtime health information for one market-data stream."""

    provider: str
    symbol: str
    timeframe: str

    connected: bool = False
    last_message_at: datetime | None = None
    last_candle_at: datetime | None = None
    last_completed_candle_at: datetime | None = None

    data_status: DataStatus = DataStatus.UNAVAILABLE
    message: str | None = None


class FeedHealthTracker:
    """Track connection and data freshness for individual streams."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        delayed_after_seconds: float = 30,
        stale_after_seconds: float = 60,
    ) -> None:
        if delayed_after_seconds <= 0:
            raise ValueError("Delayed threshold must be positive.")

        if stale_after_seconds <= delayed_after_seconds:
            raise ValueError(
                "Stale threshold must be greater than delayed threshold."
            )

        self._clock = clock or (lambda: datetime.now(UTC))
        self.delayed_after_seconds = delayed_after_seconds
        self.stale_after_seconds = stale_after_seconds

        self._feeds: dict[tuple[str, str, str], FeedHealth] = {}

    @staticmethod
    def _key(
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> tuple[str, str, str]:
        return (
            provider.strip().lower(),
            symbol.strip().upper(),
            timeframe.strip().lower(),
        )

    def _get_or_create(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> FeedHealth:
        key = self._key(provider, symbol, timeframe)

        if key not in self._feeds:
            self._feeds[key] = FeedHealth(
                provider=key[0],
                symbol=key[1],
                timeframe=key[2],
            )

        return self._feeds[key]

    def mark_connected(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        feed = self._get_or_create(provider, symbol, timeframe)

        feed.connected = True
        feed.message = "Live stream connected."

    def mark_disconnected(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        feed = self._get_or_create(provider, symbol, timeframe)

        feed.connected = False
        feed.data_status = DataStatus.UNAVAILABLE
        feed.message = "Live stream disconnected."

    def record_message(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        received_at: datetime | None = None,
    ) -> None:
        feed = self._get_or_create(provider, symbol, timeframe)

        timestamp = received_at or self._clock()

        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Message timestamp must be timezone-aware.")

        feed.last_message_at = timestamp.astimezone(UTC)

    def record_candle(
        self,
        candle: Candle,
        received_at: datetime | None = None,
    ) -> None:
        timestamp = received_at or self._clock()

        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Candle receipt timestamp must be timezone-aware.")

        timestamp = timestamp.astimezone(UTC)

        feed = self._get_or_create(
            candle.provider,
            candle.symbol,
            candle.timeframe.value,
        )

        feed.last_message_at = timestamp
        feed.last_candle_at = timestamp

        if candle.is_complete:
            feed.last_completed_candle_at = candle.close_time

        feed.data_status = DataStatus.REALTIME
        feed.message = "Market-data updates are being received."

    def evaluate_feed(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> FeedHealth | None:
        feed = self.get_feed(provider, symbol, timeframe)

        if feed is None:
            return None

        if not feed.connected:
            feed.data_status = DataStatus.UNAVAILABLE
            feed.message = "Live stream disconnected."
            return feed

        if feed.last_message_at is None:
            feed.data_status = DataStatus.UNAVAILABLE
            feed.message = "Waiting for the first provider message."
            return feed

        now = self._clock()

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Clock must return a timezone-aware datetime.")

        age_seconds = (
            now.astimezone(UTC) - feed.last_message_at
        ).total_seconds()

        if age_seconds < 0:
            feed.data_status = DataStatus.UNAVAILABLE
            feed.message = "Last message timestamp is in the future."

        elif age_seconds <= self.delayed_after_seconds:
            feed.data_status = DataStatus.REALTIME
            feed.message = "Market-data feed is healthy."

        elif age_seconds <= self.stale_after_seconds:
            feed.data_status = DataStatus.DELAYED
            feed.message = "Market-data feed is delayed."

        else:
            feed.data_status = DataStatus.STALE
            feed.message = "No recent provider messages received."

        return feed

    def evaluate_all(self) -> list[FeedHealth]:
        return [
            self.evaluate_feed(
                feed.provider,
                feed.symbol,
                feed.timeframe,
            )
            for feed in self._feeds.values()
        ]

    def get_feed(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> FeedHealth | None:
        return self._feeds.get(
            self._key(provider, symbol, timeframe)
        )

    def get_all_feeds(self) -> list[FeedHealth]:
        return list(self._feeds.values())
