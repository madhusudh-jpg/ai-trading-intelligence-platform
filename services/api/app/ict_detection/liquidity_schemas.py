from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ict_detection.schemas import SwingPoint, SwingType
from app.ict_detection.structure_break_schemas import LiquiditySide
from app.market_data.schemas.market_data import AssetClass, Timeframe


class LiquidityPoolType(StrEnum):
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"


class LiquidityPoolStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    SWEPT = "swept"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class LiquidityDetectionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    price_tolerance: Decimal = Field(default=Decimal("0.10"), ge=0)
    minimum_touches: int = Field(default=2, ge=2)

    @field_validator("price_tolerance")
    @classmethod
    def validate_price_tolerance(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Price tolerance must be finite.")
        return value


class LiquidityPool(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    provider: str

    pool_type: LiquidityPoolType
    liquidity_side: LiquiditySide
    swing_type: SwingType

    price: Decimal
    lower_bound: Decimal
    upper_bound: Decimal

    swing_points: tuple[SwingPoint, ...]
    segment_id: int

    detected_at: object
    confirmed_at: object | None = None
    swept_at: object | None = None

    status: LiquidityPoolStatus = LiquidityPoolStatus.CANDIDATE

    @field_validator("price", "lower_bound", "upper_bound")
    @classmethod
    def validate_prices(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Liquidity prices must be finite and positive.")
        return value

    @model_validator(mode="after")
    def validate_pool(self) -> LiquidityPool:
        if not self.swing_points:
            raise ValueError("A liquidity pool must contain swing evidence.")

        if len(self.swing_points) < 2 and self.status != LiquidityPoolStatus.CANDIDATE:
            raise ValueError("A confirmed pool requires at least two swing points.")

        if self.lower_bound > self.upper_bound:
            raise ValueError("Lower bound cannot exceed upper bound.")

        if not self.lower_bound <= self.price <= self.upper_bound:
            raise ValueError("Pool price must lie within its bounds.")

        if self.pool_type == LiquidityPoolType.EQUAL_HIGHS:
            if self.swing_type != SwingType.HIGH:
                raise ValueError("Equal-high pools require high swings.")
            if self.liquidity_side != LiquiditySide.BUY_SIDE:
                raise ValueError("Equal-high pools must represent buy-side liquidity.")

        if self.pool_type == LiquidityPoolType.EQUAL_LOWS:
            if self.swing_type != SwingType.LOW:
                raise ValueError("Equal-low pools require low swings.")
            if self.liquidity_side != LiquiditySide.SELL_SIDE:
                raise ValueError("Equal-low pools must represent sell-side liquidity.")

        if self.status == LiquidityPoolStatus.CONFIRMED and self.confirmed_at is None:
            raise ValueError("Confirmed pools require a confirmation timestamp.")

        if self.status == LiquidityPoolStatus.SWEPT and self.swept_at is None:
            raise ValueError("Swept pools require a sweep timestamp.")

        return self