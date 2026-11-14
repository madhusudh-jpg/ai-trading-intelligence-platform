
"""convert candles to timescale hypertable

Revision ID: 1ddba4f52b83
Revises: ae87fb8e0341
"""

from typing import Sequence, Union

from alembic import op


revision: str = "1ddba4f52b83"
down_revision: Union[str, Sequence[str], None] = "ae87fb8e0341"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        SELECT create_hypertable(
            'public.candles',
            'open_time',
            if_not_exists => TRUE,
            migrate_data => FALSE
        );
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Converting this hypertable back to a regular table is not "
        "automated because it could risk historical candle data. "
        "Perform a separately planned data-preserving migration."
    )
