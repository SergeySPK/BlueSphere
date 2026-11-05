"""add student survey progress

Revision ID: 50ef3f2598a7
Revises: 908f4b3ab191
Create Date: 2026-11-03 17:32:56.715920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50ef3f2598a7'
down_revision: Union[str, Sequence[str], None] = '908f4b3ab191'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "survey_notifications",
        sa.Column(
            "progress_status",
            sa.String(length=20),
            server_default="not_started",
            nullable=False,
        ),
    )

    op.add_column(
        "survey_notifications",
        sa.Column(
            "max_message_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "survey_notifications",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "survey_notifications",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "survey_notifications",
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_survey_notifications_progress_status",
        "survey_notifications",
        "progress_status IN ('not_started', 'in_progress', 'completed', 'closed')",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_survey_notifications_progress_status",
        "survey_notifications",
        type_="check",
    )

    op.drop_column("survey_notifications", "closed_at")
    op.drop_column("survey_notifications", "completed_at")
    op.drop_column("survey_notifications", "started_at")
    op.drop_column("survey_notifications", "max_message_id")
    op.drop_column("survey_notifications", "progress_status")
