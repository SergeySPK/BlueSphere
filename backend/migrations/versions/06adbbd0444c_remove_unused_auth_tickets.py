"""remove unused auth tickets

Revision ID: 06adbbd0444c
Revises: ccb331806eed
Create Date: 2026-10-30 00:33:05.697069

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06adbbd0444c'
down_revision: Union[str, Sequence[str], None] = 'ccb331806eed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the unused auth_tickets table."""
    op.drop_table("auth_tickets")


def downgrade() -> None:
    """Restore the auth_tickets table."""
    op.create_table(
        "auth_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_tickets_expires_at",
        "auth_tickets",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_tickets_ticket_hash",
        "auth_tickets",
        ["ticket_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_tickets_user_id",
        "auth_tickets",
        ["user_id"],
        unique=False,
    )
