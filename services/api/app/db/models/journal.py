
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    __table_args__ = (
        Index("ix_journal_entries_user_created", "user_id", "created_at"),
        Index("ix_journal_entries_setup", "trade_setup_id"),
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

    trade_setup_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("trade_setups.id", ondelete="SET NULL"),
        nullable=True,
    )

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    entry_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    market_observations: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    decision_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    lessons_learned: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    outcome: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    realized_pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10),
        nullable=True,
    )

    tags: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
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


class JournalAttachment(Base):
    __tablename__ = "journal_attachments"

    __table_args__ = (
        Index("ix_journal_attachments_entry", "journal_entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    file_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    file_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
