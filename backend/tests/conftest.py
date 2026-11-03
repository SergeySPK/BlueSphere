import os

import pytest
from sqlalchemy.engine import make_url

# Проверяем настройки до импорта main и database.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    raise RuntimeError(
        "Не задан TEST_DATABASE_URL. "
        "Тесты должны запускаться с отдельной тестовой БД."
    )

test_url = make_url(TEST_DATABASE_URL)

if test_url.database != "bluesphere_restore_test":
    raise RuntimeError("Тесты разрешены только для базы bluesphere_restore_test.")

if test_url.get_backend_name() != "postgresql":
    raise RuntimeError("Для тестов требуется PostgreSQL.")

if test_url.query.get("host") != "/var/run/postgresql":
    raise RuntimeError(
        "Тесты должны подключаться к локальному PostgreSQL " "через Unix-сокет."
    )

# Переключаем приложение на тестовую БД до импорта database.py.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture
def db_session():
    """Сессия тестовой БД с автоматическим откатом изменений."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(TEST_DATABASE_URL)

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            session = Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            )

            try:
                yield session
            finally:
                session.close()
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.fixture
def survey_test_data(db_session):
    """Создаёт изолированный набор данных для тестирования опросов."""
    from datetime import date, datetime, timedelta, timezone

    from models import (
        School,
        AcademicYear,
        Class,
        User,
        Student,
        StudentEnrollment,
        SurveyInstance,
        SurveyInstanceQuestion,
        SurveyInstanceOption,
    )

    now = datetime.now(timezone.utc)
    survey_date = date.today()

    school = School(
        region="Тестовый регион",
        city="Тестовый город",
        address="Тестовый адрес",
        short_name="Тестовая школа",
        full_name="Тестовая общеобразовательная школа",
        timezone="Asia/Yekaterinburg",
    )
    db_session.add(school)
    db_session.flush()

    academic_year = AcademicYear(
        school_id=school.id,
        name="Тестовый учебный год",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
        is_active=True,
    )
    db_session.add(academic_year)
    db_session.flush()

    school_class = Class(
        school_id=school.id,
        academic_year_id=academic_year.id,
        code="test",
        name="Тестовый класс",
    )
    db_session.add(school_class)
    db_session.flush()

    user = User(
        sferum_id="999999999",
        full_name="Тестовый ученик",
    )
    db_session.add(user)
    db_session.flush()

    student = Student(
        user_id=user.id,
        class_id=school_class.id,
    )
    db_session.add(student)
    db_session.flush()

    enrollment = StudentEnrollment(
        student_id=student.id,
        class_id=school_class.id,
        start_date=survey_date - timedelta(days=30),
        end_date=None,
    )
    db_session.add(enrollment)
    db_session.flush()

    instance = SurveyInstance(
        class_id=school_class.id,
        survey_date=survey_date,
        opens_at=now - timedelta(hours=1),
        closes_at=now + timedelta(hours=24),
        status="open",
    )
    db_session.add(instance)
    db_session.flush()

    question_definitions = [
        {
            "title": "Общая оценка состояния",
            "answer_type": "single",
            "min_answer": 1,
            "max_answer": 1,
            "options": ["Отлично", "Хорошо", "Удовлетворительно"],
        },
        {
            "title": "Наиболее тревожные предметы",
            "answer_type": "multiple",
            "min_answer": 1,
            "max_answer": 2,
            "options": ["Математика", "История", "Никакой"],
        },
        {
            "title": "Наиболее лёгкие предметы",
            "answer_type": "multiple",
            "min_answer": 1,
            "max_answer": 2,
            "options": ["Математика", "История", "Никакой"],
        },
    ]

    questions = []
    options = []

    for question_order, definition in enumerate(question_definitions, start=1):
        question = SurveyInstanceQuestion(
            instance_id=instance.id,
            title=definition["title"],
            bot_text=definition["title"],
            answer_type=definition["answer_type"],
            min_answer=definition["min_answer"],
            max_answer=definition["max_answer"],
            sort_order=question_order,
        )
        db_session.add(question)
        db_session.flush()

        question_options = []

        for option_order, title in enumerate(definition["options"], start=1):
            option = SurveyInstanceOption(
                instance_question_id=question.id,
                title=title,
                sort_order=option_order,
                is_exclusive=(title == "Никакой"),
            )
            db_session.add(option)
            db_session.flush()

            question_options.append(option)

        questions.append(question)
        options.append(question_options)

    db_session.flush()

    return {
        "school": school,
        "academic_year": academic_year,
        "class": school_class,
        "user": user,
        "student": student,
        "enrollment": enrollment,
        "instance": instance,
        "questions": questions,
        "options": options,
        "max_user_id": int(user.sferum_id),
    }


@pytest.fixture
def survey_service_session(db_session, monkeypatch):
    """Направляет собственные сессии сервиса в общую тестовую транзакцию."""
    from sqlalchemy.orm import Session
    import survey_service

    def test_session_factory():
        return Session(
            bind=db_session.connection(),
            join_transaction_mode="create_savepoint",
        )

    monkeypatch.setattr(
        survey_service,
        "SessionLocal",
        test_session_factory,
    )
