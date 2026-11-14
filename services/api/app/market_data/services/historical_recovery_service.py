
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.instrument_provider_symbol import (
    InstrumentProviderSymbol,
)
from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import CandleQuery
from app.market_data.services.candle_ingestion_service import (
    CandleIngestionService,
)
from app.market_data.services.gap_detection_service import (
    CandleGapDetectionService,
)


class HistoricalRecoveryService:
    """Coordinates detection, recovery and verification of candle gaps."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry
        self.gap_detector = CandleGapDetectionService()
        self.ingestion_service = CandleIngestionService(registry)

    async def recover_missing_candles(
        self,
        db: Session,
        provider_name: str,
        query: CandleQuery,
        as_of: datetime | None = None,
    ) -> dict:
        """Detect missing candles, recover them and verify the result."""

        provider_name = provider_name.strip().lower()

        if provider_name != "binance":
            raise ValueError(
                "Historical recovery currently supports Binance only."
            )

        mappings = db.scalars(
            select(InstrumentProviderSymbol).where(
                InstrumentProviderSymbol.provider == provider_name,
                InstrumentProviderSymbol.provider_symbol
                == query.symbol.upper(),
                InstrumentProviderSymbol.is_active.is_(True),
            )
        ).all()

        if not mappings:
            raise ValueError(
                f"No active instrument mapping found for "
                f"{provider_name}:{query.symbol}"
            )

        if len(mappings) > 1:
            raise ValueError(
                f"Multiple active mappings found for "
                f"{provider_name}:{query.symbol}. "
                "Resolve the mapping before recovery."
            )

        mapping = mappings[0]

        initial_report = self.gap_detector.find_missing_candles(
            db=db,
            instrument_provider_symbol_id=mapping.id,
            timeframe=query.timeframe,
            start_time=query.start_time,
            end_time=query.end_time,
            as_of=as_of,
        )

        initial_ranges = initial_report["missing_ranges"]

        total_received = 0
        total_upserted = 0

        for missing_range in initial_ranges:
            result = await self.ingestion_service.ingest_missing_range(
                db=db,
                provider_name=provider_name,
                query=query,
                start_time=missing_range["start_time"],
                end_time=missing_range["end_time"],
            )

            total_received += int(result["received"])
            total_upserted += int(result["upserted"])

        final_report = self.gap_detector.find_missing_candles(
            db=db,
            instrument_provider_symbol_id=mapping.id,
            timeframe=query.timeframe,
            start_time=query.start_time,
            end_time=query.end_time,
            as_of=as_of,
        )

        return {
            "provider": provider_name,
            "symbol": query.symbol.upper(),
            "timeframe": query.timeframe.value,
            "initial_missing_count": initial_report["missing_count"],
            "ranges_attempted": len(initial_ranges),
            "received": total_received,
            "upserted": total_upserted,
            "remaining_missing_count": final_report["missing_count"],
            "remaining_missing_ranges": final_report["missing_ranges"],
            "recovery_complete": final_report["missing_count"] == 0,
        }
