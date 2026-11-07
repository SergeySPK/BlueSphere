"""add ai analysis subsystem

Revision ID: a25549164ce3
Revises: 400eac312a98
Create Date: 2026-11-05 03:47:21.963634
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a25549164ce3"
down_revision: Union[str, Sequence[str], None] = "400eac312a98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Связь вариантов опроса с предметами.
    op.add_column(
        "survey_instance_options",
        sa.Column("subject_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_survey_instance_options_subject",
        "survey_instance_options",
        "subjects",
        ["subject_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_survey_instance_options_subject_id",
        "survey_instance_options",
        ["subject_id"],
        unique=False,
    )

    # История запусков AI-анализа.
    op.create_table(
        "ai_analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=30), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope IN ('class', 'school')",
            name="ck_ai_analysis_runs_scope",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_ai_analysis_runs_status",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_ai_analysis_runs_period",
        ),
        sa.CheckConstraint(
            "(scope = 'class' AND class_id IS NOT NULL) "
            "OR (scope = 'school' AND class_id IS NULL)",
            name="ck_ai_analysis_runs_scope_class",
        ),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["school_id", "academic_year_id"],
            ["academic_years.school_id", "academic_years.id"],
            name="fk_ai_analysis_runs_school_year",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id", "school_id", "academic_year_id"],
            ["classes.id", "classes.school_id", "classes.academic_year_id"],
            name="fk_ai_analysis_runs_class_school_year",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_analysis_runs_school_period",
        "ai_analysis_runs",
        ["school_id", "period_start", "period_end"],
    )
    op.create_index(
        "ix_ai_analysis_runs_class_created",
        "ai_analysis_runs",
        ["class_id", "created_at"],
    )
    op.create_index(
        "ix_ai_analysis_runs_status_created",
        "ai_analysis_runs",
        ["status", "created_at"],
    )

    # История дневной нагрузки.
    op.create_table(
        "ai_daily_loads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=30),
            server_default="ai",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level BETWEEN 0 AND 4",
            name="ck_ai_daily_loads_level",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["ai_analysis_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id",
            "class_id",
            "date",
            name="uq_ai_daily_loads_run_class_date",
        ),
    )
    op.create_index(
        "ix_ai_daily_loads_class_date",
        "ai_daily_loads",
        ["class_id", "date"],
    )
    op.create_index(
        "ix_ai_daily_loads_run",
        "ai_daily_loads",
        ["analysis_run_id"],
    )

    # Рекомендации для классов, учителей и отдельных уроков.
    op.create_table(
        "ai_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=True),
        sa.Column("schedule_id", sa.Integer(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=20),
            server_default="normal",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("recommendation_text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('class', 'teacher', 'lesson')",
            name="ck_ai_recommendations_kind",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name="ck_ai_recommendations_priority",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["ai_analysis_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["schedule.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_recommendations_class_date",
        "ai_recommendations",
        ["class_id", "date"],
    )
    op.create_index(
        "ix_ai_recommendations_teacher_date",
        "ai_recommendations",
        ["teacher_id", "date"],
    )
    op.create_index(
        "ix_ai_recommendations_run",
        "ai_recommendations",
        ["analysis_run_id"],
    )

    # Очередь фоновых AI-задач.
    op.create_table(
        "ai_analysis_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="queued",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default="5",
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
            "scope IN ('class', 'school')",
            name="ck_ai_analysis_jobs_scope",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_ai_analysis_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_ai_analysis_jobs_attempts",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_ai_analysis_jobs_period",
        ),
        sa.CheckConstraint(
            "(scope = 'class' AND class_id IS NOT NULL) "
            "OR (scope = 'school' AND class_id IS NULL)",
            name="ck_ai_analysis_jobs_scope_class",
        ),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["school_id", "academic_year_id"],
            ["academic_years.school_id", "academic_years.id"],
            name="fk_ai_analysis_jobs_school_year",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id", "school_id", "academic_year_id"],
            ["classes.id", "classes.school_id", "classes.academic_year_id"],
            name="fk_ai_analysis_jobs_class_school_year",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_ai_analysis_jobs_available",
        "ai_analysis_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_ai_analysis_jobs_lease",
        "ai_analysis_jobs",
        ["locked_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_analysis_jobs_lease",
        table_name="ai_analysis_jobs",
    )
    op.drop_index(
        "ix_ai_analysis_jobs_available",
        table_name="ai_analysis_jobs",
    )
    op.drop_table("ai_analysis_jobs")

    op.drop_index(
        "ix_ai_recommendations_run",
        table_name="ai_recommendations",
    )
    op.drop_index(
        "ix_ai_recommendations_teacher_date",
        table_name="ai_recommendations",
    )
    op.drop_index(
        "ix_ai_recommendations_class_date",
        table_name="ai_recommendations",
    )
    op.drop_table("ai_recommendations")

    op.drop_index(
        "ix_ai_daily_loads_run",
        table_name="ai_daily_loads",
    )
    op.drop_index(
        "ix_ai_daily_loads_class_date",
        table_name="ai_daily_loads",
    )
    op.drop_table("ai_daily_loads")

    op.drop_index(
        "ix_ai_analysis_runs_status_created",
        table_name="ai_analysis_runs",
    )
    op.drop_index(
        "ix_ai_analysis_runs_class_created",
        table_name="ai_analysis_runs",
    )
    op.drop_index(
        "ix_ai_analysis_runs_school_period",
        table_name="ai_analysis_runs",
    )
    op.drop_table("ai_analysis_runs")

    op.drop_index(
        "ix_survey_instance_options_subject_id",
        table_name="survey_instance_options",
    )
    op.drop_constraint(
        "fk_survey_instance_options_subject",
        "survey_instance_options",
        type_="foreignkey",
    )
    op.drop_column(
        "survey_instance_options",
        "subject_id",
    )
