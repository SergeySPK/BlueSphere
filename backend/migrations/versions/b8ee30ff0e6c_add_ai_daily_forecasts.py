"""add ai daily forecasts

Revision ID: b8ee30ff0e6c
Revises: 02d18177beb0
Create Date: 2026-11-06 16:04:49.907554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8ee30ff0e6c'
down_revision: Union[str, Sequence[str], None] = '02d18177beb0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_daily_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=20),
            server_default=sa.text("'ai'"),
            nullable=False,
        ),
        sa.Column("analysis_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level BETWEEN 0 AND 4",
            name="ck_ai_daily_forecasts_level",
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'python')",
            name="ck_ai_daily_forecasts_source",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["ai_analysis_runs.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "class_id",
            "date",
            name="uq_ai_daily_forecasts_class_date",
        ),
    )

    op.add_column(
        "ai_analysis_jobs",
        sa.Column(
            "analysis_date",
            sa.Date(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE ai_analysis_jobs
        SET analysis_date = period_start
        WHERE analysis_date IS NULL
        """
    )

    op.alter_column(
        "ai_analysis_jobs",
        "analysis_date",
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("ai_analysis_jobs", "analysis_date")
    op.drop_table("ai_daily_forecasts")
