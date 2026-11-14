
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


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

    lifecycle_status: EvidenceLifecycleStatus = (
        EvidenceLifecycleStatus.NOT_APPLICABLE
    )

    related_evidence_ids: tuple[str, ...] = ()

    invalidated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> "ConfluenceEvidence":
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
    def validate_confluence(self) -> "ICTConfluenceResult":
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


__all__ = [
    "ConfluenceDirection",
    "ConfluenceEvidence",
    "ConfluenceEvidenceType",
    "ConfluenceStatus",
    "EvidenceLifecycleStatus",
    "ICTConfluenceResult",
]
