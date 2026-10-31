"""add active academic year

Revision ID: 6a554c99e02b
Revises: 06adbbd0444c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a554c99e02b"
down_revision: Union[str, Sequence[str], None] = "06adbbd0444c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Существующие учебные годы изначально неактивны.
    op.add_column(
        "academic_years",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Активируем текущий учебный год каждой школы,
    # если на эту школу пока не назначен активный год.
    op.execute(
        sa.text("""
            UPDATE academic_years AS ay
            SET is_active = TRUE
            WHERE ay.id = (
                SELECT candidate.id
                FROM academic_years AS candidate
                WHERE candidate.school_id = ay.school_id
                  AND candidate.start_date <= CURRENT_DATE
                  AND candidate.end_date >= CURRENT_DATE
                ORDER BY candidate.start_date DESC, candidate.id DESC
                LIMIT 1
            )
        """)
    )

    # Гарантируем не более одного активного года на школу.
    op.create_index(
        "uq_academic_years_one_active_per_school",
        "academic_years",
        ["school_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )

    # Значение по умолчанию нужно только для миграции
    # существующих записей. Новые годы задаются явно.
    op.alter_column(
        "academic_years",
        "is_active",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_academic_years_one_active_per_school",
        table_name="academic_years",
    )
    op.drop_column("academic_years", "is_active")
