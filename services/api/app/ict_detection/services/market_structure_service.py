from collections.abc import Sequence

from app.ict_detection.market_structure_schemas import (
    ClassifiedSwing,
    MarketStructureConfig,
    MarketStructureResult,
    MarketTrend,
    StructureLevel,
    StructureScope,
    StructureState,
    SwingClassification,
)
from app.ict_detection.schemas import SwingPoint, SwingTier, SwingType


class MarketStructureService:
    """
    Classify confirmed swings and calculate structure independently
    for short-, intermediate- and long-term swing hierarchies.
    """

    def __init__(
        self,
        config: MarketStructureConfig | None = None,
    ) -> None:
        self.config = config or MarketStructureConfig()

    def analyze(
        self,
        swings: Sequence[SwingPoint],
    ) -> MarketStructureResult:
        """Classify swings and produce three structural states."""

        if not swings:
            raise ValueError("At least one confirmed swing is required.")

        self._validate_swings(swings)

        first = swings[0]
        classified = self._classify_swings(swings)

        return MarketStructureResult(
            symbol=first.symbol,
            asset_class=first.asset_class,
            timeframe=first.timeframe,
            provider=first.provider,
            classified_swings=classified,
            internal=self._build_state(
                classified,
                SwingTier.SHORT_TERM,
            ),
            intermediate=self._build_state(
                classified,
                SwingTier.INTERMEDIATE_TERM,
            ),
            external=self._build_state(
                classified,
                SwingTier.LONG_TERM,
            ),
        )

    @staticmethod
    def _validate_swings(
        swings: Sequence[SwingPoint],
    ) -> None:
        """Reject mixed streams and duplicate swing identities."""

        first = swings[0]

        expected_metadata = (
            first.symbol.strip().upper(),
            first.asset_class,
            first.timeframe,
            first.provider.strip().lower(),
        )

        identities = set()

        for swing in swings:
            actual_metadata = (
                swing.symbol.strip().upper(),
                swing.asset_class,
                swing.timeframe,
                swing.provider.strip().lower(),
            )

            if actual_metadata != expected_metadata:
                raise ValueError(
                    "All swings must belong to the same symbol, "
                    "asset class, timeframe and provider."
                )

            identity = (
                swing.segment_id,
                swing.tier,
                swing.swing_type,
                swing.pivot_time,
            )

            if identity in identities:
                raise ValueError("Duplicate swing points found.")

            identities.add(identity)

    @staticmethod
    def _scope_for_tier(tier: SwingTier) -> StructureScope:
        return {
            SwingTier.SHORT_TERM: StructureScope.INTERNAL,
            SwingTier.INTERMEDIATE_TERM: StructureScope.INTERMEDIATE,
            SwingTier.LONG_TERM: StructureScope.EXTERNAL,
        }[tier]

    def _classify_swings(
        self,
        swings: Sequence[SwingPoint],
    ) -> list[ClassifiedSwing]:
        """Compare highs with highs and lows with lows."""

        groups: dict[
            tuple[int, SwingTier, SwingType],
            list[SwingPoint],
        ] = {}

        for swing in swings:
            key = (
                swing.segment_id,
                swing.tier,
                swing.swing_type,
            )
            groups.setdefault(key, []).append(swing)

        results: list[ClassifiedSwing] = []
        tolerance = self.config.price_tolerance

        for (_, tier, swing_type), group in groups.items():
            ordered = sorted(
                group,
                key=lambda swing: swing.pivot_index,
            )

            previous_price = None

            for swing in ordered:
                difference = (
                    None if previous_price is None else swing.price - previous_price
                )

                if difference is None:
                    classification = SwingClassification.INITIAL

                elif abs(difference) <= tolerance:
                    classification = (
                        SwingClassification.EQH
                        if swing_type == SwingType.HIGH
                        else SwingClassification.EQL
                    )

                elif swing_type == SwingType.HIGH:
                    classification = (
                        SwingClassification.HH
                        if difference > 0
                        else SwingClassification.LH
                    )

                else:
                    classification = (
                        SwingClassification.HL
                        if difference > 0
                        else SwingClassification.LL
                    )

                results.append(
                    ClassifiedSwing(
                        swing=swing,
                        scope=self._scope_for_tier(tier),
                        classification=classification,
                        previous_comparable_price=previous_price,
                        price_difference=difference,
                    )
                )

                previous_price = swing.price

        tier_order = {
            SwingTier.SHORT_TERM: 0,
            SwingTier.INTERMEDIATE_TERM: 1,
            SwingTier.LONG_TERM: 2,
        }

        return sorted(
            results,
            key=lambda item: (
                item.swing.pivot_time,
                tier_order[item.swing.tier],
                item.swing.swing_type.value,
            ),
        )

    @staticmethod
    def _to_level(
        item: ClassifiedSwing | None,
    ) -> StructureLevel | None:
        if item is None:
            return None

        swing = item.swing

        return StructureLevel(
            price=swing.price,
            pivot_time=swing.pivot_time,
            pivot_index=swing.pivot_index,
            segment_id=swing.segment_id,
            swing_type=swing.swing_type,
            tier=swing.tier,
            classification=item.classification,
        )

    @classmethod
    def _build_state(
        cls,
        classified: Sequence[ClassifiedSwing],
        tier: SwingTier,
    ) -> StructureState:
        """Build the latest state without crossing data gaps."""

        scope = cls._scope_for_tier(tier)

        tier_items = [item for item in classified if item.swing.tier == tier]

        if not tier_items:
            return StructureState(scope=scope)

        latest_segment = max(item.swing.segment_id for item in tier_items)

        current = [
            item for item in tier_items if item.swing.segment_id == latest_segment
        ]

        current.sort(key=lambda item: item.swing.pivot_index)

        highs = [item for item in current if item.swing.swing_type == SwingType.HIGH]

        lows = [item for item in current if item.swing.swing_type == SwingType.LOW]

        latest_high = highs[-1] if highs else None
        latest_low = lows[-1] if lows else None

        trend = cls._classify_trend(
            latest_high,
            latest_low,
            len(highs),
            len(lows),
        )

        protected_high = None
        protected_low = None
        weak_high = None
        weak_low = None

        if trend == MarketTrend.BULLISH and latest_high is not None:
            candidates = [
                item
                for item in lows
                if (
                    item.classification == SwingClassification.HL
                    and item.swing.pivot_index < latest_high.swing.pivot_index
                )
            ]

            if candidates:
                protected_low = candidates[-1]
                weak_high = latest_high

        elif trend == MarketTrend.BEARISH and latest_low is not None:
            candidates = [
                item
                for item in highs
                if (
                    item.classification == SwingClassification.LH
                    and item.swing.pivot_index < latest_low.swing.pivot_index
                )
            ]

            if candidates:
                protected_high = candidates[-1]
                weak_low = latest_low

        return StructureState(
            scope=scope,
            segment_id=latest_segment,
            trend=trend,
            latest_high=cls._to_level(latest_high),
            latest_low=cls._to_level(latest_low),
            high_count=len(highs),
            low_count=len(lows),
            protected_high_candidate=cls._to_level(protected_high),
            protected_low_candidate=cls._to_level(protected_low),
            strong_high_candidate=cls._to_level(protected_high),
            strong_low_candidate=cls._to_level(protected_low),
            weak_high_candidate=cls._to_level(weak_high),
            weak_low_candidate=cls._to_level(weak_low),
        )

    @staticmethod
    def _classify_trend(
        latest_high: ClassifiedSwing | None,
        latest_low: ClassifiedSwing | None,
        high_count: int,
        low_count: int,
    ) -> MarketTrend:
        if high_count < 2 or low_count < 2 or latest_high is None or latest_low is None:
            return MarketTrend.UNKNOWN

        high_label = latest_high.classification
        low_label = latest_low.classification

        if high_label == SwingClassification.HH and low_label == SwingClassification.HL:
            return MarketTrend.BULLISH

        if high_label == SwingClassification.LH and low_label == SwingClassification.LL:
            return MarketTrend.BEARISH

        if (
            high_label == SwingClassification.EQH
            and low_label == SwingClassification.EQL
        ):
            return MarketTrend.RANGING

        return MarketTrend.TRANSITIONAL


__all__ = ["MarketStructureService"]
