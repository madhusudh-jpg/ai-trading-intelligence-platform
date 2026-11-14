
"""Add candle completion status.

Revision ID: 67f09fd339a3
Revises: 1ddba4f52b83
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "67f09fd339a3"
down_revision: Union[str, Sequence[str], None] = "1ddba4f52b83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add candle completion status and correct existing records."""

    op.add_column(
        "candles",
        sa.Column(
            "is_complete",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    # Existing candles are complete only when their interval has ended.
    op.execute(
        """
        UPDATE candles
        SET is_complete = (close_time <= CURRENT_TIMESTAMP)
        """
    )


def downgrade() -> None:
    """Remove candle completion status."""

    op.drop_column("candles", "is_complete")
