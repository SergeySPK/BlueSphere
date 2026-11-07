"""link ai analysis runs to jobs

Revision ID: 02d18177beb0
Revises: a25549164ce3
Create Date: 2026-11-06 11:06:25.937612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02d18177beb0'
down_revision: Union[str, Sequence[str], None] = 'a25549164ce3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_analysis_runs",
        sa.Column("job_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "fk_ai_analysis_runs_job_id",
        "ai_analysis_runs",
        "ai_analysis_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_ai_analysis_runs_job_id",
        "ai_analysis_runs",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ai_analysis_runs_job_id",
        "ai_analysis_runs",
        type_="unique",
    )
    op.drop_constraint(
        "fk_ai_analysis_runs_job_id",
        "ai_analysis_runs",
        type_="foreignkey",
    )
    op.drop_column("ai_analysis_runs", "job_id")
