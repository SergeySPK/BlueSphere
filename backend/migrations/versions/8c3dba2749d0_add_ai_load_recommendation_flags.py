"""add AI load recommendation flags

Revision ID: 8c3dba2749d0
Revises: b8ee30ff0e6c
Create Date: 2026-11-07 20:09:09.615559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c3dba2749d0'
down_revision: Union[str, Sequence[str], None] = 'b8ee30ff0e6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_daily_loads",
        sa.Column(
            "reduce_load",
            sa.Boolean(),
            nullable=True,
        ),
    )

    op.add_column(
        "ai_daily_loads",
        sa.Column(
            "suitable_for_moving",
            sa.Boolean(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "ai_daily_loads",
        "suitable_for_moving",
    )

    op.drop_column(
        "ai_daily_loads",
        "reduce_load",
    )
