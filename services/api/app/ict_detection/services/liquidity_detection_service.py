
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from statistics import mean

from app.ict_detection.liquidity_schemas import (
    LiquidityDetectionConfig,
    LiquidityPool,
    LiquidityPoolStatus,
    LiquidityPoolType,
)
from app.ict_detection.schemas import SwingPoint, SwingType
from app.ict_detection.structure_break_schemas import (
    LiquiditySide,
    LiquiditySweepEvidence,
)
from app.market_data.schemas.market_data import Candle


class LiquidityDetectionService:
    """Detect equal-high/equal-low liquidity pools and liquidity sweeps."""

    def __init__(
        self,
        config: LiquidityDetectionConfig | None = None,
    ) -> None:
        self.config = config or LiquidityDetectionConfig()

    def detect_pools(
        self,
        swings: Sequence[SwingPoint],
    ) -> list[LiquidityPool]:
        """Group confirmed swing points into candidate and confirmed pools."""

        self._validate_swings(swings)

        grouped: dict[tuple[int, SwingType], list[SwingPoint]] = {}

        for swing in swings:
            key = (swing.segment_id, swing.swing_type)
            grouped.setdefault(key, []).append(swing)

        pools: list[LiquidityPool] = []

        for (segment_id, swing_type), segment_swings in grouped.items():
            ordered = sorted(segment_swings, key=lambda item: item.price)
            clusters = self._cluster_swings(ordered)

            for cluster in clusters:
                pools.append(
                    self._build_pool(
                        cluster=cluster,
                        segment_id=segment_id,
                        swing_type=swing_type,
                    )
                )

        return sorted(
            pools,
            key=lambda pool: (pool.detected_at, pool.price),
        )

    def detect_sweeps(
        self,
        candles: Sequence[Candle],
        pools: Sequence[LiquidityPool],
    ) -> list[LiquiditySweepEvidence]:
        """Detect completed candles that sweep confirmed liquidity pools."""

        self._validate_candles(candles)

        completed_candles = sorted(
            (candle for candle in candles if candle.is_complete),
            key=lambda candle: candle.open_time,
        )

        events: list[LiquiditySweepEvidence] = []

        for pool in pools:
            if pool.status != LiquidityPoolStatus.CONFIRMED:
                continue

            if pool.confirmed_at is None:
                continue

            for candle in completed_candles:
                if candle.symbol != pool.symbol:
                    continue

                if candle.asset_class != pool.asset_class:
                    continue

                if candle.timeframe != pool.timeframe:
                    continue

                if candle.provider != pool.provider:
                    continue

                if candle.open_time <= pool.confirmed_at:
                    continue

                if self._is_sweep(candle, pool):
                    events.append(
                        LiquiditySweepEvidence(
                            symbol=pool.symbol,
                            asset_class=pool.asset_class,
                            timeframe=pool.timeframe,
                            provider=pool.provider,
                            liquidity_side=pool.liquidity_side,
                            segment_id=pool.segment_id,
                            pool_price=pool.price,
                            swept_price=(
                                candle.high
                                if pool.liquidity_side == LiquiditySide.BUY_SIDE
                                else candle.low
                            ),
                            sweep_time=candle.open_time,
                            confirmed_at=candle.close_time,
                        )
                    )

                    # One sweep event per pool in this detection pass.
                    break

        return sorted(events, key=lambda event: event.confirmed_at)

    def detect(
        self,
        candles: Sequence[Candle],
        swings: Sequence[SwingPoint],
    ) -> tuple[list[LiquidityPool], list[LiquiditySweepEvidence]]:
        """Run pool detection followed by sweep detection."""

        pools = self.detect_pools(swings)
        sweeps = self.detect_sweeps(candles, pools)

        return pools, sweeps

    def _cluster_swings(
        self,
        swings: Sequence[SwingPoint],
    ) -> list[list[SwingPoint]]:
        """Create price clusters using the configured absolute tolerance."""

        clusters: list[list[SwingPoint]] = []

        for swing in swings:
            matching_cluster = None

            for cluster in clusters:
                cluster_prices = [item.price for item in cluster]

                if (
                    max(max(cluster_prices), swing.price)
                    - min(min(cluster_prices), swing.price)
                    <= self.config.price_tolerance
                ):
                    matching_cluster = cluster
                    break

            if matching_cluster is None:
                clusters.append([swing])
            else:
                matching_cluster.append(swing)

        return clusters

    def _build_pool(
        self,
        cluster: Sequence[SwingPoint],
        segment_id: int,
        swing_type: SwingType,
    ) -> LiquidityPool:
        """Build a candidate or confirmed pool from a swing cluster."""

        prices = [swing.price for swing in cluster]
        lower_bound = min(prices)
        upper_bound = max(prices)

        pool_price = Decimal(
            str(mean(float(price) for price in prices))
        )

        if swing_type == SwingType.HIGH:
            pool_type = LiquidityPoolType.EQUAL_HIGHS
            liquidity_side = LiquiditySide.BUY_SIDE
        else:
            pool_type = LiquidityPoolType.EQUAL_LOWS
            liquidity_side = LiquiditySide.SELL_SIDE

        is_confirmed = len(cluster) >= self.config.minimum_touches

        confirmation_time = (
            max(swing.confirmed_at for swing in cluster)
            if is_confirmed
            else None
        )

        detected_at = max(
            swing.confirmed_at for swing in cluster
        )

        return LiquidityPool(
            symbol=cluster[0].symbol,
            asset_class=cluster[0].asset_class,
            timeframe=cluster[0].timeframe,
            provider=cluster[0].provider,
            pool_type=pool_type,
            liquidity_side=liquidity_side,
            swing_type=swing_type,
            price=pool_price,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            swing_points=tuple(cluster),
            segment_id=segment_id,
            detected_at=detected_at,
            confirmed_at=confirmation_time,
            status=(
                LiquidityPoolStatus.CONFIRMED
                if is_confirmed
                else LiquidityPoolStatus.CANDIDATE
            ),
        )

    @staticmethod
    def _is_sweep(
        candle: Candle,
        pool: LiquidityPool,
    ) -> bool:
        """Check whether price crosses a pool and closes back inside."""

        if pool.liquidity_side == LiquiditySide.BUY_SIDE:
            return (
                candle.high > pool.price
                and candle.close < pool.price
            )

        return (
            candle.low < pool.price
            and candle.close > pool.price
        )

    @staticmethod
    def _validate_swings(
        swings: Sequence[SwingPoint],
    ) -> None:
        if not swings:
            return

        first = swings[0]

        for swing in swings:
            if (
                swing.symbol != first.symbol
                or swing.asset_class != first.asset_class
                or swing.timeframe != first.timeframe
                or swing.provider != first.provider
            ):
                raise ValueError(
                    "All swing points must belong to the same market stream."
                )

    @staticmethod
    def _validate_candles(
        candles: Sequence[Candle],
    ) -> None:
        if not candles:
            return

        first = candles[0]
        timestamps = set()

        for candle in candles:
            if (
                candle.symbol != first.symbol
                or candle.asset_class != first.asset_class
                or candle.timeframe != first.timeframe
                or candle.provider != first.provider
            ):
                raise ValueError(
                    "All candles must belong to the same market stream."
                )

            if candle.open_time in timestamps:
                raise ValueError(
                    "Duplicate candle timestamps are not allowed."
                )

            timestamps.add(candle.open_time)
