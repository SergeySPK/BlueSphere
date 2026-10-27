
"""make school timezone optional

Revision ID: 77769e283a6e
Revises: d68f59653cb6
"""

from alembic import op
import sqlalchemy as sa


revision = "77769e283a6e"
down_revision = "d68f59653cb6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "schools",
        "timezone",
        existing_type=sa.String(length=100),
        nullable=True,
        existing_server_default=None,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE schools "
        "SET timezone = 'Asia/Yekaterinburg' "
        "WHERE timezone IS NULL"
    )

    op.alter_column(
        "schools",
        "timezone",
        existing_type=sa.String(length=100),
        nullable=False,
        server_default="Asia/Yekaterinburg",
        existing_server_default=None,
    )
