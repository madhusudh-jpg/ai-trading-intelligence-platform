
from sqlalchemy import UniqueConstraint

from app.db.database import Base
from app.db.models import (
    AIAnalysisLog,
    Alert,
    AlertEvent,
    AnalysisSnapshot,
    BacktestResult,
    BacktestRun,
    Candle,
    ICTObservation,
    Instrument,
    InstrumentProviderSymbol,
    JournalAttachment,
    JournalEntry,
    RiskAssessment,
    TradeSetup,
    User,
    Watchlist,
    WatchlistItem,
)


def test_all_application_tables_are_registered():
    expected_tables = {
        "users",
        "instruments",
        "instrument_provider_symbols",
        "candles",
        "analysis_snapshots",
        "trade_setups",
        "risk_assessments",
        "ict_observations",
        "watchlists",
        "watchlist_items",
        "alerts",
        "alert_events",
        "ai_analysis_logs",
        "journal_entries",
        "journal_attachments",
        "backtest_runs",
        "backtest_results",
    }

    assert set(Base.metadata.tables.keys()) == expected_tables


def test_all_models_have_primary_keys():
    models = [
        AIAnalysisLog,
        Alert,
        AlertEvent,
        AnalysisSnapshot,
        BacktestResult,
        BacktestRun,
        Candle,
        ICTObservation,
        Instrument,
        InstrumentProviderSymbol,
        JournalAttachment,
        JournalEntry,
        RiskAssessment,
        TradeSetup,
        User,
        Watchlist,
        WatchlistItem,
    ]

    for model in models:
        assert model.__table__.primary_key is not None
        assert len(model.__table__.primary_key.columns) >= 1


def test_candle_has_composite_provider_instrument_foreign_key():
    foreign_keys = {
        foreign_key.target_fullname
        for foreign_key in Candle.__table__.foreign_keys
    }

    assert "instrument_provider_symbols.id" in foreign_keys
    assert "instrument_provider_symbols.instrument_id" in foreign_keys


def test_instrument_provider_symbol_has_instrument_foreign_key():
    foreign_keys = {
        foreign_key.target_fullname
        for foreign_key in InstrumentProviderSymbol.__table__.foreign_keys
    }

    assert "instruments.id" in foreign_keys


def test_provider_symbol_has_unique_provider_mapping():
    unique_constraints = {
        constraint.name
        for constraint in InstrumentProviderSymbol.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_provider_symbol_exchange" in unique_constraints
    assert "uq_provider_symbol_id_instrument" in unique_constraints


def test_trade_setup_has_required_foreign_keys():
    foreign_keys = {
        foreign_key.target_fullname
        for foreign_key in TradeSetup.__table__.foreign_keys
    }

    assert "users.id" in foreign_keys
    assert "instruments.id" in foreign_keys
    assert "analysis_snapshots.id" in foreign_keys


def test_trade_setup_has_direction_and_status_constraints():
    constraint_names = {
        constraint.name
        for constraint in TradeSetup.__table__.constraints
    }

    assert "ck_trade_setup_direction" in constraint_names
    assert "ck_trade_setup_status" in constraint_names


def test_watchlist_item_has_unique_watchlist_instrument_pair():
    unique_constraints = {
        constraint.name
        for constraint in WatchlistItem.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_watchlist_instrument" in unique_constraints
