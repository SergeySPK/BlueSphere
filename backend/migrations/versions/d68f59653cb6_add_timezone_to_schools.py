"""add timezone to schools

Revision ID: d68f59653cb6
Revises: b0f8d0ae9821
"""

from alembic import op
import sqlalchemy as sa


revision = "d68f59653cb6"
down_revision = "b0f8d0ae9821"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schools",
        sa.Column(
            "timezone",
            sa.String(length=100),
            nullable=False,
            server_default="Asia/Yekaterinburg",
        ),
    )

    op.alter_column(
        "schools",
        "timezone",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("schools", "timezone")
