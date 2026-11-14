
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle as CandleModel
from app.db.models.instrument import Instrument
from app.db.models.instrument_provider_symbol import (
    InstrumentProviderSymbol,
)
from app.db.session import get_db
from app.market_data.providers.registry import provider_registry
from app.market_data.schemas.market_data import AssetClass, Timeframe
from app.market_data.services.market_data_service import MarketDataService
from app.schemas.common import ModuleStatus, PlatformOverview

router = APIRouter()


MODULES = [
    "trading_terminal",
    "market_data",
    "ict_detection",
    "multi_timeframe_analysis",
    "ai_copilot",
    "trade_setup_generation",
    "risk_management",
    "alerts_and_watchlists",
    "trading_journal",
    "backtesting",
]




@router.get("/", response_model=PlatformOverview)
def get_platform_overview() -> PlatformOverview:
    return PlatformOverview(
        name="AI Trading Intelligence Platform",
        supported_markets=[
            "forex",
            "crypto",
            "us_stocks",
            "indices",
            "nse_bse",
        ],
        execution_mode="analysis_only",
        modules=[
            ModuleStatus(name=module, status="planned")
            for module in MODULES
        ],
    )


@router.get("/markets")
def get_supported_markets() -> dict:
    return {
        "markets": [
            "forex",
            "crypto",
            "us_stocks",
            "indices",
            "nse_bse",
        ],
        "note": (
            "Market availability depends on configured provider "
            "coverage and licensing."
        ),
    }


@router.get("/market-data/providers", tags=["market-data"])
async def get_market_data_providers() -> dict:
    service = MarketDataService(provider_registry)
    statuses = await service.provider_statuses()

    return {
        "providers": [
            status.model_dump(mode="json")
            for status in statuses
        ],
        "configured_provider_count": len(statuses),
        "live_data_available": any(
            status.connected for status in statuses
        ),
    }


@router.get("/instruments", tags=["instruments"])
def get_instruments(
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[
        str | None,
        Query(min_length=1, max_length=100),
    ] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    exchange: Annotated[
        str | None,
        Query(min_length=1, max_length=100),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    """List and search active instruments with provider mappings."""

    instrument_query = select(Instrument).where(
        Instrument.is_active.is_(True)
    )

    if asset_class is not None:
        instrument_query = instrument_query.where(
            Instrument.asset_class == asset_class.value
        )

    if exchange is not None:
        instrument_query = instrument_query.where(
            Instrument.exchange.ilike(exchange.strip())
        )

    if search is not None:
        search_term = f"%{search.strip()}%"
        instrument_query = instrument_query.where(
            or_(
                Instrument.symbol.ilike(search_term),
                Instrument.name.ilike(search_term),
            )
        )

    instruments = db.scalars(
        instrument_query
        .order_by(Instrument.symbol.asc())
        .limit(limit)
    ).all()

    if not instruments:
        return {
            "count": 0,
            "instruments": [],
        }

    instrument_ids = [instrument.id for instrument in instruments]

    mappings = db.scalars(
        select(InstrumentProviderSymbol).where(
            InstrumentProviderSymbol.instrument_id.in_(instrument_ids),
            InstrumentProviderSymbol.is_active.is_(True),
        )
    ).all()

    mappings_by_instrument: dict[str, list[dict]] = {}

    for mapping in mappings:
        instrument_key = str(mapping.instrument_id)
        mappings_by_instrument.setdefault(instrument_key, []).append(
            {
                "provider": mapping.provider,
                "provider_symbol": mapping.provider_symbol,
                "provider_exchange": mapping.provider_exchange,
            }
        )

    return {
        "count": len(instruments),
        "instruments": [
            {
                "id": str(instrument.id),
                "symbol": instrument.symbol,
                "name": instrument.name,
                "asset_class": instrument.asset_class,
                "exchange": instrument.exchange,
                "base_currency": instrument.base_currency,
                "quote_currency": instrument.quote_currency,
                "provider_mappings": mappings_by_instrument.get(
                    str(instrument.id),
                    [],
                ),
            }
            for instrument in instruments
        ],
    }


@router.get("/market-data/candles", tags=["market-data"])
def get_market_data_candles(
    db: Annotated[Session, Depends(get_db)],
    timeframe: Annotated[Timeframe, Query()],
    instrument_id: Annotated[UUID | None, Query()] = None,
    symbol: Annotated[
        str | None,
        Query(min_length=1, max_length=100),
    ] = None,
    provider: Annotated[
        str | None,
        Query(min_length=1, max_length=50),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    start_time: Annotated[datetime | None, Query()] = None,
    end_time: Annotated[datetime | None, Query()] = None,
) -> dict:
    """Read stored candles using an instrument's provider mapping."""

    if instrument_id is None and symbol is None:
        raise HTTPException(
            status_code=422,
            detail="Provide either instrument_id or symbol.",
        )

    if instrument_id is not None and symbol is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide instrument_id or symbol, not both.",
        )

    if symbol is not None:
        symbol = symbol.strip().upper()

        if not symbol:
            raise HTTPException(
                status_code=422,
                detail="Symbol cannot be empty.",
            )

    if provider is not None:
        provider = provider.strip().lower()

        if not provider:
            raise HTTPException(
                status_code=422,
                detail="Provider cannot be empty.",
            )

    if (
        start_time is not None
        and end_time is not None
        and end_time <= start_time
    ):
        raise HTTPException(
            status_code=422,
            detail="end_time must be later than start_time.",
        )

    instrument_query = select(Instrument).where(
        Instrument.is_active.is_(True)
    )

    if instrument_id is not None:
        instrument_query = instrument_query.where(
            Instrument.id == instrument_id
        )
    else:
        instrument_query = instrument_query.where(
            Instrument.symbol.ilike(symbol)
        )

    instruments = db.scalars(instrument_query).all()

    if not instruments:
        raise HTTPException(
            status_code=404,
            detail="Active instrument not found.",
        )

    if len(instruments) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Multiple active instruments share this symbol. "
                "Use instrument_id to identify the exact instrument."
            ),
        )

    instrument = instruments[0]

    mappings_query = select(InstrumentProviderSymbol).where(
        InstrumentProviderSymbol.instrument_id == instrument.id,
        InstrumentProviderSymbol.is_active.is_(True),
    )

    if provider is not None:
        mappings_query = mappings_query.where(
            InstrumentProviderSymbol.provider == provider
        )

    mappings = db.scalars(mappings_query).all()

    if not mappings:
        raise HTTPException(
            status_code=404,
            detail="No active provider mapping found for this instrument.",
        )

    if len(mappings) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Multiple active provider mappings found. "
                "Specify the provider query parameter."
            ),
        )

    mapping = mappings[0]

    try:
        selected_provider = provider_registry.get(mapping.provider)
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{mapping.provider}' is not configured.",
        ) from exc

    capabilities = selected_provider.capabilities

    if instrument.asset_class not in {
        asset_class.value
        for asset_class in capabilities.supported_asset_classes
    }:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Provider '{mapping.provider}' does not support "
                f"the '{instrument.asset_class}' asset class."
            ),
        )

    if timeframe not in capabilities.supported_timeframes:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Provider '{mapping.provider}' does not support "
                f"the '{timeframe.value}' timeframe."
            ),
        )

    candle_query = select(CandleModel).where(
        CandleModel.instrument_provider_symbol_id == mapping.id,
        CandleModel.timeframe == timeframe.value,
    )

    if start_time is not None:
        candle_query = candle_query.where(
            CandleModel.open_time >= start_time
        )

    if end_time is not None:
        candle_query = candle_query.where(
            CandleModel.open_time < end_time
        )

    candle_query = (
        candle_query
        .order_by(CandleModel.open_time.desc())
        .limit(limit)
    )

    candles = db.scalars(candle_query).all()
    candles.reverse()

    return {
        "instrument_id": str(instrument.id),
        "symbol": instrument.symbol,
        "asset_class": instrument.asset_class,
        "exchange": instrument.exchange,
        "provider": mapping.provider,
        "provider_symbol": mapping.provider_symbol,
        "timeframe": timeframe.value,
        "count": len(candles),
        "candles": [
            {
                "open_time": candle.open_time.isoformat(),
                "close_time": candle.close_time.isoformat(),
                "open": str(Decimal(candle.open)),
                "high": str(Decimal(candle.high)),
                "low": str(Decimal(candle.low)),
                "close": str(Decimal(candle.close)),
                "volume": (
                    str(Decimal(candle.volume))
                    if candle.volume is not None
                    else None
                ),
                "is_complete": candle.is_complete,
            }
            for candle in candles
        ],
    }
