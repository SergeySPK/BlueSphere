"""Convert class IDs and add student enrollments.

Revision ID: 1a64714f55a9
Revises: 6a554c99e02b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1a64714f55a9"
down_revision: Union[str, Sequence[str], None] = "6a554c99e02b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CLASS_FK_TABLES = (
    "students",
    "teaching_assignments",
    "surveys",
    "survey_drafts",
    "recommendations",
)


def upgrade() -> None:
    # 1. Сохраняем старые строковые идентификаторы классов
    # в отдельном поле code.
    op.add_column(
        "classes",
        sa.Column("code", sa.String(length=20), nullable=True),
    )

    op.execute("""
        UPDATE classes
        SET code = id
    """)

    # 2. Создаём новые числовые идентификаторы.
    op.add_column(
        "classes",
        sa.Column(
            "new_id",
            sa.Integer(),
            sa.Identity(),
            nullable=False,
        ),
    )

    # 3. Добавляем временные числовые FK во все связанные таблицы.
    for table in CLASS_FK_TABLES:
        op.add_column(
            table,
            sa.Column("new_class_id", sa.Integer(), nullable=True),
        )

        op.execute(sa.text(f"""
            UPDATE {table} AS related
            SET new_class_id = classes.new_id
            FROM classes
            WHERE related.class_id = classes.code
        """))

        # Проверяем, что все старые связи перенесены.
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM {table}
                    WHERE new_class_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Не удалось перенести class_id в таблице {table}';
                END IF;
            END
            $$;
        """))

        op.alter_column(
            table,
            "new_class_id",
            nullable=False,
        )

    # 4. Удаляем ограничения, которые ссылаются на старые ID.
    for table in CLASS_FK_TABLES:
        op.drop_constraint(
            f"{table}_class_id_fkey",
            table,
            type_="foreignkey",
        )

    # Составная уникальность назначений зависит от старого class_id.
    op.drop_constraint(
        "teaching_assignments_teacher_id_class_id_subject_id_academi_key",
        "teaching_assignments",
        type_="unique",
    )

    # 5. Удаляем старые строковые FK и переименовываем новые.
    for table in CLASS_FK_TABLES:
        op.drop_column(table, "class_id")
        op.alter_column(
            table,
            "new_class_id",
            new_column_name="class_id",
        )

    # 6. Заменяем первичный ключ classes.
    op.drop_constraint(
        "classes_pkey",
        "classes",
        type_="primary",
    )

    op.drop_column("classes", "id")

    op.alter_column(
        "classes",
        "new_id",
        new_column_name="id",
    )

    op.create_primary_key(
        "classes_pkey",
        "classes",
        ["id"],
    )

    op.alter_column(
        "classes",
        "code",
        nullable=False,
    )

    # 7. Восстанавливаем уникальность классов
    # в пределах школы и учебного года.
    op.create_unique_constraint(
        "uq_classes_school_year_code",
        "classes",
        ["school_id", "academic_year_id", "code"],
    )

    # 8. Восстанавливаем внешние ключи.
    for table in CLASS_FK_TABLES:
        op.create_foreign_key(
            f"{table}_class_id_fkey",
            table,
            "classes",
            ["class_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # 9. Восстанавливаем составную уникальность назначений.
    op.create_unique_constraint(
        "teaching_assignments_teacher_id_class_id_subject_id_academi_key",
        "teaching_assignments",
        [
            "teacher_id",
            "class_id",
            "subject_id",
            "academic_year_id",
            "subgroup",
        ],
    )

    # 10. Создаём историю зачислений.
    op.create_table(
        "student_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_student_enrollments_dates",
        ),
    )

    op.create_index(
        "uq_student_enrollments_active_student",
        "student_enrollments",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("end_date IS NULL"),
    )

    # 11. Создаём первоначальное зачисление существующих учеников.
    op.execute("""
        INSERT INTO student_enrollments (
            student_id,
            class_id,
            start_date,
            end_date
        )
        SELECT
            students.id,
            students.class_id,
            DATE '2026-09-01',
            NULL
        FROM students
    """)



def downgrade() -> None:
    # 1. Проверяем, что история зачислений не содержит переводов.
    # Откат к старой структуре не поддерживает историю перемещений.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM student_enrollments AS enrollment
                LEFT JOIN students
                    ON students.id = enrollment.student_id
                WHERE
                    students.id IS NULL
                    OR enrollment.end_date IS NOT NULL
                    OR enrollment.start_date <> DATE '2026-09-01'
                    OR enrollment.class_id <> students.class_id
            )
            OR EXISTS (
                SELECT 1
                FROM students
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM student_enrollments AS enrollment
                    WHERE
                        enrollment.student_id = students.id
                        AND enrollment.class_id = students.class_id
                        AND enrollment.start_date = DATE '2026-09-01'
                        AND enrollment.end_date IS NULL
                )
            ) THEN
                RAISE EXCEPTION
                    'Откат невозможен: история зачислений содержит изменения. '
                    'Сначала необходимо сохранить историю отдельно.';
            END IF;
        END
        $$;
    """)

    # 2. Удаляем таблицу истории зачислений.
    op.drop_index(
        "uq_student_enrollments_active_student",
        table_name="student_enrollments",
    )
    op.drop_table("student_enrollments")

    # 3. Удаляем ограничения, зависящие от числовых class_id.
    for table in CLASS_FK_TABLES:
        op.drop_constraint(
            f"{table}_class_id_fkey",
            table,
            type_="foreignkey",
        )

    op.drop_constraint(
        "teaching_assignments_teacher_id_class_id_subject_id_academi_key",
        "teaching_assignments",
        type_="unique",
    )

    # 4. Восстанавливаем старые строковые коды как временные FK.
    for table in CLASS_FK_TABLES:
        op.add_column(
            table,
            sa.Column("old_class_id", sa.String(length=20), nullable=True),
        )

        op.execute(sa.text(f"""
            UPDATE {table} AS related
            SET old_class_id = classes.code
            FROM classes
            WHERE related.class_id = classes.id
        """))

        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM {table}
                    WHERE old_class_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Не удалось восстановить class_id в таблице {table}';
                END IF;
            END
            $$;
        """))

        op.alter_column(
            table,
            "old_class_id",
            nullable=False,
        )

    # 5. Удаляем числовые FK и возвращаем строковые.
    for table in CLASS_FK_TABLES:
        op.drop_column(table, "class_id")
        op.alter_column(
            table,
            "old_class_id",
            new_column_name="class_id",
        )

    # 6. Возвращаем старый строковый первичный ключ classes.
    op.drop_constraint(
        "uq_classes_school_year_code",
        "classes",
        type_="unique",
    )

    op.drop_constraint(
        "classes_pkey",
        "classes",
        type_="primary",
    )

    op.add_column(
        "classes",
        sa.Column("old_id", sa.String(length=20), nullable=True),
    )

    op.execute("""
        UPDATE classes
        SET old_id = code
    """)

    op.alter_column(
        "classes",
        "old_id",
        nullable=False,
    )

    op.drop_column("classes", "id")
    op.drop_column("classes", "code")

    op.alter_column(
        "classes",
        "old_id",
        new_column_name="id",
    )

    op.create_primary_key(
        "classes_pkey",
        "classes",
        ["id"],
    )

    # 7. Восстанавливаем старые внешние ключи.
    for table in CLASS_FK_TABLES:
        op.create_foreign_key(
            f"{table}_class_id_fkey",
            table,
            "classes",
            ["class_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # 8. Восстанавливаем составную уникальность назначений.
    op.create_unique_constraint(
        "teaching_assignments_teacher_id_class_id_subject_id_academi_key",
        "teaching_assignments",
        [
            "teacher_id",
            "class_id",
            "subject_id",
            "academic_year_id",
            "subgroup",
        ],
    )
