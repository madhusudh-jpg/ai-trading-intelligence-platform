from collections.abc import Sequence
from decimal import Decimal

from app.ict_detection.displacement_schemas import (
    DisplacementDetectionConfig,
    DisplacementDirection,
    DisplacementEvent,
)
from app.market_data.schemas.market_data import Candle
from app.market_data.services.timeframes import next_candle_open


class DisplacementDetectionService:
    """
    Detect single-candle bullish and bearish displacement.

    ATR is calculated exclusively from preceding completed candles.
    A missing candle interval starts a new calculation segment.
    Forming candles are never used as displacement evidence.
    """

    def __init__(
        self,
        config: DisplacementDetectionConfig | None = None,
    ) -> None:
        self.config = config or DisplacementDetectionConfig()

    def detect(
        self,
        candles: Sequence[Candle],
    ) -> list[DisplacementEvent]:
        """Return qualifying displacement events chronologically."""

        ordered = self._prepare_candles(candles)

        if not ordered:
            return []

        segments = self._build_segments(ordered)
        events: list[DisplacementEvent] = []

        for segment_id, start, end in segments:
            segment = ordered[start:end]
            true_ranges = self._calculate_true_ranges(segment)

            for local_index in range(
                self.config.atr_period,
                len(segment),
            ):
                previous_ranges = true_ranges[
                    local_index - self.config.atr_period : local_index
                ]

                atr = sum(previous_ranges, Decimal("0")) / Decimal(
                    self.config.atr_period
                )

                if atr <= 0:
                    continue

                candle = segment[local_index]

                event = self._evaluate_candle(
                    candle=candle,
                    atr=atr,
                    true_range=true_ranges[local_index],
                    candle_index=start + local_index,
                    segment_id=segment_id,
                )

                if event is not None:
                    events.append(event)

        return events

    @staticmethod
    def _prepare_candles(
        candles: Sequence[Candle],
    ) -> list[Candle]:
        """Validate one candle stream and remove forming candles."""

        materialized = list(candles)

        if not materialized:
            return []

        first = materialized[0]

        expected_metadata = (
            first.symbol.strip().upper(),
            first.asset_class,
            first.timeframe,
            first.provider.strip().lower(),
        )

        for candle in materialized:
            actual_metadata = (
                candle.symbol.strip().upper(),
                candle.asset_class,
                candle.timeframe,
                candle.provider.strip().lower(),
            )

            if actual_metadata != expected_metadata:
                raise ValueError(
                    "All candles must belong to the same symbol, "
                    "asset class, timeframe and provider."
                )

        ordered = sorted(
            materialized,
            key=lambda candle: candle.open_time,
        )

        for previous, current in zip(
            ordered,
            ordered[1:],
            strict=False,
        ):
            if previous.open_time == current.open_time:
                raise ValueError("Duplicate candle opening timestamps found.")

        return [candle for candle in ordered if candle.is_complete]

    @staticmethod
    def _build_segments(
        candles: Sequence[Candle],
    ) -> list[tuple[int, int, int]]:
        """Split candles at missing expected time intervals."""

        if not candles:
            return []

        timeframe = candles[0].timeframe
        segments = []
        segment_start = 0
        segment_id = 0

        for index in range(1, len(candles)):
            expected_open = next_candle_open(
                candles[index - 1].open_time,
                timeframe,
            )

            if candles[index].open_time != expected_open:
                segments.append((segment_id, segment_start, index))
                segment_id += 1
                segment_start = index

        segments.append((segment_id, segment_start, len(candles)))

        return segments

    @staticmethod
    def _calculate_true_ranges(
        candles: Sequence[Candle],
    ) -> list[Decimal]:
        """Calculate True Range inside one contiguous segment."""

        ranges = []

        for index, candle in enumerate(candles):
            high_low = candle.high - candle.low

            if index == 0:
                ranges.append(high_low)
                continue

            previous_close = candles[index - 1].close

            ranges.append(
                max(
                    high_low,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            )

        return ranges

    def _evaluate_candle(
        self,
        candle: Candle,
        atr: Decimal,
        true_range: Decimal,
        candle_index: int,
        segment_id: int,
    ) -> DisplacementEvent | None:
        """Apply directional displacement thresholds."""

        candle_range = candle.high - candle.low

        if candle_range <= 0:
            return None

        if candle.close > candle.open:
            direction = DisplacementDirection.BULLISH
            close_location = (candle.close - candle.low) / candle_range
            opposing_wick = (candle.open - candle.low) / candle_range

        elif candle.close < candle.open:
            direction = DisplacementDirection.BEARISH
            close_location = (candle.high - candle.close) / candle_range
            opposing_wick = (candle.high - candle.open) / candle_range

        else:
            return None

        body_ratio = abs(candle.close - candle.open) / candle_range
        range_expansion_atr = true_range / atr

        if body_ratio < self.config.min_body_ratio:
            return None

        if range_expansion_atr < self.config.min_range_expansion_atr:
            return None

        if close_location < self.config.min_directional_close_location:
            return None

        if opposing_wick > self.config.max_opposing_wick_ratio:
            return None

        return DisplacementEvent(
            symbol=candle.symbol,
            asset_class=candle.asset_class,
            timeframe=candle.timeframe,
            provider=candle.provider,
            direction=direction,
            candle_index=candle_index,
            segment_id=segment_id,
            open_time=candle.open_time,
            close_time=candle.close_time,
            confirmed_at=candle.close_time,
            open_price=candle.open,
            close_price=candle.close,
            high_price=candle.high,
            low_price=candle.low,
            true_range=true_range,
            atr_value=atr,
            body_ratio=body_ratio,
            range_expansion_atr=range_expansion_atr,
            directional_close_location=close_location,
            opposing_wick_ratio=opposing_wick,
        )


__all__ = ["DisplacementDetectionService"]
