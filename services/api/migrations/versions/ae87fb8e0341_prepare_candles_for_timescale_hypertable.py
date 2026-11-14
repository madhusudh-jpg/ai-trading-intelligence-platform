
"""prepare candles for timescale hypertable

Revision ID: ae87fb8e0341
Revises: 3cb2fbb37423
"""

from typing import Sequence, Union

from alembic import op


revision: str = "ae87fb8e0341"
down_revision: Union[str, Sequence[str], None] = "3cb2fbb37423"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Replace the single-column primary key with a composite primary key.
    op.drop_constraint(
        "candles_pkey",
        "candles",
        type_="primary",
    )

    op.create_primary_key(
        "candles_pkey",
        "candles",
        ["id", "open_time"],
    )


def downgrade() -> None:
    # Restore the original single-column primary key.
    op.drop_constraint(
        "candles_pkey",
        "candles",
        type_="primary",
    )

    op.create_primary_key(
        "candles_pkey",
        "candles",
        ["id"],
    )
