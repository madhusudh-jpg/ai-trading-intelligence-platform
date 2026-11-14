
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ICTObservation(Base):
    __tablename__ = "ict_observations"

    __table_args__ = (
        CheckConstraint(
            "observation_type IN ("
            "'fvg', 'order_block', 'bos', 'choch', "
            "'liquidity_sweep', 'equal_highs', 'equal_lows', "
            "'premium_discount', 'other')",
            name="ck_ict_observation_type",
        ),
        CheckConstraint(
            "direction IN ('bullish', 'bearish', 'neutral', 'unknown')",
            name="ck_ict_observation_direction",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ict_observation_confidence",
        ),
        Index(
            "ix_ict_observations_instrument_time",
            "instrument_id",
            "detected_at",
        ),
        Index(
            "ix_ict_observations_analysis",
            "analysis_snapshot_id",
        ),
        Index(
            "ix_ict_observations_type_timeframe",
            "observation_type",
            "timeframe",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=False,
    )

    analysis_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    observation_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    direction: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        nullable=False,
    )

    timeframe: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    upper_price: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    lower_price: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )

    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
