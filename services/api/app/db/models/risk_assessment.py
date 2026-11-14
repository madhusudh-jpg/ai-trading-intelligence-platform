
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    __table_args__ = (
        CheckConstraint(
            "risk_amount >= 0",
            name="ck_risk_assessment_nonnegative_amount",
        ),
        CheckConstraint(
            "risk_percentage >= 0",
            name="ck_risk_assessment_nonnegative_percentage",
        ),
        CheckConstraint(
            "max_loss >= 0",
            name="ck_risk_assessment_nonnegative_max_loss",
        ),
        CheckConstraint(
            "status IN ('approved', 'warning', 'rejected')",
            name="ck_risk_assessment_status",
        ),
        Index(
            "ix_risk_assessments_setup_created",
            "trade_setup_id",
            "created_at",
        ),
        Index(
            "ix_risk_assessments_user_created",
            "user_id",
            "created_at",
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

    trade_setup_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("trade_setups.id", ondelete="CASCADE"),
        nullable=False,
    )

    account_balance: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    risk_percentage: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )

    risk_amount: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    position_size: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    max_loss: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    calculated_risk_reward: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    exposure_details: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    warnings: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    assessment_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
