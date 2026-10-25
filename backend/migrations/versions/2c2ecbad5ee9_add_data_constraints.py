"""add data constraints

Revision ID: 2c2ecbad5ee9
Revises: 9d208ef11222
Create Date: 2026-10-25 15:43:30.043230
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '2c2ecbad5ee9'
down_revision: Union[str, Sequence[str], None] = '9d208ef11222'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ограничения уже создаются начальной миграцией."""
    pass


def downgrade() -> None:
    """Ограничения остаются частью начальной миграции."""
    pass
