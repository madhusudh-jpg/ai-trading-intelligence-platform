from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ict_detection.analysis_schemas import ICTAnalysisResult
from app.ict_detection.imbalance_schemas import (
    ImbalanceStatus,
    InverseFVGStatus,
)
from app.ict_detection.market_structure_schemas import MarketTrend
from app.ict_detection.order_block_schemas import OrderBlockStatus
from app.ict_detection.structure_break_schemas import LiquiditySide


class ConfluenceDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ConfluenceStatus(StrEnum):
    BULLISH_ALIGNMENT = "bullish_alignment"
    BEARISH_ALIGNMENT = "bearish_alignment"
    NEUTRAL = "neutral"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ConfluenceEvidenceType(StrEnum):
    MARKET_STRUCTURE = "market_structure"
    DISPLACEMENT = "displacement"
    STRUCTURE_BREAK = "structure_break"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    FAIR_VALUE_GAP = "fair_value_gap"
    INVERSE_FVG = "inverse_fvg"
    BALANCED_PRICE_RANGE = "balanced_price_range"
    ORDER_BLOCK = "order_block"


class EvidenceLifecycleStatus(StrEnum):
    ACTIVE = "active"
    MITIGATED = "mitigated"
    INVALIDATED = "invalidated"
    SWEPT = "swept"
    EXPIRED = "expired"
    NOT_APPLICABLE = "not_applicable"


class ConfluenceEvidence(BaseModel):
    """One evidence item contributing to timeframe confluence."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    evidence_type: ConfluenceEvidenceType
    direction: ConfluenceDirection | None = None

    symbol: str
    asset_class: str
    timeframe: str
    provider: str

    detected_at: datetime
    confirmed_at: datetime

    metadata: dict[str, Any] = Field(default_factory=dict)

    lifecycle_status: EvidenceLifecycleStatus = (
        EvidenceLifecycleStatus.NOT_APPLICABLE
    )

    related_evidence_ids: tuple[str, ...] = ()

    invalidated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> ConfluenceEvidence:
        timestamps = [self.detected_at, self.confirmed_at]

        if self.invalidated_at is not None:
            timestamps.append(self.invalidated_at)

        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None
            for timestamp in timestamps
        ):
            raise ValueError("Evidence timestamps must be timezone-aware.")

        if self.confirmed_at < self.detected_at:
            raise ValueError("Evidence cannot be confirmed before detection.")

        if (
            self.invalidated_at is not None
            and self.invalidated_at < self.confirmed_at
        ):
            raise ValueError("Invalidation cannot precede confirmation.")

        if not self.evidence_id.strip():
            raise ValueError("evidence_id cannot be empty.")

        if self.evidence_id in self.related_evidence_ids:
            raise ValueError("Evidence cannot reference itself.")

        if len(set(self.related_evidence_ids)) != len(
            self.related_evidence_ids
        ):
            raise ValueError("Related evidence IDs must be unique.")

        return self


class ICTConfluenceResult(BaseModel):
    """Evidence-backed confluence interpretation for one timeframe."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: str
    timeframe: str
    provider: str

    analyzed_at: datetime

    status: ConfluenceStatus

    evidence: tuple[ConfluenceEvidence, ...] = ()

    bullish_evidence_count: int = 0
    bearish_evidence_count: int = 0

    @model_validator(mode="after")
    def validate_confluence(self) -> ICTConfluenceResult:
        if self.analyzed_at.tzinfo is None or self.analyzed_at.utcoffset() is None:
            raise ValueError("analyzed_at must be timezone-aware.")

        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty.")

        if not self.asset_class.strip():
            raise ValueError("asset_class cannot be empty.")

        if not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty.")

        if not self.provider.strip():
            raise ValueError("provider cannot be empty.")

        if self.bullish_evidence_count < 0 or self.bearish_evidence_count < 0:
            raise ValueError("Evidence counts cannot be negative.")

        ids = [item.evidence_id for item in self.evidence]

        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique.")

        if any(
            item.symbol != self.symbol
            or item.asset_class != self.asset_class
            or item.timeframe != self.timeframe
            or item.provider != self.provider
            for item in self.evidence
        ):
            raise ValueError("All evidence must belong to the same market stream.")

        return self




class ConfluenceService:
    """
    Builds deterministic, evidence-based ICT confluence for one timeframe.

    Directional alignment requires at least two independent evidence groups.
    Related observations are linked and counted as one group.
    """

    def analyze(self, analysis: ICTAnalysisResult) -> ICTConfluenceResult:
        self._validate_stream(analysis)

        evidence: list[ConfluenceEvidence] = []
        group_by_id: dict[str, str] = {}

        self._add_market_structure(analysis, evidence, group_by_id)
        self._add_displacements(analysis, evidence, group_by_id)
        self._add_structure_breaks(analysis, evidence, group_by_id)
        self._add_liquidity_sweeps(analysis, evidence, group_by_id)
        self._add_fair_value_gaps(analysis, evidence, group_by_id)
        self._add_inverse_fvgs(analysis, evidence, group_by_id)
        self._add_balanced_price_ranges(analysis, evidence, group_by_id)
        self._add_order_blocks(analysis, evidence, group_by_id)

        evidence = self._connect_related_evidence(evidence)

        bullish_groups: set[str] = set()
        bearish_groups: set[str] = set()

        for item in evidence:
            if item.lifecycle_status in {
                EvidenceLifecycleStatus.INVALIDATED,
                EvidenceLifecycleStatus.EXPIRED,
            }:
                continue

            group = group_by_id.get(item.evidence_id, item.evidence_id)

            if item.direction == ConfluenceDirection.BULLISH:
                bullish_groups.add(group)
            elif item.direction == ConfluenceDirection.BEARISH:
                bearish_groups.add(group)

        bullish_count = len(bullish_groups)
        bearish_count = len(bearish_groups)

        status = self._determine_status(
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            evidence_count=len(evidence),
        )

        return ICTConfluenceResult(
            symbol=analysis.symbol,
            asset_class=analysis.asset_class,
            timeframe=analysis.timeframe,
            provider=analysis.provider,
            analyzed_at=analysis.analyzed_at,
            status=status,
            evidence=tuple(evidence),
            bullish_evidence_count=bullish_count,
            bearish_evidence_count=bearish_count,
        )

    # ------------------------------------------------------------------
    # Evidence creation
    # ------------------------------------------------------------------

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    @staticmethod
    def _add(
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
        *,
        analysis: ICTAnalysisResult,
        evidence_type: ConfluenceEvidenceType,
        direction: ConfluenceDirection | None,
        detected_at: datetime,
        confirmed_at: datetime,
        lifecycle_status: EvidenceLifecycleStatus,
        metadata: dict[str, Any],
        group_key: str,
        related_evidence_ids: tuple[str, ...] = (),
        invalidated_at: datetime | None = None,
    ) -> str:
        evidence_id = ConfluenceService._new_id(
            evidence_type.value.lower()
        )

        item = ConfluenceEvidence(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            direction=direction,
            symbol=analysis.symbol,
            asset_class=str(analysis.asset_class),
            timeframe=str(analysis.timeframe),
            provider=analysis.provider,
            metadata=metadata,
            detected_at=detected_at,
            confirmed_at=confirmed_at,
            lifecycle_status=lifecycle_status,
            related_evidence_ids=related_evidence_ids,
            invalidated_at=invalidated_at,
        )

        evidence.append(item)
        group_by_id[evidence_id] = group_key

        return evidence_id

    # ------------------------------------------------------------------
    # Market structure
    # ------------------------------------------------------------------

    def _add_market_structure(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        result = analysis.market_structure

        states = (
            result.internal,
            result.intermediate,
            result.external,
        )

        # All market-structure scopes belong to one evidence family.
        group_key = f"market_structure:{analysis.timeframe}"

        for state in states:
            if state is None:
                continue

            if state.trend == MarketTrend.BULLISH:
                direction = ConfluenceDirection.BULLISH
            elif state.trend == MarketTrend.BEARISH:
                direction = ConfluenceDirection.BEARISH
            else:
                direction = None

            if direction is None:
                continue

            matching = [
                classified
                for classified in result.classified_swings
                if classified.scope == state.scope
            ]

            if not matching:
                continue

            latest = max(
                matching,
                key=lambda item: item.swing.confirmed_at,
            )

            swing = latest.swing

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.MARKET_STRUCTURE,
                direction=direction,
                detected_at=swing.pivot_time,
                confirmed_at=swing.confirmed_at,
                lifecycle_status=EvidenceLifecycleStatus.ACTIVE,
                metadata={
                    "scope": state.scope.value,
                    "trend": state.trend.value,
                    "swing_tier": swing.tier.value,
                    "pivot_time": swing.pivot_time.isoformat(),
                    "confirmed_at": swing.confirmed_at.isoformat(),
                },
                group_key=group_key,
            )

    # ------------------------------------------------------------------
    # Displacement
    # ------------------------------------------------------------------

    def _add_displacements(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for displacement in analysis.displacements:
            direction = self._direction(displacement.direction)

            group_key = self._price_action_group(
                displacement.open_time,
                direction,
            )

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.DISPLACEMENT,
                direction=direction,
                detected_at=displacement.open_time,
                confirmed_at=displacement.confirmed_at,
                lifecycle_status=EvidenceLifecycleStatus.ACTIVE,
                metadata={
                    "open_time": displacement.open_time.isoformat(),
                    "close_time": displacement.close_time.isoformat(),
                    "direction": displacement.direction.value,
                },
                group_key=group_key,
            )

    # ------------------------------------------------------------------
    # Structure breaks
    # ------------------------------------------------------------------

    def _add_structure_breaks(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for event in analysis.structure_breaks:
            direction = self._direction(event.direction)

            group_key = self._price_action_group(
                event.break_open_time,
                direction,
            )

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.STRUCTURE_BREAK,
                direction=direction,
                detected_at=event.break_open_time,
                confirmed_at=event.confirmed_at,
                lifecycle_status=EvidenceLifecycleStatus.ACTIVE,
                metadata={
                    "event_type": event.event_type.value,
                    "scope": event.scope.value,
                    "direction": event.direction.value,
                    "break_open_time": event.break_open_time.isoformat(),
                    "break_close_time": event.break_close_time.isoformat(),
                    "displacement_confirmed": event.displacement_confirmed,
                    "liquidity_sweep_preceded": (
                        event.liquidity_sweep_preceded
                    ),
                },
                group_key=group_key,
            )

    # ------------------------------------------------------------------
    # Liquidity sweeps
    # ------------------------------------------------------------------

    def _add_liquidity_sweeps(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for sweep in analysis.liquidity_sweeps:
            if sweep.liquidity_side == LiquiditySide.BUY_SIDE:
                direction = ConfluenceDirection.BEARISH
            else:
                direction = ConfluenceDirection.BULLISH

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.LIQUIDITY_SWEEP,
                direction=direction,
                detected_at=sweep.sweep_time,
                confirmed_at=sweep.confirmed_at,
                lifecycle_status=EvidenceLifecycleStatus.SWEPT,
                metadata={
                    "liquidity_side": sweep.liquidity_side.value,
                    "sweep_time": sweep.sweep_time.isoformat(),
                },
                group_key=(
                    f"liquidity_sweep:{sweep.sweep_time.isoformat()}:"
                    f"{sweep.liquidity_side.value}"
                ),
            )

    # ------------------------------------------------------------------
    # Fair value gaps
    # ------------------------------------------------------------------

    def _add_fair_value_gaps(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for fvg in analysis.fair_value_gaps:
            direction = self._direction(fvg.direction)
            lifecycle = self._fvg_lifecycle(fvg.status)

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.FAIR_VALUE_GAP,
                direction=direction,
                detected_at=fvg.first_candle_time,
                confirmed_at=fvg.confirmed_at,
                lifecycle_status=lifecycle,
                metadata={
                    "direction": fvg.direction.value,
                    "status": fvg.status.value,
                    "first_candle_time": (
                        fvg.first_candle_time.isoformat()
                    ),
                },
                group_key=(
                    f"fvg:{fvg.first_candle_time.isoformat()}:"
                    f"{fvg.direction.value}"
                ),
                invalidated_at=getattr(fvg, "invalidated_at", None),
            )

    # ------------------------------------------------------------------
    # Inverse fair value gaps
    # ------------------------------------------------------------------


    def _add_inverse_fvgs(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for inverse in analysis.inverse_fair_value_gaps:
            original = inverse.original_fvg

            direction = self._direction(inverse.inverse_direction)
            lifecycle = self._inverse_fvg_lifecycle(inverse.status)

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.INVERSE_FVG,
                direction=direction,
                detected_at=inverse.invalidation_candle_time,
                confirmed_at=inverse.confirmed_at,
                lifecycle_status=lifecycle,
                metadata={
                    "inverse_direction": inverse.inverse_direction.value,
                    "status": inverse.status.value,
                    "original_fvg_direction": original.direction.value,
                    "original_fvg_first_candle_time": (
                        original.first_candle_time.isoformat()
                    ),
                },
                group_key=(
                    f"fvg:{original.first_candle_time.isoformat()}:"
                    f"{direction.value}"
                ),
                invalidated_at=(
                    inverse.invalidation_candle_time
                    if lifecycle == EvidenceLifecycleStatus.INVALIDATED
                    else None
                ),
            )

    # ------------------------------------------------------------------
    # Balanced price ranges
    # ------------------------------------------------------------------

    def _add_balanced_price_ranges(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for bpr in analysis.balanced_price_ranges:
            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=(
                    ConfluenceEvidenceType.BALANCED_PRICE_RANGE
                ),
                direction=None,
                detected_at=bpr.confirmed_at,
                confirmed_at=bpr.confirmed_at,
                lifecycle_status=EvidenceLifecycleStatus.NOT_APPLICABLE,
                metadata={
                    "bullish_fvg_time": (
                        bpr.bullish_fvg.first_candle_time.isoformat()
                    ),
                    "bearish_fvg_time": (
                        bpr.bearish_fvg.first_candle_time.isoformat()
                    ),
                },
                group_key=(
                    f"bpr:{bpr.confirmed_at.isoformat()}"
                ),
            )

    # ------------------------------------------------------------------
    # Order blocks
    # ------------------------------------------------------------------

    def _add_order_blocks(
        self,
        analysis: ICTAnalysisResult,
        evidence: list[ConfluenceEvidence],
        group_by_id: dict[str, str],
    ) -> None:
        for order_block in analysis.order_blocks:
            direction = self._direction(order_block.direction)

            lifecycle = self._order_block_lifecycle(
                order_block.status
            )

            group_key = self._price_action_group(
                order_block.displacement_open_time,
                direction,
            )

            self._add(
                evidence,
                group_by_id,
                analysis=analysis,
                evidence_type=ConfluenceEvidenceType.ORDER_BLOCK,
                direction=direction,
                detected_at=order_block.origin_open_time,
                confirmed_at=order_block.confirmed_at,
                lifecycle_status=lifecycle,
                metadata={
                    "direction": order_block.direction.value,
                    "status": order_block.status.value,
                    "origin_open_time": (
                        order_block.origin_open_time.isoformat()
                    ),
                    "displacement_open_time": (
                        order_block.displacement_open_time.isoformat()
                    ),
                    "structure_break_open_time": (
                        order_block.structure_break_open_time.isoformat()
                    ),
                },
                group_key=group_key,
                invalidated_at=getattr(
                    order_block,
                    "invalidated_at",
                    None,
                ),
            )

    # ------------------------------------------------------------------
    # Evidence relationships
    # ------------------------------------------------------------------

    @staticmethod
    def _connect_related_evidence(
        evidence: list[ConfluenceEvidence],
    ) -> list[ConfluenceEvidence]:
        """
        Connect evidence that belongs to the same price-action sequence.

        Displacement, structure break, and order block observations remain
        separate evidence records, but their relationship is explicit.
        """
        by_candle: dict[str, list[str]] = defaultdict(list)

        for item in evidence:
            if item.evidence_type not in {
                ConfluenceEvidenceType.DISPLACEMENT,
                ConfluenceEvidenceType.STRUCTURE_BREAK,
                ConfluenceEvidenceType.ORDER_BLOCK,
            }:
                continue

            candle_time = (
                item.metadata.get("open_time")
                or item.metadata.get("break_open_time")
                or item.metadata.get("displacement_open_time")
            )

            if candle_time:
                key = (
                    f"{candle_time}:"
                    f"{item.direction.value if item.direction else 'NONE'}"
                )
                by_candle[key].append(item.evidence_id)

        connected: list[ConfluenceEvidence] = []

        for item in evidence:
            candle_time = (
                item.metadata.get("open_time")
                or item.metadata.get("break_open_time")
                or item.metadata.get("displacement_open_time")
            )

            related: tuple[str, ...] = item.related_evidence_ids

            if candle_time:
                key = (
                    f"{candle_time}:"
                    f"{item.direction.value if item.direction else 'NONE'}"
                )

                related = tuple(
                    evidence_id
                    for evidence_id in by_candle.get(key, [])
                    if evidence_id != item.evidence_id
                )

            connected.append(
                item.model_copy(
                    update={"related_evidence_ids": related}
                )
            )

        return connected

    # ------------------------------------------------------------------
    # Stream validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_stream(analysis: ICTAnalysisResult) -> None:
        """
        Ensure all top-level evidence belongs to the same market stream.

        InverseFairValueGap does not have top-level stream metadata.
        Its original_fvg contains the stream metadata and is validated
        separately below.
        """
        expected = (
            analysis.symbol,
            analysis.asset_class,
            analysis.timeframe,
            analysis.provider,
        )

        sources = (
            *analysis.swings,
            *analysis.displacements,
            *analysis.structure_breaks,
            *analysis.liquidity_pools,
            *analysis.liquidity_sweeps,
            *analysis.fair_value_gaps,
            *analysis.balanced_price_ranges,
            *analysis.order_blocks,
        )

        for source in sources:
            actual = (
                source.symbol,
                source.asset_class,
                source.timeframe,
                source.provider,
            )

            if actual != expected:
                raise ValueError(
                    "ICT evidence stream mismatch: "
                    f"expected {expected}, received {actual}"
                )

        # Corrected handling: validate the nested original FVG.
        for inverse in analysis.inverse_fair_value_gaps:
            original = inverse.original_fvg

            actual = (
                original.symbol,
                original.asset_class,
                original.timeframe,
                original.provider,
            )

            if actual != expected:
                raise ValueError(
                    "Inverse FVG original evidence stream mismatch: "
                    f"expected {expected}, received {actual}"
                )

    # ------------------------------------------------------------------
    # Direction and lifecycle helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _direction(value: Any) -> ConfluenceDirection:
        """Normalize bullish/bearish enum values or strings."""
        raw = value.value if hasattr(value, "value") else str(value)
        normalized = raw.strip().upper()

        mapping = {
            "BULLISH": ConfluenceDirection.BULLISH,
            "BEARISH": ConfluenceDirection.BEARISH,
        }
        if normalized not in mapping:
            raise ValueError(f"Unsupported directional value: {raw}")

        return mapping[normalized]

    @staticmethod
    def _fvg_lifecycle(
        status: ImbalanceStatus,
    ) -> EvidenceLifecycleStatus:
        mapping = {
            ImbalanceStatus.ACTIVE: EvidenceLifecycleStatus.ACTIVE,
            ImbalanceStatus.PARTIALLY_FILLED: (
                EvidenceLifecycleStatus.MITIGATED
            ),
            ImbalanceStatus.FILLED: EvidenceLifecycleStatus.MITIGATED,
            ImbalanceStatus.INVALIDATED: (
                EvidenceLifecycleStatus.INVALIDATED
            ),
            ImbalanceStatus.EXPIRED: EvidenceLifecycleStatus.EXPIRED,
        }

        return mapping[status]

    @staticmethod
    def _inverse_fvg_lifecycle(
        status: InverseFVGStatus,
    ) -> EvidenceLifecycleStatus:
        mapping = {
            InverseFVGStatus.CONFIRMED: EvidenceLifecycleStatus.ACTIVE,
            InverseFVGStatus.ACTIVE: EvidenceLifecycleStatus.ACTIVE,
            InverseFVGStatus.INVALIDATED: (
                EvidenceLifecycleStatus.INVALIDATED
            ),
            InverseFVGStatus.EXPIRED: EvidenceLifecycleStatus.EXPIRED,
        }

        return mapping[status]

    @staticmethod
    def _order_block_lifecycle(
        status: OrderBlockStatus,
    ) -> EvidenceLifecycleStatus:
        mapping = {
            OrderBlockStatus.ACTIVE: EvidenceLifecycleStatus.ACTIVE,
            OrderBlockStatus.MITIGATED: (
                EvidenceLifecycleStatus.MITIGATED
            ),
            OrderBlockStatus.INVALIDATED: (
                EvidenceLifecycleStatus.INVALIDATED
            ),
            OrderBlockStatus.EXPIRED: EvidenceLifecycleStatus.EXPIRED,
        }

        return mapping[status]

    @staticmethod
    def _price_action_group(
        candle_time: datetime,
        direction: ConfluenceDirection,
    ) -> str:
        return (
            f"price_action:{candle_time.isoformat()}:"
            f"{direction.value}"
        )

    # ------------------------------------------------------------------
    # Final confluence decision
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_status(
        *,
        bullish_count: int,
        bearish_count: int,
        evidence_count: int,
    ) -> ConfluenceStatus:
        if bullish_count > 0 and bearish_count > 0:
            return ConfluenceStatus.CONFLICTING

        if bullish_count >= 2:
            return ConfluenceStatus.BULLISH_ALIGNMENT

        if bearish_count >= 2:
            return ConfluenceStatus.BEARISH_ALIGNMENT

        if bullish_count == 1 or bearish_count == 1:
            return ConfluenceStatus.INSUFFICIENT_EVIDENCE

        if evidence_count > 0:
            return ConfluenceStatus.NEUTRAL

        return ConfluenceStatus.INSUFFICIENT_EVIDENCE


__all__ = ["ConfluenceService"]
