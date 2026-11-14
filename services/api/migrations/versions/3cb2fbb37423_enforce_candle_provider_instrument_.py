
"""enforce candle provider instrument consistency

Revision ID: 3cb2fbb37423
Revises: f46cf1f3dfdf
"""

from typing import Sequence, Union

from alembic import op


revision: str = "3cb2fbb37423"
down_revision: Union[str, Sequence[str], None] = "f46cf1f3dfdf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the referenced unique constraint first.
    op.create_unique_constraint(
        "uq_provider_symbol_id_instrument",
        "instrument_provider_symbols",
        ["id", "instrument_id"],
    )

    # Remove the previous independent foreign keys.
    op.drop_constraint(
        "fk_candles_instrument_id",
        "candles",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_candles_provider_symbol_id",
        "candles",
        type_="foreignkey",
    )

    # Enforce that the provider mapping belongs to the same instrument.
    op.create_foreign_key(
        "fk_candles_provider_symbol_instrument",
        "candles",
        "instrument_provider_symbols",
        ["instrument_provider_symbol_id", "instrument_id"],
        ["id", "instrument_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_candles_provider_symbol_instrument",
        "candles",
        type_="foreignkey",
    )

    # Restore the previous independent foreign keys.
    op.create_foreign_key(
        "fk_candles_instrument_id",
        "candles",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_candles_provider_symbol_id",
        "candles",
        "instrument_provider_symbols",
        ["instrument_provider_symbol_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "uq_provider_symbol_id_instrument",
        "instrument_provider_symbols",
        type_="unique",
    )
