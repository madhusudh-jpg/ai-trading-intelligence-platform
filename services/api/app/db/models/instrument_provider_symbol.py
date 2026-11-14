
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class InstrumentProviderSymbol(Base):
    __tablename__ = "instrument_provider_symbols"

    __table_args__ = (
        ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name="fk_provider_symbols_instrument_id",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider",
            "provider_symbol",
            "provider_exchange",
            name="uq_provider_symbol_exchange",
        ),
        UniqueConstraint(
            "id",
            "instrument_id",
            name="uq_provider_symbol_id_instrument",
        ),
        Index(
            "ix_provider_symbols_instrument_provider",
            "instrument_id",
            "provider",
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

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    provider_symbol: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    provider_exchange: Mapped[str] = mapped_column(
        String(100),
        default="",
        nullable=False,
    )

    provider_instrument_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
