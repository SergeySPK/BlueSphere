"""add school consistency constraints

Revision ID: 00ada0c7cd4e
Revises: 1a64714f55a9
"""

from alembic import op
import sqlalchemy as sa


revision = "00ada0c7cd4e"
down_revision = "1a64714f55a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Добавляем уникальные ограничения для составных внешних ключей.
    op.create_unique_constraint(
        "uq_academic_years_school_id",
        "academic_years",
        ["school_id", "id"],
    )

    op.create_unique_constraint(
        "uq_classes_id_school_year",
        "classes",
        ["id", "school_id", "academic_year_id"],
    )

    op.create_unique_constraint(
        "uq_subjects_id_school",
        "subjects",
        ["id", "school_id"],
    )

    op.create_unique_constraint(
        "uq_teachers_id_school",
        "teachers",
        ["id", "school_id"],
    )

    # 2. Проверяем принадлежность учебного года школе класса.
    op.drop_constraint(
        "classes_academic_year_id_fkey",
        "classes",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_classes_school_academic_year",
        "classes",
        "academic_years",
        ["school_id", "academic_year_id"],
        ["school_id", "id"],
        ondelete="CASCADE",
    )

    # 3. Добавляем school_id в назначения преподавателей.
    # Сначала разрешаем NULL, поскольку таблица уже содержит записи.
    op.add_column(
        "teaching_assignments",
        sa.Column("school_id", sa.Integer(), nullable=True),
    )

    # Заполняем school_id на основании школы соответствующего класса.
    op.execute(
        """
        UPDATE teaching_assignments AS ta
        SET school_id = c.school_id
        FROM classes AS c
        WHERE ta.class_id = c.id
        """
    )

    # После заполнения запрещаем NULL.
    op.alter_column(
        "teaching_assignments",
        "school_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # 4. Удаляем старые внешние ключи.
    op.drop_constraint(
        "teaching_assignments_teacher_id_fkey",
        "teaching_assignments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "teaching_assignments_class_id_fkey",
        "teaching_assignments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "teaching_assignments_subject_id_fkey",
        "teaching_assignments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "teaching_assignments_academic_year_id_fkey",
        "teaching_assignments",
        type_="foreignkey",
    )

    # 5. Добавляем составные внешние ключи.
    # Преподаватель должен принадлежать той же школе.
    op.create_foreign_key(
        "fk_assignments_teacher_school",
        "teaching_assignments",
        "teachers",
        ["teacher_id", "school_id"],
        ["id", "school_id"],
        ondelete="CASCADE",
    )

    # Класс и учебный год должны соответствовать друг другу.
    op.create_foreign_key(
        "fk_assignments_class_school_year",
        "teaching_assignments",
        "classes",
        ["class_id", "school_id", "academic_year_id"],
        ["id", "school_id", "academic_year_id"],
        ondelete="CASCADE",
    )

    # Предмет должен принадлежать той же школе.
    op.create_foreign_key(
        "fk_assignments_subject_school",
        "teaching_assignments",
        "subjects",
        ["subject_id", "school_id"],
        ["id", "school_id"],
        ondelete="CASCADE",
    )

    # Школа назначения должна существовать.
    op.create_foreign_key(
        "fk_assignments_school",
        "teaching_assignments",
        "schools",
        ["school_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 1. Удаляем новые внешние ключи.
    op.drop_constraint(
        "fk_assignments_school",
        "teaching_assignments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_assignments_subject_school",
        "teaching_assignments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_assignments_class_school_year",
        "teaching_assignments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_assignments_teacher_school",
        "teaching_assignments",
        type_="foreignkey",
    )

    # 2. Возвращаем прежние внешние ключи.
    op.create_foreign_key(
        "teaching_assignments_teacher_id_fkey",
        "teaching_assignments",
        "teachers",
        ["teacher_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "teaching_assignments_class_id_fkey",
        "teaching_assignments",
        "classes",
        ["class_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "teaching_assignments_subject_id_fkey",
        "teaching_assignments",
        "subjects",
        ["subject_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "teaching_assignments_academic_year_id_fkey",
        "teaching_assignments",
        "academic_years",
        ["academic_year_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 3. Удаляем добавленный столбец.
    op.drop_column("teaching_assignments", "school_id")

    # 4. Возвращаем прежний внешний ключ класса на учебный год.
    op.drop_constraint(
        "fk_classes_school_academic_year",
        "classes",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "classes_academic_year_id_fkey",
        "classes",
        "academic_years",
        ["academic_year_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 5. Удаляем уникальные ограничения.
    op.drop_constraint(
        "uq_teachers_id_school",
        "teachers",
        type_="unique",
    )

    op.drop_constraint(
        "uq_subjects_id_school",
        "subjects",
        type_="unique",
    )

    op.drop_constraint(
        "uq_classes_id_school_year",
        "classes",
        type_="unique",
    )

    op.drop_constraint(
        "uq_academic_years_school_id",
        "academic_years",
        type_="unique",
    )