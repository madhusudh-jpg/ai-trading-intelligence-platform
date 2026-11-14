
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Instrument(Base):
    __tablename__ = "instruments"

    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "symbol",
            name="uq_instrument_exchange_symbol",
        ),
        Index("ix_instrument_asset_class", "asset_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    asset_class: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    exchange: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    base_currency: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    quote_currency: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
