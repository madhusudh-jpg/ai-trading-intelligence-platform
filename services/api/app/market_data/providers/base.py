
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.market_data.providers.capabilities import ProviderCapabilities
from app.market_data.schemas.market_data import (
    Candle,
    CandleQuery,
    ProviderStatus,
)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Standard interface for all market-data providers."""

    name: str

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Describe the provider's verified data capabilities."""
        ...

    async def get_status(self) -> ProviderStatus:
        """Check provider configuration and connection status."""
        ...

    async def get_historical_candles(
        self,
        query: CandleQuery,
    ) -> list[Candle]:
        """Retrieve historical OHLCV candles."""
        ...

    def stream_candles(
        self,
        query: CandleQuery,
    ) -> AsyncIterator[Candle]:
        """Stream live candle updates when supported."""
        ...
