
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"

    __table_args__ = (
        CheckConstraint(
            "market_bias IN ('bullish', 'bearish', 'neutral', 'unknown')",
            name="ck_analysis_market_bias",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_analysis_status",
        ),
        Index("ix_analysis_user_created", "user_id", "created_at"),
        Index("ix_analysis_instrument_created", "instrument_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
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

    analysis_timeframe: Mapped[str] = mapped_column(String(20), nullable=False)

    market_bias: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False
    )

    market_structure: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    liquidity_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    timeframe_observations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    trading_session: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
