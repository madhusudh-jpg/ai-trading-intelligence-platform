
"""add candle provider mapping and validation

Revision ID: f46cf1f3dfdf
Revises: 71447127b220
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f46cf1f3dfdf"
down_revision: Union[str, Sequence[str], None] = "71447127b220"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the provider mapping as nullable first.
    op.add_column(
        "candles",
        sa.Column(
            "instrument_provider_symbol_id",
            sa.Uuid(),
            nullable=True,
        ),
    )

    # The candles table is currently empty, so this is safe.
    op.alter_column(
        "candles",
        "instrument_provider_symbol_id",
        nullable=False,
    )

    # Replace the old uniqueness constraint.
    op.drop_constraint(
        "uq_candle_instrument_timeframe_open",
        "candles",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_candle_provider_timeframe_open",
        "candles",
        [
            "instrument_provider_symbol_id",
            "timeframe",
            "open_time",
        ],
    )

    # Replace the instrument foreign key with RESTRICT.
    op.drop_constraint(
        "candles_instrument_id_fkey",
        "candles",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_candles_instrument_id",
        "candles",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Add provider mapping foreign key.
    op.create_foreign_key(
        "fk_candles_provider_symbol_id",
        "candles",
        "instrument_provider_symbols",
        ["instrument_provider_symbol_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Add query indexes.
    op.create_index(
        "ix_candles_provider_time",
        "candles",
        ["instrument_provider_symbol_id", "open_time"],
        unique=False,
    )

    # Add candle data validation constraints.
    op.create_check_constraint(
        "ck_candle_high_gte_low",
        "candles",
        "high >= low",
    )

    op.create_check_constraint(
        "ck_candle_high_gte_open_close",
        "candles",
        "high >= open AND high >= close",
    )

    op.create_check_constraint(
        "ck_candle_low_lte_open_close",
        "candles",
        "low <= open AND low <= close",
    )

    op.create_check_constraint(
        "ck_candle_volume_nonnegative",
        "candles",
        "volume IS NULL OR volume >= 0",
    )

    op.create_check_constraint(
        "ck_candle_close_after_open",
        "candles",
        "close_time > open_time",
    )

    # Provider identity is now obtained through the mapping table.
    op.drop_column("candles", "source")


def downgrade() -> None:
    # Restore the source column using the provider mapping.
    op.add_column(
        "candles",
        sa.Column("source", sa.String(length=50), nullable=True),
    )

    op.execute(
        """
        UPDATE candles
        SET source = instrument_provider_symbols.provider
        FROM instrument_provider_symbols
        WHERE candles.instrument_provider_symbol_id =
              instrument_provider_symbols.id
        """
    )

    op.alter_column(
        "candles",
        "source",
        nullable=False,
    )

    # Remove validation constraints.
    op.drop_constraint(
        "ck_candle_close_after_open",
        "candles",
        type_="check",
    )
    op.drop_constraint(
        "ck_candle_volume_nonnegative",
        "candles",
        type_="check",
    )
    op.drop_constraint(
        "ck_candle_low_lte_open_close",
        "candles",
        type_="check",
    )
    op.drop_constraint(
        "ck_candle_high_gte_open_close",
        "candles",
        type_="check",
    )
    op.drop_constraint(
        "ck_candle_high_gte_low",
        "candles",
        type_="check",
    )

    op.drop_index(
        "ix_candles_provider_time",
        table_name="candles",
    )

    op.drop_constraint(
        "fk_candles_provider_symbol_id",
        "candles",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_candles_instrument_id",
        "candles",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "candles_instrument_id_fkey",
        "candles",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "uq_candle_provider_timeframe_open",
        "candles",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_candle_instrument_timeframe_open",
        "candles",
        ["instrument_id", "timeframe", "open_time"],
    )

    op.drop_column(
        "candles",
        "instrument_provider_symbol_id",
    )
