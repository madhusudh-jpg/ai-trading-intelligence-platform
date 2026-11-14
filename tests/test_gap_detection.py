
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.market_data.schemas.market_data import Timeframe
from app.market_data.services.gap_detection_service import (
    CandleGapDetectionService,
)

BASE_TIME = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
PROVIDER_SYMBOL_ID = uuid4()


def make_database(stored_times):
    mapping = SimpleNamespace(
        id=PROVIDER_SYMBOL_ID,
        instrument_id=uuid4(),
        provider="binance",
        is_active=True,
    )

    instrument = SimpleNamespace(asset_class="crypto")

    db = MagicMock()
    db.get.side_effect = [mapping, instrument]
    db.scalars.return_value.all.return_value = stored_times

    return db


def detect_gaps(stored_times, hours=5):
    db = make_database(stored_times)

    return CandleGapDetectionService().find_missing_candles(
        db=db,
        instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
        timeframe=Timeframe.H1,
        start_time=BASE_TIME,
        end_time=BASE_TIME + timedelta(hours=hours),
        as_of=BASE_TIME + timedelta(hours=hours + 1),
    )


def test_no_missing_candles():
    stored = [
        BASE_TIME + timedelta(hours=hour)
        for hour in range(5)
    ]

    result = detect_gaps(stored)

    assert result["expected_candles"] == 5
    assert result["stored_candles"] == 5
    assert result["missing_count"] == 0
    assert result["missing_ranges"] == []


def test_single_missing_candle():
    stored = [
        BASE_TIME,
        BASE_TIME + timedelta(hours=1),
        BASE_TIME + timedelta(hours=3),
        BASE_TIME + timedelta(hours=4),
    ]

    result = detect_gaps(stored)

    assert result["missing_count"] == 1
    assert result["missing_candles"] == [
        BASE_TIME + timedelta(hours=2)
    ]

    assert result["missing_ranges"] == [
        {
            "start_time": BASE_TIME + timedelta(hours=2),
            "end_time": BASE_TIME + timedelta(hours=3),
        }
    ]


def test_consecutive_missing_candles_are_grouped():
    stored = [
        BASE_TIME,
        BASE_TIME + timedelta(hours=4),
    ]

    result = detect_gaps(stored)

    assert result["missing_count"] == 3
    assert result["missing_ranges"] == [
        {
            "start_time": BASE_TIME + timedelta(hours=1),
            "end_time": BASE_TIME + timedelta(hours=4),
        }
    ]


def test_separate_gaps_create_separate_ranges():
    stored = [
        BASE_TIME,
        BASE_TIME + timedelta(hours=2),
        BASE_TIME + timedelta(hours=4),
    ]

    result = detect_gaps(stored)

    assert result["missing_count"] == 2
    assert result["missing_ranges"] == [
        {
            "start_time": BASE_TIME + timedelta(hours=1),
            "end_time": BASE_TIME + timedelta(hours=2),
        },
        {
            "start_time": BASE_TIME + timedelta(hours=3),
            "end_time": BASE_TIME + timedelta(hours=4),
        },
    ]


def test_still_forming_candles_are_not_expected():
    db = make_database([BASE_TIME])

    result = CandleGapDetectionService().find_missing_candles(
        db=db,
        instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
        timeframe=Timeframe.H1,
        start_time=BASE_TIME,
        end_time=BASE_TIME + timedelta(hours=5),
        as_of=BASE_TIME + timedelta(hours=2, minutes=30),
    )

    assert result["expected_candles"] == 2
    assert result["stored_candles"] == 1
    assert result["missing_count"] == 1
    assert result["missing_candles"] == [
        BASE_TIME + timedelta(hours=1)
    ]


def test_naive_start_time_is_rejected():
    db = make_database([])

    with pytest.raises(ValueError, match="start_time"):
        CandleGapDetectionService().find_missing_candles(
            db=db,
            instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
            timeframe=Timeframe.H1,
            start_time=datetime(2026, 11, 9, 10, 0),
            end_time=BASE_TIME + timedelta(hours=5),
        )


def test_naive_end_time_is_rejected():
    db = make_database([])

    with pytest.raises(ValueError, match="end_time"):
        CandleGapDetectionService().find_missing_candles(
            db=db,
            instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=datetime(2026, 11, 9, 15, 0),
        )


def test_naive_as_of_is_rejected():
    db = make_database([])

    with pytest.raises(ValueError, match="as_of"):
        CandleGapDetectionService().find_missing_candles(
            db=db,
            instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=BASE_TIME + timedelta(hours=5),
            as_of=datetime(2026, 11, 9, 16, 0),
        )


def test_misaligned_start_time_is_rejected():
    db = make_database([])

    with pytest.raises(ValueError, match="aligned"):
        CandleGapDetectionService().find_missing_candles(
            db=db,
            instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME + timedelta(minutes=30),
            end_time=BASE_TIME + timedelta(hours=5),
        )


def test_inactive_mapping_is_rejected():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(
        provider="binance",
        is_active=False,
    )

    with pytest.raises(ValueError, match="Active provider-symbol"):
        CandleGapDetectionService().find_missing_candles(
            db=db,
            instrument_provider_symbol_id=PROVIDER_SYMBOL_ID,
            timeframe=Timeframe.H1,
            start_time=BASE_TIME,
            end_time=BASE_TIME + timedelta(hours=5),
        )
