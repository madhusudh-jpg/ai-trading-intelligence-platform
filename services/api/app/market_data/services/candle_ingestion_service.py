
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.candle import Candle as CandleModel
from app.db.models.instrument import Instrument
from app.db.models.instrument_provider_symbol import (
    InstrumentProviderSymbol,
)
from app.market_data.providers.registry import ProviderRegistry
from app.market_data.schemas.market_data import Candle, CandleQuery
from app.market_data.services.timeframes import is_candle_open_aligned


class CandleIngestionService:
    """Fetches and persists historical and live candles."""

    BATCH_SIZE = 1000

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _build_update_condition(statement):
        """Update only changed candles that are not already finalized."""

        excluded = statement.excluded

        has_changed_values = or_(
            CandleModel.close_time.is_distinct_from(excluded.close_time),
            CandleModel.open.is_distinct_from(excluded.open),
            CandleModel.high.is_distinct_from(excluded.high),
            CandleModel.low.is_distinct_from(excluded.low),
            CandleModel.close.is_distinct_from(excluded.close),
            CandleModel.volume.is_distinct_from(excluded.volume),
            CandleModel.is_complete.is_distinct_from(excluded.is_complete),
        )

        return and_(
            CandleModel.is_complete.is_(False),
            has_changed_values,
        )

    @staticmethod
    def _build_upsert_statement(rows):
        """Build an insert that safely updates incomplete candles."""

        statement = insert(CandleModel).values(rows)

        return statement.on_conflict_do_update(
            index_elements=[
                CandleModel.instrument_provider_symbol_id,
                CandleModel.timeframe,
                CandleModel.open_time,
            ],
            set_={
                "close_time": statement.excluded.close_time,
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "volume": statement.excluded.volume,
                "is_complete": statement.excluded.is_complete,
                "source_updated_at": statement.excluded.source_updated_at,
            },
            where=CandleIngestionService._build_update_condition(statement),
        )

    def ingest_live_candle(
        self,
        db: Session,
        provider_name: str,
        candle: Candle,
    ) -> dict[str, int | str]:
        """Validate and persist one live candle update."""

        provider_name = provider_name.strip().lower()

        try:
            if candle.provider.strip().lower() != provider_name:
                raise ValueError(
                    "Candle provider does not match the requested provider."
                )

            if candle.symbol != candle.symbol.upper():
                raise ValueError("Candle symbol must be uppercase.")

            if not is_candle_open_aligned(
                candle.open_time,
                candle.timeframe,
            ):
                raise ValueError(
                    "Live candle opening time is not timeframe-aligned."
                )

            self.registry.get(provider_name)

            mappings = db.scalars(
                select(InstrumentProviderSymbol).where(
                    InstrumentProviderSymbol.provider == provider_name,
                    InstrumentProviderSymbol.provider_symbol == candle.symbol,
                    InstrumentProviderSymbol.is_active.is_(True),
                )
            ).all()

            if not mappings:
                raise ValueError(
                    f"No active instrument mapping found for "
                    f"{provider_name}:{candle.symbol}"
                )

            if len(mappings) > 1:
                raise ValueError(
                    f"Multiple active mappings found for "
                    f"{provider_name}:{candle.symbol}."
                )

            mapping = mappings[0]
            instrument = db.get(Instrument, mapping.instrument_id)

            if instrument is None:
                raise ValueError(
                    "The mapped instrument does not exist."
                )

            if instrument.asset_class != candle.asset_class.value:
                raise ValueError(
                    "Instrument asset class does not match "
                    "the live candle asset class."
                )

            row = {
                "id": uuid4(),
                "instrument_id": mapping.instrument_id,
                "instrument_provider_symbol_id": mapping.id,
                "timeframe": candle.timeframe.value,
                "open_time": candle.open_time,
                "close_time": candle.close_time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "is_complete": candle.is_complete,
                "source_updated_at": datetime.now(UTC),
            }

            statement = self._build_upsert_statement(row)

            result = db.execute(
                statement.returning(CandleModel.id)
            )
            affected_ids = result.scalars().all()

            db.commit()

            return {
                "provider": provider_name,
                "received": 1,
                "upserted": len(affected_ids),
                "skipped": 1 - len(affected_ids),
            }

        except Exception:
            db.rollback()
            raise

    async def ingest_missing_range(
        self,
        db: Session,
        provider_name: str,
        query: CandleQuery,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int | str]:
        """Ingest one specifically identified missing candle range."""

        for field_name, value in (
            ("start_time", start_time),
            ("end_time", end_time),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(
                    f"{field_name} must be timezone-aware"
                )

        if end_time <= start_time:
            raise ValueError(
                "Missing range end_time must be later than start_time"
            )

        if not is_candle_open_aligned(start_time, query.timeframe):
            raise ValueError(
                "start_time must be aligned to a valid candle opening"
            )

        if not is_candle_open_aligned(end_time, query.timeframe):
            raise ValueError(
                "end_time must be aligned to a valid candle opening"
            )

        range_query = CandleQuery(
            symbol=query.symbol,
            asset_class=query.asset_class,
            timeframe=query.timeframe,
            start_time=start_time,
            end_time=end_time,
            limit=query.limit,
        )

        return await self.ingest_historical_candles(
            db=db,
            provider_name=provider_name,
            query=range_query,
        )

    async def ingest_historical_candles(
        self,
        db: Session,
        provider_name: str,
        query: CandleQuery,
    ) -> dict[str, int | str]:
        """Fetch and upsert historical candles in bounded batches."""

        provider_name = provider_name.strip().lower()
        provider = self.registry.get(provider_name)

        try:
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
                    "Resolve the mapping before ingestion."
                )

            mapping = mappings[0]
            instrument = db.get(Instrument, mapping.instrument_id)

            if instrument is None:
                raise ValueError(
                    "The mapped instrument does not exist."
                )

            if instrument.asset_class != query.asset_class.value:
                raise ValueError(
                    "Instrument asset class does not match "
                    "the requested candle asset class."
                )

            total_received = 0
            total_upserted = 0
            total_skipped = 0
            cursor = query.start_time

            while total_received < query.limit:
                batch_limit = min(
                    self.BATCH_SIZE,
                    query.limit - total_received,
                )

                batch_query = CandleQuery(
                    symbol=query.symbol,
                    asset_class=query.asset_class,
                    timeframe=query.timeframe,
                    start_time=cursor,
                    end_time=query.end_time,
                    limit=batch_limit,
                )

                candles = await provider.get_historical_candles(
                    batch_query
                )

                if not candles:
                    break

                candles.sort(key=lambda candle: candle.open_time)

                for candle in candles:
                    if (
                        candle.symbol != query.symbol.upper()
                        or candle.asset_class != query.asset_class
                        or candle.timeframe != query.timeframe
                        or candle.provider != provider_name
                    ):
                        raise ValueError(
                            "Provider returned a candle that does "
                            "not match the requested market data."
                        )

                    if not (
                        query.start_time
                        <= candle.open_time
                        < query.end_time
                    ):
                        raise ValueError(
                            "Provider returned a candle outside "
                            "the requested time range."
                        )

                next_cursor = candles[-1].close_time

                if next_cursor <= cursor:
                    raise RuntimeError(
                        "Provider returned a non-advancing "
                        "candle batch."
                    )

                now = datetime.now(UTC)

                rows = [
                    {
                        "id": uuid4(),
                        "instrument_id": mapping.instrument_id,
                        "instrument_provider_symbol_id": mapping.id,
                        "timeframe": candle.timeframe.value,
                        "open_time": candle.open_time,
                        "close_time": candle.close_time,
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                        "is_complete": candle.is_complete,
                        "source_updated_at": now,
                    }
                    for candle in candles
                ]

                statement = self._build_upsert_statement(rows)

                result = db.execute(
                    statement.returning(CandleModel.id)
                )
                affected_ids = result.scalars().all()

                total_received += len(candles)
                total_upserted += len(affected_ids)
                total_skipped += len(candles) - len(affected_ids)

                db.commit()
                cursor = next_cursor

                if len(candles) < batch_limit:
                    break

            return {
                "provider": provider_name,
                "received": total_received,
                "upserted": total_upserted,
                "skipped": total_skipped,
            }

        except Exception:
            db.rollback()
            raise
