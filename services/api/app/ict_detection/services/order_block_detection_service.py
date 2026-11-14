
from collections.abc import Sequence

from app.ict_detection.displacement_schemas import (
    DisplacementDirection,
    DisplacementEvent,
)
from app.ict_detection.order_block_schemas import (
    OrderBlock,
    OrderBlockDetectionConfig,
    OrderBlockDirection,
    OrderBlockStatus,
)
from app.ict_detection.structure_break_schemas import (
    BreakDirection,
    StructureBreakEvent,
    StructureEventType,
)
from app.market_data.schemas.market_data import Candle
from app.market_data.services.timeframes import next_candle_open


class OrderBlockDetectionService:
    """Detect confirmed order blocks using displacement and structure evidence."""

    def __init__(
        self,
        config: OrderBlockDetectionConfig | None = None,
    ) -> None:
        self.config = config or OrderBlockDetectionConfig()

    def detect(
        self,
        candles: Sequence[Candle],
        displacements: Sequence[DisplacementEvent],
        structure_breaks: Sequence[StructureBreakEvent],
    ) -> list[OrderBlock]:
        """Detect order blocks and evaluate their subsequent lifecycle."""

        ordered = self._prepare_candles(candles)

        if not ordered:
            return []

        segments = self._build_segments(ordered)
        metadata = self._build_metadata(ordered, segments)

        displacement_map = self._validate_displacements(
            displacements,
            ordered,
            metadata,
        )

        validated_breaks = self._validate_structure_breaks(
            structure_breaks,
            ordered,
            metadata,
        )

        order_blocks = []
        detected_keys = set()

        for event, break_index, segment_id in validated_breaks:
            if not event.displacement_confirmed:
                continue

            displacement = displacement_map.get(event.break_open_time)

            if displacement is None:
                continue

            direction = self._matching_direction(
                event.direction,
                displacement.direction,
            )

            if direction is None:
                continue

            if event.event_type not in (
                StructureEventType.BOS,
                StructureEventType.CHOCH,
                StructureEventType.MSS,
            ):
                continue

            segment_start, segment_end = self._get_segment_bounds(
                segment_id,
                segments,
            )

            origin_index = self._find_origin_candle(
                candles=ordered,
                displacement_index=break_index,
                pivot_confirmed_at=event.pivot_confirmed_at,
                segment_start=segment_start,
                direction=direction,
            )

            if origin_index is None:
                continue

            origin = ordered[origin_index]

            key = (
                segment_id,
                direction,
                origin.open_time,
                displacement.open_time,
            )

            if key in detected_keys:
                continue

            order_block = self._build_order_block(
                candles=ordered,
                origin_index=origin_index,
                displacement=displacement,
                event=event,
                direction=direction,
                segment_id=segment_id,
                segment_end=segment_end,
            )

            order_blocks.append(order_block)
            detected_keys.add(key)

        return sorted(
            order_blocks,
            key=lambda item: (
                item.origin_open_time,
                item.confirmed_at,
                item.direction.value,
            ),
        )

    @staticmethod
    def _prepare_candles(
        candles: Sequence[Candle],
    ) -> list[Candle]:
        """Validate one candle stream and exclude forming candles."""

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

        segments = []
        segment_start = 0
        segment_id = 0
        timeframe = candles[0].timeframe

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
    def _build_metadata(
        candles: Sequence[Candle],
        segments: list[tuple[int, int, int]],
    ) -> dict:
        """Index candle opening and closing timestamps."""

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
                    "index": index,
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
            raise ValueError(
                "All supplied evidence must match the candle stream."
            )

    def _validate_displacements(
        self,
        displacements: Sequence[DisplacementEvent],
        candles: Sequence[Candle],
        metadata: dict,
    ) -> dict:
        """Validate displacement evidence against its source candle."""

        results = {}
        first = candles[0]

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
                raise ValueError(
                    "Displacement must match a completed candle."
                )

            index = candle_info["index"]
            candle = candles[index]

            if (
                event.candle_index != index
                or event.confirmed_at != candle.close_time
                or event.open_price != candle.open
                or event.high_price != candle.high
                or event.low_price != candle.low
                or event.close_price != candle.close
                or event.segment_id != candle_info["segment_id"]
            ):
                raise ValueError(
                    "Displacement evidence does not match its candle."
                )

            if event.open_time in results:
                raise ValueError("Duplicate displacement events found.")

            results[event.open_time] = event

        return results

    def _validate_structure_breaks(
        self,
        structure_breaks: Sequence[StructureBreakEvent],
        candles: Sequence[Candle],
        metadata: dict,
    ) -> list[tuple[StructureBreakEvent, int, int]]:
        """Validate structural break evidence against its source candle."""

        results = []
        first = candles[0]

        for event in structure_breaks:
            self._validate_metadata(
                event.symbol,
                event.asset_class,
                event.timeframe,
                event.provider,
                first,
            )

            break_info = metadata["opens"].get(event.break_open_time)
            break_close_info = metadata["closes"].get(event.break_close_time)
            pivot_info = metadata["opens"].get(event.pivot_time)
            pivot_confirmation = metadata["closes"].get(
                event.pivot_confirmed_at
            )

            if (
                break_info is None
                or break_close_info is None
                or pivot_info is None
                or pivot_confirmation is None
            ):
                raise ValueError(
                    "Structure break timestamps must match completed candles."
                )

            break_index = break_info["index"]
            segment_id = break_info["segment_id"]
            break_candle = candles[break_index]

            if (
                break_close_info["index"] != break_index
                or break_close_info["segment_id"] != segment_id
                or pivot_info["segment_id"] != segment_id
                or pivot_confirmation["segment_id"] != segment_id
            ):
                raise ValueError(
                    "Structure break evidence cannot cross data gaps."
                )

            if (
                event.confirmed_at != break_candle.close_time
                or event.break_close != break_candle.close
                or event.pivot_confirmed_at > event.break_open_time
            ):
                raise ValueError(
                    "Structure break evidence does not match its candle."
                )

            results.append((event, break_index, segment_id))

        return results

    @staticmethod
    def _matching_direction(
        break_direction: BreakDirection,
        displacement_direction: DisplacementDirection,
    ) -> OrderBlockDirection | None:
        if (
            break_direction == BreakDirection.BULLISH
            and displacement_direction == DisplacementDirection.BULLISH
        ):
            return OrderBlockDirection.BULLISH

        if (
            break_direction == BreakDirection.BEARISH
            and displacement_direction == DisplacementDirection.BEARISH
        ):
            return OrderBlockDirection.BEARISH

        return None

    def _find_origin_candle(
        self,
        *,
        candles: Sequence[Candle],
        displacement_index: int,
        pivot_confirmed_at,
        segment_start: int,
        direction: OrderBlockDirection,
    ) -> int | None:
        """Find the last opposing candle before qualifying displacement."""

        confirmation_index = next(
            (
                index
                for index, candle in enumerate(candles)
                if candle.close_time == pivot_confirmed_at
            ),
            None,
        )

        if confirmation_index is None:
            return None

        lookback_start = max(
            segment_start,
            displacement_index - self.config.max_origin_lookback_bars,
            confirmation_index + 1,
        )

        for index in range(displacement_index - 1, lookback_start - 1, -1):
            candle = candles[index]

            if (
                direction == OrderBlockDirection.BULLISH
                and candle.close < candle.open
            ):
                return index

            if (
                direction == OrderBlockDirection.BEARISH
                and candle.close > candle.open
            ):
                return index

        return None

    @staticmethod
    def _get_segment_bounds(
        segment_id: int,
        segments: list[tuple[int, int, int]],
    ) -> tuple[int, int]:
        for current_id, start, end in segments:
            if current_id == segment_id:
                return start, end

        raise ValueError("Unknown candle segment.")

    def _build_order_block(
        self,
        *,
        candles: Sequence[Candle],
        origin_index: int,
        displacement: DisplacementEvent,
        event: StructureBreakEvent,
        direction: OrderBlockDirection,
        segment_id: int,
        segment_end: int,
    ) -> OrderBlock:
        """Build an order block and evaluate its subsequent lifecycle."""

        origin = candles[origin_index]

        lower_bound = origin.low
        upper_bound = origin.high

        mitigated_at = None
        invalidated_at = None

        for candle in candles[displacement.candle_index + 1 : segment_end]:
            overlaps_zone = (
                candle.low <= upper_bound
                and candle.high >= lower_bound
            )

            if overlaps_zone and mitigated_at is None:
                mitigated_at = candle.close_time

            if direction == OrderBlockDirection.BULLISH:
                invalidated = (
                    candle.close
                    < lower_bound - self.config.invalidation_buffer
                )
            else:
                invalidated = (
                    candle.close
                    > upper_bound + self.config.invalidation_buffer
                )

            if invalidated:
                invalidated_at = candle.close_time
                break

        if invalidated_at is not None:
            status = OrderBlockStatus.INVALIDATED
        elif mitigated_at is not None:
            status = OrderBlockStatus.MITIGATED
        else:
            status = OrderBlockStatus.ACTIVE

        return OrderBlock(
            symbol=origin.symbol,
            asset_class=origin.asset_class.value,
            timeframe=origin.timeframe.value,
            provider=origin.provider,
            direction=direction,
            origin_candle_index=origin_index,
            segment_id=segment_id,
            origin_open_time=origin.open_time,
            origin_close_time=origin.close_time,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            displacement_candle_index=displacement.candle_index,
            displacement_open_time=displacement.open_time,
            displacement_confirmed_at=displacement.confirmed_at,
            structure_break_type=event.event_type,
            broken_level=event.broken_level,
            structure_break_open_time=event.break_open_time,
            structure_break_confirmed_at=event.confirmed_at,
            confirmed_at=event.confirmed_at,
            status=status,
            mitigated_at=mitigated_at,
            invalidated_at=invalidated_at,
        )


__all__ = ["OrderBlockDetectionService"]
