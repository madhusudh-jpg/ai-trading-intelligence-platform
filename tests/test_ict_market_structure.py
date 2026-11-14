
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ict_detection import (
    MarketStructureConfig,
    MarketStructureService,
    MarketTrend,
    StructureScope,
    SwingClassification,
    SwingConfirmationBasis,
    SwingPoint,
    SwingTier,
    SwingType,
)
from app.market_data.schemas.market_data import (
    AssetClass,
    Timeframe,
)


def make_swing(
    index: int,
    price: str,
    swing_type: SwingType,
    *,
    tier: SwingTier = SwingTier.SHORT_TERM,
    segment_id: int = 0,
    symbol: str = "BTCUSDT",
) -> SwingPoint:
    pivot_time = (
        datetime(2026, 1, 1, tzinfo=UTC)
        + timedelta(hours=index)
    )

    return SwingPoint(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.H1,
        provider="binance",
        swing_type=swing_type,
        tier=tier,
        price=Decimal(price),
        pivot_time=pivot_time,
        confirmed_at=pivot_time + timedelta(hours=1),
        pivot_index=index,
        segment_id=segment_id,
        left_bars=2,
        right_bars=2,
        confirmation_basis=SwingConfirmationBasis.FRACTAL,
    )


def test_classifies_higher_high_and_higher_low():
    swings = [
        make_swing(0, "90", SwingType.LOW),
        make_swing(1, "100", SwingType.HIGH),
        make_swing(2, "95", SwingType.LOW),
        make_swing(3, "110", SwingType.HIGH),
    ]

    result = MarketStructureService().analyze(swings)

    high_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.HIGH
    ]

    low_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.LOW
    ]

    assert high_labels == [
        SwingClassification.INITIAL,
        SwingClassification.HH,
    ]
    assert low_labels == [
        SwingClassification.INITIAL,
        SwingClassification.HL,
    ]
    assert result.internal.trend == MarketTrend.BULLISH


def test_classifies_lower_high_and_lower_low():
    swings = [
        make_swing(0, "110", SwingType.HIGH),
        make_swing(1, "100", SwingType.LOW),
        make_swing(2, "105", SwingType.HIGH),
        make_swing(3, "95", SwingType.LOW),
    ]

    result = MarketStructureService().analyze(swings)

    high_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.HIGH
    ]
    low_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.LOW
    ]

    assert high_labels[-1] == SwingClassification.LH
    assert low_labels[-1] == SwingClassification.LL
    assert result.internal.trend == MarketTrend.BEARISH


def test_classifies_equal_highs_and_equal_lows():
    swings = [
        make_swing(0, "100", SwingType.HIGH),
        make_swing(1, "90", SwingType.LOW),
        make_swing(2, "100.05", SwingType.HIGH),
        make_swing(3, "90.05", SwingType.LOW),
    ]

    service = MarketStructureService(
        MarketStructureConfig(
            price_tolerance=Decimal("0.10")
        )
    )

    result = service.analyze(swings)

    high_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.HIGH
    ]
    low_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.LOW
    ]

    assert high_labels[-1] == SwingClassification.EQH
    assert low_labels[-1] == SwingClassification.EQL
    assert result.internal.trend == MarketTrend.RANGING


def test_classifies_mixed_structure_as_transitional():
    swings = [
        make_swing(0, "100", SwingType.HIGH),
        make_swing(1, "90", SwingType.LOW),
        make_swing(2, "110", SwingType.HIGH),
        make_swing(3, "85", SwingType.LOW),
    ]

    result = MarketStructureService().analyze(swings)

    assert result.internal.trend == MarketTrend.TRANSITIONAL


def test_returns_unknown_when_insufficient_swings():
    swings = [
        make_swing(0, "100", SwingType.HIGH),
        make_swing(1, "90", SwingType.LOW),
    ]

    result = MarketStructureService().analyze(swings)

    assert result.internal.trend == MarketTrend.UNKNOWN


def test_identifies_bullish_protection_candidates():
    swings = [
        make_swing(0, "90", SwingType.LOW),
        make_swing(1, "100", SwingType.HIGH),
        make_swing(2, "95", SwingType.LOW),
        make_swing(3, "110", SwingType.HIGH),
    ]

    state = MarketStructureService().analyze(swings).internal

    assert state.protected_low_candidate is not None
    assert state.protected_low_candidate.price == Decimal("95")

    assert state.strong_low_candidate is not None
    assert state.strong_low_candidate.price == Decimal("95")

    assert state.weak_high_candidate is not None
    assert state.weak_high_candidate.price == Decimal("110")

    assert state.protected_high_candidate is None
    assert state.weak_low_candidate is None


def test_identifies_bearish_protection_candidates():
    swings = [
        make_swing(0, "110", SwingType.HIGH),
        make_swing(1, "100", SwingType.LOW),
        make_swing(2, "105", SwingType.HIGH),
        make_swing(3, "95", SwingType.LOW),
    ]

    state = MarketStructureService().analyze(swings).internal

    assert state.protected_high_candidate is not None
    assert state.protected_high_candidate.price == Decimal("105")

    assert state.strong_high_candidate is not None
    assert state.strong_high_candidate.price == Decimal("105")

    assert state.weak_low_candidate is not None
    assert state.weak_low_candidate.price == Decimal("95")


def test_keeps_three_structure_tiers_separate():
    swings = []

    tier_data = [
        (
            SwingTier.SHORT_TERM,
            ["95", "100", "90", "110"],
        ),
        (
            SwingTier.INTERMEDIATE_TERM,
            ["100", "110", "90", "105"],
        ),
        (
            SwingTier.LONG_TERM,
            ["95", "100", "90", "110"],
        ),
    ]

    for tier, prices in tier_data:
        specifications = [
            (0, prices[0], SwingType.LOW),
            (1, prices[1], SwingType.HIGH),
            (2, prices[2], SwingType.LOW),
            (3, prices[3], SwingType.HIGH),
        ]

        swings.extend(
            make_swing(
                index,
                price,
                swing_type,
                tier=tier,
            )
            for index, price, swing_type in specifications
        )

    result = MarketStructureService().analyze(swings)

    assert result.internal.scope == StructureScope.INTERNAL
    assert result.intermediate.scope == StructureScope.INTERMEDIATE
    assert result.external.scope == StructureScope.EXTERNAL

    assert result.internal.trend == MarketTrend.TRANSITIONAL
    assert result.intermediate.trend == MarketTrend.BEARISH
    assert result.external.trend == MarketTrend.TRANSITIONAL


def test_does_not_compare_swings_across_data_segments():
    swings = [
        make_swing(0, "100", SwingType.HIGH, segment_id=0),
        make_swing(1, "110", SwingType.HIGH, segment_id=1),
        make_swing(0, "90", SwingType.LOW, segment_id=0),
        make_swing(1, "95", SwingType.LOW, segment_id=1),
    ]

    result = MarketStructureService().analyze(swings)

    high_labels = [
        item.classification
        for item in result.classified_swings
        if item.swing.swing_type == SwingType.HIGH
    ]

    assert high_labels == [
        SwingClassification.INITIAL,
        SwingClassification.INITIAL,
    ]
    assert result.internal.segment_id == 1
    assert result.internal.trend == MarketTrend.UNKNOWN


def test_rejects_mixed_instruments():
    swings = [
        make_swing(0, "100", SwingType.HIGH),
        make_swing(1, "105", SwingType.HIGH, symbol="ETHUSDT"),
    ]

    with pytest.raises(ValueError, match="same symbol"):
        MarketStructureService().analyze(swings)


def test_rejects_duplicate_swings():
    swing = make_swing(0, "100", SwingType.HIGH)

    with pytest.raises(ValueError, match="Duplicate"):
        MarketStructureService().analyze([swing, swing])


def test_rejects_empty_swing_input():
    with pytest.raises(ValueError, match="At least one"):
        MarketStructureService().analyze([])


def test_rejects_negative_tolerance():
    with pytest.raises(ValueError, match="non-negative"):
        MarketStructureConfig(
            price_tolerance=Decimal("-0.1")
        )
