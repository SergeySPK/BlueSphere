import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

@pytest.fixture
def db_connection():
    """
    Подключение к отдельной тестовой PostgreSQL БД.

    Все изменения автоматически отменяются после теста.
    """

    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        pytest.fail(
            "Не задан TEST_DATABASE_URL. "
            "Запускайте интеграционные тесты "
            "только с отдельной тестовой БД."
        )

    url = make_url(database_url)

    # Защита от случайного подключения к рабочей базе.
    if url.database != "bluesphere_restore_test":
        pytest.fail(
            "Интеграционные тесты разрешены только "
            "для базы bluesphere_restore_test."
        )

    if url.get_backend_name() != "postgresql":
        pytest.fail("Для тестов требуется PostgreSQL.")

    if url.query.get("host") != "/var/run/postgresql":
        pytest.fail(
            "Разрешено подключение только к локальному "
            "PostgreSQL через Unix-сокет."
        )

    engine = create_engine(database_url)

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def create_test_student(db_connection):
    """Создаёт отдельного ученика со школой, учебным годом и классом."""

    school_id = db_connection.execute(
        text("""
            INSERT INTO schools (
                region, city, address, short_name, full_name
            )
            VALUES (
                'Тестовый регион',
                'Тестовый город',
                'Тестовый адрес',
                'Школа для тестов',
                'Тестовая общеобразовательная школа'
            )
            RETURNING id
        """)
    ).scalar_one()

    academic_year_id = db_connection.execute(
        text("""
            INSERT INTO academic_years (
                school_id, name, start_date, end_date, is_active
            )
            VALUES (
                :school_id,
                '2026–2027',
                '2026-09-01',
                '2027-08-31',
                TRUE
            )
            RETURNING id
        """),
        {"school_id": school_id},
    ).scalar_one()

    class_id = db_connection.execute(
        text("""
            INSERT INTO classes (
                school_id, academic_year_id, name, code
            )
            VALUES (
                :school_id,
                :academic_year_id,
                'Тестовый класс',
                'TEST'
            )
            RETURNING id
        """),
        {
            "school_id": school_id,
            "academic_year_id": academic_year_id,
        },
    ).scalar_one()

    user_id = db_connection.execute(
        text("""
            INSERT INTO users (sferum_id, full_name)
            VALUES (:sferum_id, 'Тестовый ученик')
            RETURNING id
        """),
        {"sferum_id": f"test-{school_id}"},
    ).scalar_one()

    student_id = db_connection.execute(
        text("""
            INSERT INTO students (user_id, class_id)
            VALUES (:user_id, :class_id)
            RETURNING id
        """),
        {
            "user_id": user_id,
            "class_id": class_id,
        },
    ).scalar_one()

    return student_id, class_id


def create_test_assignment_context(db_connection):
    """Создаёт школу, учебный год, класс, учителя и предмет."""

    school_id = db_connection.execute(
        text("""
            INSERT INTO schools (
                region, city, address, short_name, full_name
            )
            VALUES (
                'Тестовый регион',
                'Тестовый город',
                'Тестовый адрес',
                'Школа для назначений',
                'Тестовая школа для учебных назначений'
            )
            RETURNING id
        """)
    ).scalar_one()

    academic_year_id = db_connection.execute(
        text("""
            INSERT INTO academic_years (
                school_id, name, start_date, end_date, is_active
            )
            VALUES (
                :school_id,
                '2026–2027',
                '2026-09-01',
                '2027-08-31',
                TRUE
            )
            RETURNING id
        """),
        {"school_id": school_id},
    ).scalar_one()

    class_id = db_connection.execute(
        text("""
            INSERT INTO classes (
                school_id, academic_year_id, name, code
            )
            VALUES (
                :school_id,
                :academic_year_id,
                'Тестовый класс',
                'TEST'
            )
            RETURNING id
        """),
        {
            "school_id": school_id,
            "academic_year_id": academic_year_id,
        },
    ).scalar_one()

    user_id = db_connection.execute(
        text("""
            INSERT INTO users (sferum_id, full_name)
            VALUES (:sferum_id, 'Тестовый учитель')
            RETURNING id
        """),
        {"sferum_id": f"teacher-test-{school_id}"},
    ).scalar_one()

    teacher_id = db_connection.execute(
        text("""
            INSERT INTO teachers (user_id, school_id)
            VALUES (:user_id, :school_id)
            RETURNING id
        """),
        {
            "user_id": user_id,
            "school_id": school_id,
        },
    ).scalar_one()

    subject_id = db_connection.execute(
        text("""
            INSERT INTO subjects (school_id, name)
            VALUES (:school_id, 'Тестовый предмет')
            RETURNING id
        """),
        {"school_id": school_id},
    ).scalar_one()

    return school_id, academic_year_id, class_id, teacher_id, subject_id


def test_school_cannot_have_two_active_academic_years(db_connection):
    # Создаём отдельную школу для теста.
    school_id = db_connection.execute(
        text("""
            INSERT INTO schools (
                region,
                city,
                address,
                short_name,
                full_name
            )
            VALUES (
                'Тестовый регион',
                'Тестовый город',
                'Тестовая улица, 1',
                'Тестовая школа',
                'Тестовая общеобразовательная школа'
            )
            RETURNING id
        """)
    ).scalar_one()

    # Добавляем первый активный учебный год.
    db_connection.execute(
        text("""
            INSERT INTO academic_years (
                school_id,
                name,
                start_date,
                end_date,
                is_active
            )
            VALUES (
                :school_id,
                '2026–2027',
                '2026-09-01',
                '2027-08-31',
                TRUE
            )
        """),
        {"school_id": school_id},
    )

    # Второй активный учебный год для той же школы
    # должен вызвать ошибку ограничения уникальности.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO academic_years (
                        school_id,
                        name,
                        start_date,
                        end_date,
                        is_active
                    )
                    VALUES (
                        :school_id,
                        '2027–2028',
                        '2027-09-01',
                        '2028-08-31',
                        TRUE
                    )
                """),
                {"school_id": school_id},
            )


def test_student_cannot_have_two_active_enrollments(db_connection):
    student_id, class_id = create_test_student(db_connection)

    # Первое активное зачисление.
    db_connection.execute(
        text("""
            INSERT INTO student_enrollments (
                student_id, class_id, start_date
            )
            VALUES (
                :student_id, :class_id, '2026-09-01'
            )
        """),
        {
            "student_id": student_id,
            "class_id": class_id,
        },
    )

    # Второе активное зачисление должно быть запрещено.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO student_enrollments (
                        student_id, class_id, start_date
                    )
                    VALUES (
                        :student_id, :class_id, '2026-10-01'
                    )
                """),
                {
                    "student_id": student_id,
                    "class_id": class_id,
                },
            )


def test_enrollment_end_date_cannot_be_before_start_date(db_connection):
    student_id, class_id = create_test_student(db_connection)

    # Дата окончания раньше даты начала.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO student_enrollments (
                        student_id,
                        class_id,
                        start_date,
                        end_date
                    )
                    VALUES (
                        :student_id,
                        :class_id,
                        '2026-10-01',
                        '2026-09-01'
                    )
                """),
                {
                    "student_id": student_id,
                    "class_id": class_id,
                },
            )


def test_duplicate_teaching_assignment_is_rejected(db_connection):
    (
        school_id,
        academic_year_id,
        class_id,
        teacher_id,
        subject_id,
    ) = create_test_assignment_context(db_connection)

    assignment = {
        "school_id": school_id,
        "academic_year_id": academic_year_id,
        "class_id": class_id,
        "teacher_id": teacher_id,
        "subject_id": subject_id,
        "subgroup": 0,
    }

    # Первое назначение должно успешно создаться.
    db_connection.execute(
        text("""
            INSERT INTO teaching_assignments (
                school_id,
                academic_year_id,
                class_id,
                teacher_id,
                subject_id,
                subgroup
            )
            VALUES (
                :school_id,
                :academic_year_id,
                :class_id,
                :teacher_id,
                :subject_id,
                :subgroup
            )
        """),
        assignment,
    )

    # Повтор того же назначения должен вызвать ошибку.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO teaching_assignments (
                        school_id,
                        academic_year_id,
                        class_id,
                        teacher_id,
                        subject_id,
                        subgroup
                    )
                    VALUES (
                        :school_id,
                        :academic_year_id,
                        :class_id,
                        :teacher_id,
                        :subject_id,
                        :subgroup
                    )
                """),
                assignment,
            )


def test_teaching_assignment_rejects_invalid_subgroup(db_connection):
    (
        school_id,
        academic_year_id,
        class_id,
        teacher_id,
        subject_id,
    ) = create_test_assignment_context(db_connection)

    # Значение 3 не входит в разрешённый диапазон 0, 1, 2.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO teaching_assignments (
                        school_id,
                        academic_year_id,
                        class_id,
                        teacher_id,
                        subject_id,
                        subgroup
                    )
                    VALUES (
                        :school_id,
                        :academic_year_id,
                        :class_id,
                        :teacher_id,
                        :subject_id,
                        3
                    )
                """),
                {
                    "school_id": school_id,
                    "academic_year_id": academic_year_id,
                    "class_id": class_id,
                    "teacher_id": teacher_id,
                    "subject_id": subject_id,
                },
            )


def test_teaching_assignment_rejects_teacher_from_another_school(
    db_connection,
):
    (
        school_a,
        year_a,
        class_a,
        teacher_a,
        subject_a,
    ) = create_test_assignment_context(db_connection)

    (
        school_b,
        year_b,
        class_b,
        teacher_b,
        subject_b,
    ) = create_test_assignment_context(db_connection)

    # Используем школу, класс и предмет школы A,
    # но учителя школы B.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO teaching_assignments (
                        school_id,
                        academic_year_id,
                        class_id,
                        teacher_id,
                        subject_id,
                        subgroup
                    )
                    VALUES (
                        :school_id,
                        :academic_year_id,
                        :class_id,
                        :teacher_id,
                        :subject_id,
                        0
                    )
                """),
                {
                    "school_id": school_a,
                    "academic_year_id": year_a,
                    "class_id": class_a,
                    "teacher_id": teacher_b,
                    "subject_id": subject_a,
                },
            )


def test_teaching_assignment_rejects_subject_from_another_school(
    db_connection,
):
    (
        school_a,
        year_a,
        class_a,
        teacher_a,
        subject_a,
    ) = create_test_assignment_context(db_connection)

    (
        school_b,
        year_b,
        class_b,
        teacher_b,
        subject_b,
    ) = create_test_assignment_context(db_connection)

    # Школа, класс и учитель принадлежат школе A,
    # но предмет взят из школы B.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO teaching_assignments (
                        school_id,
                        academic_year_id,
                        class_id,
                        teacher_id,
                        subject_id,
                        subgroup
                    )
                    VALUES (
                        :school_id,
                        :academic_year_id,
                        :class_id,
                        :teacher_id,
                        :subject_id,
                        0
                    )
                """),
                {
                    "school_id": school_a,
                    "academic_year_id": year_a,
                    "class_id": class_a,
                    "teacher_id": teacher_a,
                    "subject_id": subject_b,
                },
            )


def test_teaching_assignment_rejects_class_from_another_academic_year(
    db_connection,
):
    (
        school_a,
        year_a,
        class_a,
        teacher_a,
        subject_a,
    ) = create_test_assignment_context(db_connection)

    (
        school_b,
        year_b,
        class_b,
        teacher_b,
        subject_b,
    ) = create_test_assignment_context(db_connection)

    # Класс, учитель и предмет относятся к школе A,
    # но учебный год указан от школы B.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO teaching_assignments (
                        school_id,
                        academic_year_id,
                        class_id,
                        teacher_id,
                        subject_id,
                        subgroup
                    )
                    VALUES (
                        :school_id,
                        :academic_year_id,
                        :class_id,
                        :teacher_id,
                        :subject_id,
                        0
                    )
                """),
                {
                    "school_id": school_a,
                    "academic_year_id": year_b,
                    "class_id": class_a,
                    "teacher_id": teacher_a,
                    "subject_id": subject_a,
                },
            )


def test_class_rejects_academic_year_from_another_school(db_connection):
    (
        school_a,
        year_a,
        class_a,
        teacher_a,
        subject_a,
    ) = create_test_assignment_context(db_connection)

    (
        school_b,
        year_b,
        class_b,
        teacher_b,
        subject_b,
    ) = create_test_assignment_context(db_connection)

    # Школа A не должна использовать учебный год школы B.
    with pytest.raises(IntegrityError):
        with db_connection.begin_nested():
            db_connection.execute(
                text("""
                    INSERT INTO classes (
                        school_id,
                        academic_year_id,
                        name,
                        code
                    )
                    VALUES (
                        :school_id,
                        :academic_year_id,
                        'Некорректный тестовый класс',
                        'INVALID'
                    )
                """),
                {
                    "school_id": school_a,
                    "academic_year_id": year_b,
                },
            )