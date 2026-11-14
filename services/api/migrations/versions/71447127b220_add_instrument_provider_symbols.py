
"""add instrument provider symbols

Revision ID: 71447127b220
Revises: 88fb69edd77c
Create Date: 2026-11-08 20:32:56.068151
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "71447127b220"
down_revision: Union[str, Sequence[str], None] = "88fb69edd77c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_provider_symbols",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_symbol", sa.String(length=100), nullable=False),
        sa.Column(
            "provider_exchange",
            sa.String(length=100),
            server_default="",
            nullable=False,
        ),
        sa.Column("provider_instrument_id", sa.String(length=150), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_symbol",
            "provider_exchange",
            name="uq_provider_symbol_exchange",
        ),
    )

    op.create_index(
        "ix_provider_symbols_instrument_provider",
        "instrument_provider_symbols",
        ["instrument_id", "provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_symbols_instrument_provider",
        table_name="instrument_provider_symbols",
    )
    op.drop_table("instrument_provider_symbols")
