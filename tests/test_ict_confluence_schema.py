
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.ict_detection.confluence_schemas import (
    ConfluenceDirection,
    ConfluenceEvidence,
    ConfluenceEvidenceType,
    ConfluenceStatus,
    EvidenceLifecycleStatus,
    ICTConfluenceResult,
)


NOW = datetime.now(timezone.utc)


def create_evidence(**overrides):
    data = {
        "evidence_id": "displacement_001",
        "evidence_type": ConfluenceEvidenceType.DISPLACEMENT,
        "direction": ConfluenceDirection.BULLISH,
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "timeframe": "1h",
        "provider": "test",
        "detected_at": NOW,
        "confirmed_at": NOW + timedelta(minutes=5),
    }
    data.update(overrides)
    return ConfluenceEvidence(**data)


def create_confluence(**overrides):
    data = {
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "timeframe": "1h",
        "provider": "test",
        "analyzed_at": NOW,
        "status": ConfluenceStatus.BULLISH_ALIGNMENT,
        "evidence": (create_evidence(),),
        "bullish_evidence_count": 1,
        "bearish_evidence_count": 0,
    }
    data.update(overrides)
    return ICTConfluenceResult(**data)


def test_accepts_valid_evidence():
    evidence = create_evidence()

    assert evidence.direction == ConfluenceDirection.BULLISH
    assert evidence.evidence_type == ConfluenceEvidenceType.DISPLACEMENT


def test_rejects_naive_evidence_timestamp():
    with pytest.raises(ValidationError):
        create_evidence(detected_at=datetime(2026, 1, 1))


def test_rejects_confirmation_before_detection():
    with pytest.raises(ValidationError):
        create_evidence(
            confirmed_at=NOW - timedelta(minutes=1)
        )


def test_rejects_invalidation_before_confirmation():
    with pytest.raises(ValidationError):
        create_evidence(
            invalidated_at=NOW + timedelta(minutes=1)
        )


def test_rejects_self_referencing_evidence():
    with pytest.raises(ValidationError):
        create_evidence(
            related_evidence_ids=("displacement_001",)
        )


def test_rejects_duplicate_related_evidence_ids():
    with pytest.raises(ValidationError):
        create_evidence(
            related_evidence_ids=("event_001", "event_001")
        )


def test_accepts_valid_confluence_result():
    result = create_confluence()

    assert result.status == ConfluenceStatus.BULLISH_ALIGNMENT
    assert result.bullish_evidence_count == 1
    assert len(result.evidence) == 1


def test_rejects_duplicate_evidence_ids():
    evidence = create_evidence()

    with pytest.raises(ValidationError):
        create_confluence(evidence=(evidence, evidence))


def test_rejects_evidence_from_another_timeframe():
    evidence = create_evidence(timeframe="4h")

    with pytest.raises(ValidationError):
        create_confluence(evidence=(evidence,))


def test_rejects_negative_evidence_counts():
    with pytest.raises(ValidationError):
        create_confluence(bullish_evidence_count=-1)


def test_rejects_naive_analysis_timestamp():
    with pytest.raises(ValidationError):
        create_confluence(analyzed_at=datetime(2026, 1, 1))


def test_confluence_result_is_immutable():
    result = create_confluence()

    with pytest.raises(ValidationError):
        result.symbol = "ETHUSDT"
