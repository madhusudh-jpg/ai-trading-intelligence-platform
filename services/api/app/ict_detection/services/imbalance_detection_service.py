
from collections.abc import Sequence
from decimal import Decimal

from app.ict_detection.imbalance_schemas import (
    BalancedPriceRange,
    FairValueGap,
    ImbalanceDetectionConfig,
    ImbalanceDirection,
    InverseFairValueGap,
    InverseFVGStatus,
)
from app.market_data.schemas.market_data import Candle
from app.market_data.services.timeframes import next_candle_open


class ImbalanceDetectionService:
    """
    Detect Fair Value Gaps, Inverse FVGs and Balanced Price Ranges.

    Only completed candles are used.
    FVGs require three consecutive candles.
    Missing candle intervals create separate detection segments.
    IFVGs require a later completed candle to close through
    the original FVG boundary.
    """

    def __init__(
        self,
        config: ImbalanceDetectionConfig | None = None,
    ) -> None:
        self.config = config or ImbalanceDetectionConfig()

    def detect_fvgs(
        self,
        candles: Sequence[Candle],
    ) -> list[FairValueGap]:
        """Detect bullish and bearish three-candle fair value gaps."""

        ordered = self._prepare_candles(candles)

        if len(ordered) < 3:
            return []

        segments = self._build_segments(ordered)
        events: list[FairValueGap] = []

        for segment_id, start, end in segments:
            segment = ordered[start:end]

            for local_index in range(2, len(segment)):
                first = segment[local_index - 2]
                middle = segment[local_index - 1]
                third = segment[local_index]

                event = self._evaluate_fvg(
                    first=first,
                    middle=middle,
                    third=third,
                    first_index=start + local_index - 2,
                    middle_index=start + local_index - 1,
                    third_index=start + local_index,
                    segment_id=segment_id,
                )

                if event is not None:
                    events.append(event)

        return events

    def detect_ifvgs(
        self,
        candles: Sequence[Candle],
        fvgs: Sequence[FairValueGap],
    ) -> list[InverseFairValueGap]:
        """
        Detect the first confirmed close-through of each original FVG.

        Bullish FVG: a later close below its lower boundary creates
        a bearish IFVG.

        Bearish FVG: a later close above its upper boundary creates
        a bullish IFVG.
        """

        ordered = self._prepare_candles(candles)

        self._validate_fvgs(fvgs)

        if not ordered or not fvgs:
            return []

        segments = self._build_segments(ordered)
        candle_segments: dict[int, int] = {}

        for segment_id, start, end in segments:
            for index in range(start, end):
                candle_segments[index] = segment_id

        events: list[InverseFairValueGap] = []

        for fvg in fvgs:
            for index, candle in enumerate(ordered):
                if candle.open_time < fvg.confirmation_time:
                    continue

                if candle.close_time <= fvg.confirmation_time:
                    continue

                if candle_segments.get(index) != fvg.segment_id:
                    continue

                if index - fvg.confirmation_candle_index > (
                    self.config.maximum_age_bars
                ):
                    break

                inverse_direction = self._get_invalidation_direction(
                    candle=candle,
                    fvg=fvg,
                )

                if inverse_direction is None:
                    continue

                events.append(
                    InverseFairValueGap(
                        original_fvg=fvg,
                        inverse_direction=inverse_direction,
                        status=InverseFVGStatus.CONFIRMED,
                        invalidation_candle_time=candle.open_time,
                        confirmed_at=candle.close_time,
                        invalidation_candle_index=index,
                    )
                )

                # Only the first invalidation is reported per FVG.
                break

        return sorted(
            events,
            key=lambda event: event.confirmed_at,
        )

    def detect_bprs(
        self,
        fvgs: Sequence[FairValueGap],
    ) -> list[BalancedPriceRange]:
        """
        Detect overlapping bullish and bearish FVGs.

        Both FVGs must already be confirmed. The BPR confirmation
        time is the later of the two FVG confirmation times.
        """

        self._validate_fvgs(fvgs)

        bullish = [
            fvg
            for fvg in fvgs
            if fvg.direction == ImbalanceDirection.BULLISH
        ]

        bearish = [
            fvg
            for fvg in fvgs
            if fvg.direction == ImbalanceDirection.BEARISH
        ]

        events: list[BalancedPriceRange] = []

        for bullish_fvg in bullish:
            for bearish_fvg in bearish:
                if not self._same_fvg_stream(
                    bullish_fvg,
                    bearish_fvg,
                ):
                    continue

                lower_bound = max(
                    bullish_fvg.lower_bound,
                    bearish_fvg.lower_bound,
                )

                upper_bound = min(
                    bullish_fvg.upper_bound,
                    bearish_fvg.upper_bound,
                )

                overlap_size = upper_bound - lower_bound

                if overlap_size <= 0:
                    continue

                if overlap_size < self.config.minimum_overlap_size:
                    continue

                midpoint = (
                    lower_bound + upper_bound
                ) / Decimal("2")

                events.append(
                    BalancedPriceRange(
                        symbol=bullish_fvg.symbol,
                        asset_class=bullish_fvg.asset_class,
                        timeframe=bullish_fvg.timeframe,
                        provider=bullish_fvg.provider,
                        bullish_fvg=bullish_fvg,
                        bearish_fvg=bearish_fvg,
                        lower_bound=lower_bound,
                        upper_bound=upper_bound,
                        overlap_size=overlap_size,
                        consequent_encroachment=midpoint,
                        confirmed_at=max(
                            bullish_fvg.confirmed_at,
                            bearish_fvg.confirmed_at,
                        ),
                        segment_id=bullish_fvg.segment_id,
                    )
                )

        return sorted(
            events,
            key=lambda event: event.confirmed_at,
        )

    def detect(
        self,
        candles: Sequence[Candle],
    ) -> tuple[
        list[FairValueGap],
        list[InverseFairValueGap],
        list[BalancedPriceRange],
    ]:
        """Run FVG, IFVG and BPR detection."""

        fvgs = self.detect_fvgs(candles)

        ifvgs = self.detect_ifvgs(
            candles=candles,
            fvgs=fvgs,
        )

        bprs = self.detect_bprs(fvgs)

        return fvgs, ifvgs, bprs

    def _evaluate_fvg(
        self,
        first: Candle,
        middle: Candle,
        third: Candle,
        first_index: int,
        middle_index: int,
        third_index: int,
        segment_id: int,
    ) -> FairValueGap | None:
        """Evaluate a three-candle FVG."""

        direction: ImbalanceDirection
        lower_bound: Decimal
        upper_bound: Decimal

        if first.high < third.low:
            direction = ImbalanceDirection.BULLISH
            lower_bound = first.high
            upper_bound = third.low

        elif first.low > third.high:
            direction = ImbalanceDirection.BEARISH
            lower_bound = third.high
            upper_bound = first.low

        else:
            return None

        gap_size = upper_bound - lower_bound

        if gap_size < self.config.minimum_gap_size:
            return None

        midpoint = (
            lower_bound + upper_bound
        ) / Decimal("2")

        return FairValueGap(
            symbol=first.symbol,
            asset_class=first.asset_class,
            timeframe=first.timeframe,
            provider=first.provider,
            direction=direction,
            first_candle_time=first.open_time,
            middle_candle_time=middle.open_time,
            confirmation_time=third.close_time,
            confirmed_at=third.close_time,
            first_candle_index=first_index,
            middle_candle_index=middle_index,
            confirmation_candle_index=third_index,
            segment_id=segment_id,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            gap_size=gap_size,
            consequent_encroachment=midpoint,
        )

    @staticmethod
    def _get_invalidation_direction(
        candle: Candle,
        fvg: FairValueGap,
    ) -> ImbalanceDirection | None:
        """Check whether a completed candle closes through an FVG."""

        if (
            fvg.direction == ImbalanceDirection.BULLISH
            and candle.close < fvg.lower_bound
        ):
            return ImbalanceDirection.BEARISH

        if (
            fvg.direction == ImbalanceDirection.BEARISH
            and candle.close > fvg.upper_bound
        ):
            return ImbalanceDirection.BULLISH

        return None

    @staticmethod
    def _same_fvg_stream(
        first: FairValueGap,
        second: FairValueGap,
    ) -> bool:
        return (
            first.symbol == second.symbol
            and first.asset_class == second.asset_class
            and first.timeframe == second.timeframe
            and first.provider == second.provider
            and first.segment_id == second.segment_id
        )

    @staticmethod
    def _validate_fvgs(
        fvgs: Sequence[FairValueGap],
    ) -> None:
        """Validate that supplied FVGs belong to one market stream."""

        if not fvgs:
            return

        first = fvgs[0]

        for fvg in fvgs:
            if not ImbalanceDetectionService._same_market_stream(
                first,
                fvg,
            ):
                raise ValueError(
                    "All FVGs must belong to the same market stream."
                )

    @staticmethod
    def _same_market_stream(
        first: FairValueGap,
        second: FairValueGap,
    ) -> bool:
        return (
            first.symbol == second.symbol
            and first.asset_class == second.asset_class
            and first.timeframe == second.timeframe
            and first.provider == second.provider
        )

    @staticmethod
    def _prepare_candles(
        candles: Sequence[Candle],
    ) -> list[Candle]:
        """Validate a single candle stream and remove forming candles."""

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
                raise ValueError(
                    "Duplicate candle opening timestamps found."
                )

        return [
            candle
            for candle in ordered
            if candle.is_complete
        ]

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
                segments.append(
                    (segment_id, segment_start, index)
                )
                segment_id += 1
                segment_start = index

        segments.append(
            (segment_id, segment_start, len(candles))
        )

        return segments


__all__ = ["ImbalanceDetectionService"]
