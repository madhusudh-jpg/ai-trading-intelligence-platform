
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TradeSetup(Base):
    __tablename__ = "trade_setups"

    __table_args__ = (
        CheckConstraint(
            "direction IN ('long', 'short')",
            name="ck_trade_setup_direction",
        ),
        CheckConstraint(
            (
                "status IN "
                "('draft', 'active', 'triggered', 'invalidated', 'expired', 'closed')"
            ),
            name="ck_trade_setup_status",
        ),
        CheckConstraint(
            "entry_price > 0",
            name="ck_trade_setup_entry_price",
        ),
        CheckConstraint(
            "stop_loss > 0",
            name="ck_trade_setup_stop_loss",
        ),
        Index(
            "ix_trade_setups_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_trade_setups_instrument_status",
            "instrument_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=False,
    )

    analysis_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )

    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    stop_loss: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    take_profit_1: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    take_profit_2: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    take_profit_3: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    timeframe: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    invalidation_conditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
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
