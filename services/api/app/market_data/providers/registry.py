from app.market_data.providers.base import MarketDataProvider


class ProviderRegistry:
    """Maintains the registered market-data providers."""

    def __init__(self) -> None:
        self._providers: dict[str, MarketDataProvider] = {}

    def register(self, provider: MarketDataProvider) -> None:
        name = provider.name.strip().lower()

        if not name:
            raise ValueError("Provider name cannot be empty")

        if name in self._providers:
            raise ValueError(
                f"Provider '{name}' is already registered"
            )

        self._providers[name] = provider

    def get(self, name: str) -> MarketDataProvider:
        key = name.strip().lower()

        if key not in self._providers:
            raise KeyError(
                f"Market-data provider '{key}' is not registered"
            )

        return self._providers[key]

    def list_providers(self) -> list[MarketDataProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return sorted(self._providers)


provider_registry = ProviderRegistry()