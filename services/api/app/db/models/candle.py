
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Candle(Base):
    __tablename__ = "candles"

    __table_args__ = (
        ForeignKeyConstraint(
            ["instrument_provider_symbol_id", "instrument_id"],
            [
                "instrument_provider_symbols.id",
                "instrument_provider_symbols.instrument_id",
            ],
            name="fk_candles_provider_symbol_instrument",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "instrument_provider_symbol_id",
            "timeframe",
            "open_time",
            name="uq_candle_provider_timeframe_open",
        ),
        CheckConstraint(
            "high >= low",
            name="ck_candle_high_gte_low",
        ),
        CheckConstraint(
            "high >= open AND high >= close",
            name="ck_candle_high_gte_open_close",
        ),
        CheckConstraint(
            "low <= open AND low <= close",
            name="ck_candle_low_lte_open_close",
        ),
        CheckConstraint(
            "volume IS NULL OR volume >= 0",
            name="ck_candle_volume_nonnegative",
        ),
        CheckConstraint(
            "close_time > open_time",
            name="ck_candle_close_after_open",
        ),
        Index(
            "ix_candles_instrument_time",
            "instrument_id",
            "timeframe",
            "open_time",
        ),
        Index(
            "ix_candles_provider_time",
            "instrument_provider_symbol_id",
            "open_time",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    instrument_provider_symbol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    timeframe: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )

    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    open: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    high: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    low: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    close: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    volume: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    is_complete: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
