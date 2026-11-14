
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_backtest_run_status",
        ),
        CheckConstraint(
            "end_time > start_time",
            name="ck_backtest_run_time_range",
        ),
        Index(
            "ix_backtest_runs_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_backtest_runs_instrument_status",
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

    strategy_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    timeframe: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    __table_args__ = (
        CheckConstraint(
            "total_trades >= 0",
            name="ck_backtest_result_total_trades",
        ),
        CheckConstraint(
            "winning_trades >= 0 AND losing_trades >= 0",
            name="ck_backtest_result_trade_counts",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    backtest_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    total_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    winning_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    losing_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    win_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    profit_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4),
        nullable=True,
    )

    max_drawdown: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4),
        nullable=True,
    )

    net_return: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4),
        nullable=True,
    )

    net_profit_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    additional_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
