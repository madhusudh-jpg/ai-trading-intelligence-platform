from collections.abc import Sequence

from app.ict_detection.schemas import (
    SwingConfirmationBasis,
    SwingDetectionConfig,
    SwingPoint,
    SwingTier,
    SwingType,
)
from app.market_data.schemas.market_data import Candle
from app.market_data.services.timeframes import next_candle_open


class SwingDetectionService:
    """
    Detect confirmed short-, intermediate- and long-term swings.

    Short-term swings use a configurable left/right candle pivot.

    Intermediate-term swings are derived from neighbouring
    short-term swings of the same type.

    Long-term swings are derived from neighbouring
    intermediate-term swings of the same type.

    Only completed candles are considered. Swing confirmation
    never uses candles outside the supplied historical sequence.
    """

    def __init__(
        self,
        config: SwingDetectionConfig | None = None,
    ) -> None:
        self.config = config or SwingDetectionConfig()

    def detect(
        self,
        candles: Sequence[Candle],
    ) -> list[SwingPoint]:
        """
        Detect confirmed swings from a chronological candle sequence.

        Input candles may be unordered, but must belong to the
        same symbol, asset class, timeframe and provider.

        Missing candle intervals create separate detection segments.
        No pivot or hierarchy may be confirmed across those segments.
        """

        completed_candles = self._prepare_candles(candles)

        if not completed_candles:
            return []

        segments = self._build_contiguous_segments(completed_candles)

        short_term = self._detect_short_term(
            completed_candles,
            segments,
        )

        results = list(short_term)

        if not self.config.include_hierarchy:
            return self._sort_results(results)

        intermediate_term = self._derive_hierarchy(
            short_term,
            SwingTier.INTERMEDIATE_TERM,
        )

        long_term = self._derive_hierarchy(
            intermediate_term,
            SwingTier.LONG_TERM,
        )

        results.extend(intermediate_term)
        results.extend(long_term)

        return self._sort_results(results)

    @staticmethod
    def _prepare_candles(
        candles: Sequence[Candle],
    ) -> list[Candle]:
        """Validate dataset consistency and return completed candles."""

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
    def _build_contiguous_segments(
        candles: Sequence[Candle],
    ) -> list[tuple[int, int, int]]:
        """
        Build contiguous candle segments.

        Each tuple contains:
            (segment_id, start_index, end_index)

        The end index is exclusive.
        """

        if not candles:
            return []

        timeframe = candles[0].timeframe

        segments: list[tuple[int, int, int]] = []

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

    def _detect_short_term(
        self,
        candles: Sequence[Candle],
        segments: list[tuple[int, int, int]],
    ) -> list[SwingPoint]:
        """Detect strict left/right candle pivots."""

        left_bars = self.config.left_bars
        right_bars = self.config.right_bars

        results: list[SwingPoint] = []

        for segment_id, start, end in segments:
            first_candidate = start + left_bars
            final_candidate = end - right_bars

            for pivot_index in range(
                first_candidate,
                final_candidate,
            ):
                candidate = candles[pivot_index]

                left_candles = candles[pivot_index - left_bars : pivot_index]

                right_candles = candles[pivot_index + 1 : pivot_index + right_bars + 1]

                neighbours = [
                    *left_candles,
                    *right_candles,
                ]

                neighbour_highs = [candle.high for candle in neighbours]

                neighbour_lows = [candle.low for candle in neighbours]

                if candidate.high > max(neighbour_highs):
                    results.append(
                        self._create_short_term_point(
                            candle=candidate,
                            pivot_index=pivot_index,
                            segment_id=segment_id,
                            swing_type=SwingType.HIGH,
                            price=candidate.high,
                            confirmed_at=right_candles[-1].close_time,
                        )
                    )

                if candidate.low < min(neighbour_lows):
                    results.append(
                        self._create_short_term_point(
                            candle=candidate,
                            pivot_index=pivot_index,
                            segment_id=segment_id,
                            swing_type=SwingType.LOW,
                            price=candidate.low,
                            confirmed_at=right_candles[-1].close_time,
                        )
                    )

        return results

    def _create_short_term_point(
        self,
        candle: Candle,
        pivot_index: int,
        segment_id: int,
        swing_type: SwingType,
        price,
        confirmed_at,
    ) -> SwingPoint:
        """Create a confirmed short-term swing point."""

        return SwingPoint(
            symbol=candle.symbol,
            asset_class=candle.asset_class,
            timeframe=candle.timeframe,
            provider=candle.provider,
            swing_type=swing_type,
            tier=SwingTier.SHORT_TERM,
            price=price,
            pivot_time=candle.open_time,
            confirmed_at=confirmed_at,
            pivot_index=pivot_index,
            segment_id=segment_id,
            left_bars=self.config.left_bars,
            right_bars=self.config.right_bars,
            hierarchy_left_points=0,
            hierarchy_right_points=0,
            confirmation_basis=SwingConfirmationBasis.FRACTAL,
        )

    @staticmethod
    def _derive_hierarchy(
        source_points: Sequence[SwingPoint],
        target_tier: SwingTier,
    ) -> list[SwingPoint]:
        """
        Derive the next swing hierarchy level.

        A high must exceed both neighbouring highs of the
        same hierarchy level.

        A low must be below both neighbouring lows.

        Confirmation is delayed until all three source swings
        are themselves confirmed.
        """

        grouped: dict[
            tuple[int, SwingType],
            list[SwingPoint],
        ] = {}

        for point in source_points:
            key = (point.segment_id, point.swing_type)
            grouped.setdefault(key, []).append(point)

        results: list[SwingPoint] = []

        for group in grouped.values():
            ordered = sorted(
                group,
                key=lambda point: point.pivot_index,
            )

            for index in range(1, len(ordered) - 1):
                previous = ordered[index - 1]
                current = ordered[index]
                following = ordered[index + 1]

                if current.swing_type == SwingType.HIGH:
                    is_higher = (
                        current.price > previous.price
                        and current.price > following.price
                    )

                else:
                    is_higher = (
                        current.price < previous.price
                        and current.price < following.price
                    )

                if not is_higher:
                    continue

                confirmation_time = max(
                    previous.confirmed_at,
                    current.confirmed_at,
                    following.confirmed_at,
                )

                results.append(
                    current.model_copy(
                        update={
                            "tier": target_tier,
                            "confirmed_at": confirmation_time,
                            "hierarchy_left_points": 1,
                            "hierarchy_right_points": 1,
                            "confirmation_basis": (
                                SwingConfirmationBasis.NESTED_HIERARCHY
                            ),
                        }
                    )
                )

        return results

    @staticmethod
    def _sort_results(
        points: list[SwingPoint],
    ) -> list[SwingPoint]:
        """Return deterministic chronological output."""

        tier_order = {
            SwingTier.SHORT_TERM: 0,
            SwingTier.INTERMEDIATE_TERM: 1,
            SwingTier.LONG_TERM: 2,
        }

        return sorted(
            points,
            key=lambda point: (
                point.pivot_time,
                point.swing_type.value,
                tier_order[point.tier],
            ),
        )


__all__ = ["SwingDetectionService"]
