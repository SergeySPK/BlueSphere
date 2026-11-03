"""add demo flag and homeroom assignments

Revision ID: 908f4b3ab191
Revises: 800573f0b14a
Create Date: 2026-11-01 19:45:31.169152
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "908f4b3ab191"
down_revision: Union[str, Sequence[str], None] = "800573f0b14a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет demo-флаг"""

    op.add_column(
        "users",
        sa.Column(
            "is_demo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Убирает demo-флаг"""

    op.drop_column("users", "is_demo")
