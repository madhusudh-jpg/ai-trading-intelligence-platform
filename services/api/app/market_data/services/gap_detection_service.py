
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle as CandleModel
from app.db.models.instrument import Instrument
from app.db.models.instrument_provider_symbol import (
    InstrumentProviderSymbol,
)
from app.market_data.schemas.market_data import Timeframe
from app.market_data.services.timeframes import (
    is_candle_open_aligned,
    next_candle_open,
)


class CandleGapDetectionService:
    """Detect missing completed candles without modifying stored data."""

    MAX_EXPECTED_CANDLES = 100_000

    def find_missing_candles(
        self,
        db: Session,
        instrument_provider_symbol_id: UUID,
        timeframe: Timeframe,
        start_time: datetime,
        end_time: datetime,
        as_of: datetime | None = None,
    ) -> dict:
        """Find missing Binance crypto candles in a UTC time range.

        start_time must be aligned to a candle opening.
        end_time is exclusive.
        Only candles whose intervals have ended are considered.
        This method performs database reads only.
        """

        if start_time.tzinfo is None or start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware")

        if end_time.tzinfo is None or end_time.utcoffset() is None:
            raise ValueError("end_time must be timezone-aware")

        if end_time <= start_time:
            raise ValueError("end_time must be later than start_time")

        if as_of is None:
            as_of = datetime.now(UTC)
        elif as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")

        start_time = start_time.astimezone(UTC)
        end_time = end_time.astimezone(UTC)
        as_of = as_of.astimezone(UTC)

        if not is_candle_open_aligned(start_time, timeframe):
            raise ValueError(
                "start_time must be aligned to a valid candle opening"
            )

        mapping = db.get(
            InstrumentProviderSymbol,
            instrument_provider_symbol_id,
        )

        if mapping is None or not mapping.is_active:
            raise ValueError("Active provider-symbol mapping not found")

        if mapping.provider.lower() != "binance":
            raise ValueError(
                "Initial gap detection supports Binance only"
            )

        instrument = db.get(Instrument, mapping.instrument_id)

        if instrument is None or instrument.asset_class != "crypto":
            raise ValueError(
                "Initial gap detection supports crypto instruments only"
            )

        expected_times: list[datetime] = []
        cursor = start_time

        while cursor < end_time:
            next_time = next_candle_open(cursor, timeframe)

            # Do not classify a still-forming candle as missing.
            if next_time > as_of:
                break

            expected_times.append(cursor)

            if len(expected_times) > self.MAX_EXPECTED_CANDLES:
                raise ValueError(
                    "Requested range exceeds the gap-detection limit"
                )

            cursor = next_time

        if not expected_times:
            return {
                "provider": "binance",
                "timeframe": timeframe.value,
                "expected_candles": 0,
                "stored_candles": 0,
                "missing_count": 0,
                "missing_candles": [],
                "missing_ranges": [],
            }

        stored_times = set(
            db.scalars(
                select(CandleModel.open_time).where(
                    CandleModel.instrument_provider_symbol_id
                    == instrument_provider_symbol_id,
                    CandleModel.timeframe == timeframe.value,
                    CandleModel.open_time >= expected_times[0],
                    CandleModel.open_time <= expected_times[-1],
                    CandleModel.is_complete.is_(True),
                )
            ).all()
        )

        stored_times = {
            timestamp.astimezone(UTC)
            for timestamp in stored_times
        }

        missing_times = [
            timestamp
            for timestamp in expected_times
            if timestamp not in stored_times
        ]

        missing_ranges = []

        if missing_times:
            range_start = missing_times[0]
            previous_missing = missing_times[0]

            for timestamp in missing_times[1:]:
                expected_after_previous = next_candle_open(
                    previous_missing,
                    timeframe,
                )

                if timestamp != expected_after_previous:
                    missing_ranges.append(
                        {
                            "start_time": range_start,
                            "end_time": expected_after_previous,
                        }
                    )
                    range_start = timestamp

                previous_missing = timestamp

            missing_ranges.append(
                {
                    "start_time": range_start,
                    "end_time": next_candle_open(
                        previous_missing,
                        timeframe,
                    ),
                }
            )

        return {
            "provider": "binance",
            "timeframe": timeframe.value,
            "expected_candles": len(expected_times),
            "stored_candles": len(expected_times) - len(missing_times),
            "missing_count": len(missing_times),
            "missing_candles": missing_times,
            "missing_ranges": missing_ranges,
        }
