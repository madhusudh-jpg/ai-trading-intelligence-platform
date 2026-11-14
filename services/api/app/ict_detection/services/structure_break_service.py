from collections.abc import Sequence

from app.ict_detection.displacement_schemas import (
    DisplacementDirection,
    DisplacementEvent,
)
from app.ict_detection.market_structure_schemas import (
    MarketStructureConfig,
    MarketTrend,
    StructureScope,
)
from app.ict_detection.schemas import SwingPoint, SwingTier, SwingType
from app.ict_detection.services.market_structure_service import (
    MarketStructureService,
)
from app.ict_detection.structure_break_schemas import (
    BreakDirection,
    LiquiditySide,
    LiquiditySweepEvidence,
    StructureBreakConfig,
    StructureBreakEvent,
    StructureBreakProfile,
    StructureEventType,
)
from app.market_data.schemas.market_data import Candle
from app.market_data.services.timeframes import next_candle_open


class StructureBreakService:
    """Detect BOS, CHoCH and MSS from confirmed market structure."""

    def __init__(
        self,
        config: StructureBreakConfig | None = None,
    ) -> None:
        self.config = config or StructureBreakConfig()

        self.structure_service = MarketStructureService(
            MarketStructureConfig(price_tolerance=self.config.structure_tolerance)
        )

    def detect(
        self,
        candles: Sequence[Candle],
        swings: Sequence[SwingPoint],
        displacements: Sequence[DisplacementEvent] = (),
        liquidity_sweeps: Sequence[LiquiditySweepEvidence] = (),
    ) -> list[StructureBreakEvent]:
        """Return confirmed structural breaks chronologically."""

        ordered = self._prepare_candles(candles)

        if not ordered or not swings:
            return []

        segments = self._build_segments(ordered)

        metadata = self._build_candle_metadata(
            ordered,
            segments,
        )

        validated_swings = self._validate_swings(
            swings,
            ordered,
            metadata,
        )

        displacement_map = self._validate_displacements(
            displacements,
            ordered,
            metadata,
        )

        validated_sweeps = self._validate_sweeps(
            liquidity_sweeps,
            ordered,
            metadata,
        )

        events: list[StructureBreakEvent] = []
        event_keys = set()

        ordered_swings = sorted(
            validated_swings,
            key=lambda item: item[1],
            reverse=True,
        )

        for swing, _, confirmation_index, segment_id in ordered_swings:
            direction = (
                BreakDirection.BULLISH
                if swing.swing_type == SwingType.HIGH
                else BreakDirection.BEARISH
            )

            threshold = (
                swing.price + self.config.break_buffer
                if direction == BreakDirection.BULLISH
                else swing.price - self.config.break_buffer
            )

            segment_end = next(
                end
                for current_segment, _, end in segments
                if current_segment == segment_id
            )

            for candle_index in range(
                confirmation_index + 1,
                segment_end,
            ):
                current = ordered[candle_index]
                previous = ordered[candle_index - 1]

                if direction == BreakDirection.BULLISH:
                    crossed = previous.close <= threshold and current.close > threshold
                else:
                    crossed = previous.close >= threshold and current.close < threshold

                if not crossed:
                    continue

                key = (
                    segment_id,
                    swing.tier,
                    swing.swing_type,
                    current.open_time,
                )

                if key in event_keys:
                    break

                event = self._classify_break(
                    swing=swing,
                    direction=direction,
                    candle=current,
                    candle_index=candle_index,
                    segment_id=segment_id,
                    prior_swings=validated_swings,
                    displacement=displacement_map.get(current.open_time),
                    liquidity_sweeps=validated_sweeps,
                )

                events.append(event)
                event_keys.add(key)
                break

        return sorted(
            events,
            key=lambda event: (
                event.break_open_time,
                event.timeframe.value,
                event.broken_swing_tier.value,
                event.broken_swing_type.value,
            ),
        )

    @staticmethod
    def _prepare_candles(
        candles: Sequence[Candle],
    ) -> list[Candle]:
        """Validate one stream and exclude forming candles."""

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
        """Split the candle stream at missing expected intervals."""

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
    def _build_candle_metadata(
        candles: Sequence[Candle],
        segments: list[tuple[int, int, int]],
    ) -> dict:
        """Keep candle-open and candle-close timestamps separate."""

        metadata = {
            "opens": {},
            "closes": {},
        }

        for segment_id, start, end in segments:
            for index in range(start, end):
                candle = candles[index]

                metadata["opens"][candle.open_time] = {
                    "index": index,
                    "segment_id": segment_id,
                }

                metadata["closes"][candle.close_time] = {
                    "close_index": index,
                    "segment_id": segment_id,
                }

        return metadata

    @staticmethod
    def _validate_metadata(
        symbol: str,
        asset_class,
        timeframe,
        provider: str,
        first: Candle,
    ) -> None:
        if (
            symbol.strip().upper() != first.symbol.strip().upper()
            or asset_class != first.asset_class
            or timeframe != first.timeframe
            or provider.strip().lower() != first.provider.strip().lower()
        ):
            raise ValueError("All supplied evidence must match the candle stream.")

    def _validate_swings(
        self,
        swings: Sequence[SwingPoint],
        candles: Sequence[Candle],
        metadata: dict,
    ) -> list[tuple[SwingPoint, int, int, int]]:
        """Validate swing identity, timing, price and segment."""

        first = candles[0]
        results = []
        identities = set()

        for swing in swings:
            self._validate_metadata(
                swing.symbol,
                swing.asset_class,
                swing.timeframe,
                swing.provider,
                first,
            )

            pivot = metadata["opens"].get(swing.pivot_time)
            confirmation = metadata["closes"].get(swing.confirmed_at)

            if pivot is None:
                raise ValueError("Swing pivot must correspond to a completed candle.")

            if confirmation is None:
                raise ValueError(
                    "Swing confirmation must correspond to a completed candle close."
                )

            pivot_index = pivot["index"]
            confirmation_index = confirmation["close_index"]
            segment_id = pivot["segment_id"]

            if confirmation_index <= pivot_index:
                raise ValueError("Swing confirmation must follow its pivot candle.")

            if confirmation["segment_id"] != segment_id:
                raise ValueError("Swing cannot be confirmed across a data gap.")

            if swing.segment_id != segment_id:
                raise ValueError("Swing segment does not match the candle dataset.")

            identity = (
                segment_id,
                swing.tier,
                swing.swing_type,
                swing.pivot_time,
            )

            if identity in identities:
                raise ValueError("Duplicate swing points found.")

            identities.add(identity)

            pivot_candle = candles[pivot_index]

            expected_price = (
                pivot_candle.high
                if swing.swing_type == SwingType.HIGH
                else pivot_candle.low
            )

            if swing.price != expected_price:
                raise ValueError("Swing price does not match its pivot candle.")

            results.append(
                (
                    swing,
                    pivot_index,
                    confirmation_index,
                    segment_id,
                )
            )

        return results

    def _validate_displacements(
        self,
        displacements: Sequence[DisplacementEvent],
        candles: Sequence[Candle],
        metadata: dict,
    ) -> dict:
        """Validate displacement evidence against its source candle."""

        first = candles[0]
        results = {}

        for event in displacements:
            self._validate_metadata(
                event.symbol,
                event.asset_class,
                event.timeframe,
                event.provider,
                first,
            )

            candle_info = metadata["opens"].get(event.open_time)

            if candle_info is None:
                raise ValueError("Displacement must match a completed candle.")

            candle_index = candle_info["index"]
            candle = candles[candle_index]

            if (
                event.candle_index != candle_index
                or event.confirmed_at != candle.close_time
                or event.open_price != candle.open
                or event.high_price != candle.high
                or event.low_price != candle.low
                or event.close_price != candle.close
                or event.segment_id != candle_info["segment_id"]
            ):
                raise ValueError("Displacement evidence does not match its candle.")

            if event.open_time in results:
                raise ValueError("Duplicate displacement events found.")

            results[event.open_time] = event

        return results

    def _validate_sweeps(
        self,
        sweeps: Sequence[LiquiditySweepEvidence],
        candles: Sequence[Candle],
        metadata: dict,
    ) -> list[tuple[LiquiditySweepEvidence, int, int]]:
        """Validate sweeps, including their return inside the pool."""

        first = candles[0]
        results = []

        for sweep in sweeps:
            self._validate_metadata(
                sweep.symbol,
                sweep.asset_class,
                sweep.timeframe,
                sweep.provider,
                first,
            )

            sweep_info = metadata["opens"].get(sweep.sweep_time)
            confirmation = metadata["closes"].get(sweep.confirmed_at)

            if sweep_info is None:
                raise ValueError("Sweep must refer to a completed candle.")

            if confirmation is None:
                raise ValueError("Sweep confirmation must match a candle close.")

            sweep_index = sweep_info["index"]
            segment_id = sweep_info["segment_id"]
            sweep_candle = candles[sweep_index]

            if (
                sweep.segment_id != segment_id
                or confirmation["segment_id"] != segment_id
                or confirmation["close_index"] != sweep_index
            ):
                raise ValueError("Sweep evidence does not match its candle.")

            if sweep.liquidity_side == LiquiditySide.BUY_SIDE:
                if (
                    sweep.swept_price > sweep_candle.high
                    or sweep_candle.close > sweep.pool_price
                ):
                    raise ValueError(
                        "Buy-side sweep must trade above the pool "
                        "and close back inside."
                    )
            else:
                if (
                    sweep.swept_price < sweep_candle.low
                    or sweep_candle.close < sweep.pool_price
                ):
                    raise ValueError(
                        "Sell-side sweep must trade below the pool "
                        "and close back inside."
                    )

            results.append((sweep, sweep_index, segment_id))

        return results

    def _classify_break(
        self,
        *,
        swing: SwingPoint,
        direction: BreakDirection,
        candle: Candle,
        candle_index: int,
        segment_id: int,
        prior_swings: Sequence[tuple],
        displacement: DisplacementEvent | None,
        liquidity_sweeps: Sequence[tuple],
    ) -> StructureBreakEvent:
        """Classify a break using evidence available at that time."""

        available_swings = [
            item[0]
            for item in prior_swings
            if (item[3] == segment_id and item[0].confirmed_at <= candle.open_time)
        ]

        prior_trend, protected_level, scope = self._get_prior_structure(
            swing.tier,
            available_swings,
        )

        matching_displacement = displacement is not None and (
            (
                direction == BreakDirection.BULLISH
                and displacement.direction == DisplacementDirection.BULLISH
            )
            or (
                direction == BreakDirection.BEARISH
                and displacement.direction == DisplacementDirection.BEARISH
            )
        )

        matching_sweep = self._find_preceding_sweep(
            direction=direction,
            segment_id=segment_id,
            break_index=candle_index,
            break_time=candle.open_time,
            sweeps=liquidity_sweeps,
        )

        event_type = self._classify_event_type(
            swing=swing,
            direction=direction,
            prior_trend=prior_trend,
            protected_level=protected_level,
            displacement_confirmed=matching_displacement,
            matching_sweep=matching_sweep,
        )

        recorded_sweep = (
            matching_sweep if event_type == StructureEventType.MSS else None
        )

        return StructureBreakEvent(
            symbol=candle.symbol,
            asset_class=candle.asset_class,
            timeframe=candle.timeframe,
            provider=candle.provider,
            event_type=event_type,
            direction=direction,
            scope=scope,
            profile=self.config.profile,
            broken_swing_type=swing.swing_type,
            broken_swing_tier=swing.tier,
            broken_level=swing.price,
            pivot_time=swing.pivot_time,
            pivot_confirmed_at=swing.confirmed_at,
            break_open_time=candle.open_time,
            break_close_time=candle.close_time,
            confirmed_at=candle.close_time,
            break_close=candle.close,
            break_buffer=self.config.break_buffer,
            prior_trend=prior_trend,
            displacement_confirmed=matching_displacement,
            liquidity_sweep_preceded=recorded_sweep is not None,
            liquidity_side=(
                recorded_sweep[0].liquidity_side if recorded_sweep is not None else None
            ),
            liquidity_sweep_time=(
                recorded_sweep[0].sweep_time if recorded_sweep is not None else None
            ),
        )

    def _get_prior_structure(
        self,
        tier: SwingTier,
        swings: Sequence[SwingPoint],
    ) -> tuple[MarketTrend, object | None, StructureScope]:
        """Reconstruct structure from previously confirmed swings."""

        scope_by_tier = {
            SwingTier.SHORT_TERM: StructureScope.INTERNAL,
            SwingTier.INTERMEDIATE_TERM: StructureScope.INTERMEDIATE,
            SwingTier.LONG_TERM: StructureScope.EXTERNAL,
        }

        scope = scope_by_tier[tier]

        if not swings:
            return MarketTrend.UNKNOWN, None, scope

        result = self.structure_service.analyze(swings)

        state_by_tier = {
            SwingTier.SHORT_TERM: result.internal,
            SwingTier.INTERMEDIATE_TERM: result.intermediate,
            SwingTier.LONG_TERM: result.external,
        }

        state = state_by_tier[tier]

        if state.trend == MarketTrend.BEARISH:
            protected_level = state.protected_high_candidate
        elif state.trend == MarketTrend.BULLISH:
            protected_level = state.protected_low_candidate
        else:
            protected_level = None

        return state.trend, protected_level, scope

    def _classify_event_type(
        self,
        *,
        swing: SwingPoint,
        direction: BreakDirection,
        prior_trend: MarketTrend,
        protected_level,
        displacement_confirmed: bool,
        matching_sweep: tuple | None,
    ) -> StructureEventType:
        """Apply the selected standard or strict event profile."""

        if prior_trend == MarketTrend.UNKNOWN:
            return StructureEventType.UNCLASSIFIED_BREAK

        if prior_trend in (
            MarketTrend.RANGING,
            MarketTrend.TRANSITIONAL,
        ):
            return StructureEventType.UNCLASSIFIED_BREAK

        if (
            direction == BreakDirection.BULLISH and prior_trend == MarketTrend.BULLISH
        ) or (
            direction == BreakDirection.BEARISH and prior_trend == MarketTrend.BEARISH
        ):
            return StructureEventType.BOS

        if protected_level is None:
            return StructureEventType.CHOCH

        is_protected_break = (
            protected_level.pivot_time == swing.pivot_time
            and protected_level.price == swing.price
        )

        if not is_protected_break or not displacement_confirmed:
            return StructureEventType.CHOCH

        if (
            self.config.profile == StructureBreakProfile.STRICT_ICT_2022
            and matching_sweep is None
        ):
            return StructureEventType.CHOCH

        return StructureEventType.MSS

    def _find_preceding_sweep(
        self,
        *,
        direction: BreakDirection,
        segment_id: int,
        break_index: int,
        break_time,
        sweeps: Sequence[tuple],
    ) -> tuple | None:
        """Find a recent opposing-side sweep confirmed before the break."""

        required_side = (
            LiquiditySide.SELL_SIDE
            if direction == BreakDirection.BULLISH
            else LiquiditySide.BUY_SIDE
        )

        candidates = []

        for sweep, sweep_index, sweep_segment in sweeps:
            if sweep_segment != segment_id:
                continue

            if sweep.liquidity_side != required_side:
                continue

            if sweep.confirmed_at > break_time:
                continue

            age = break_index - sweep_index

            if age < 1 or age > self.config.max_sweep_age_bars:
                continue

            candidates.append((sweep, sweep_index, sweep_segment))

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda item: item[1],
        )


__all__ = ["StructureBreakService"]
