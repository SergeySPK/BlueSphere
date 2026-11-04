import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import survey_service
from models import (
    School,
    AcademicYear,
    Class,
    User,
    Teacher,
    TeacherClassAccess,
    Subject,
    TeachingAssignment,
    Schedule,
    Student,
    StudentEnrollment,
    SurveyInstance,
    SurveyInstanceQuestion,
    SurveyInstanceOption,
)

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

    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    closes_at = datetime(
        survey_date.year,
        survey_date.month,
        survey_date.day,
        18,
        0,
        tzinfo=school_timezone,
    ) + timedelta(days=1)

    instance = SurveyInstance(
        class_id=school_class.id,
        survey_date=survey_date,
        opens_at=now - timedelta(hours=1),
        closes_at=closes_at,
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


@pytest.fixture
def teacher_transfer_data(db_session):
    """Создаёт данные для тестирования переноса классов учителю."""

    school = School(
        region="Тестовый регион",
        city="Тестовый город",
        address="Тестовый адрес",
        short_name="Школа переноса",
        full_name="Тестовая школа для переноса",
        timezone="Asia/Yekaterinburg",
    )
    db_session.add(school)
    db_session.flush()

    active_year = AcademicYear(
        school_id=school.id,
        name="2026–2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
        is_active=True,
    )

    old_year = AcademicYear(
        school_id=school.id,
        name="2025–2026",
        start_date=date(2025, 9, 1),
        end_date=date(2026, 8, 31),
        is_active=False,
    )

    db_session.add_all([active_year, old_year])
    db_session.flush()

    class_5a = Class(
        school_id=school.id,
        academic_year_id=active_year.id,
        code="5a",
        name="5А",
    )

    class_5b = Class(
        school_id=school.id,
        academic_year_id=active_year.id,
        code="5b",
        name="5Б",
    )

    class_6a = Class(
        school_id=school.id,
        academic_year_id=active_year.id,
        code="6a",
        name="6А",
    )

    old_class_5a = Class(
        school_id=school.id,
        academic_year_id=old_year.id,
        code="5a",
        name="5А",
    )

    db_session.add_all([
        class_5a,
        class_5b,
        class_6a,
        old_class_5a,
    ])
    db_session.flush()

    old_user = User(
        sferum_id="990000001",
        full_name="Старый учитель",
    )

    new_user = User(
        sferum_id="990000002",
        full_name="Новый учитель",
    )

    other_user = User(
        sferum_id="990000003",
        full_name="Другой учитель",
    )

    db_session.add_all([old_user, new_user, other_user])
    db_session.flush()

    old_teacher = Teacher(
        user_id=old_user.id,
        school_id=school.id,
    )

    new_teacher = Teacher(
        user_id=new_user.id,
        school_id=school.id,
    )

    other_teacher = Teacher(
        user_id=other_user.id,
        school_id=school.id,
    )

    db_session.add_all([
        old_teacher,
        new_teacher,
        other_teacher,
    ])
    db_session.flush()

    subject_math = Subject(
        school_id=school.id,
        name="Математика",
    )

    subject_russian = Subject(
        school_id=school.id,
        name="Русский язык",
    )

    db_session.add_all([subject_math, subject_russian])
    db_session.flush()

    assignments = [
        TeachingAssignment(
            school_id=school.id,
            teacher_id=old_teacher.id,
            class_id=class_5a.id,
            subject_id=subject_math.id,
            academic_year_id=active_year.id,
            subgroup=0,
        ),
        TeachingAssignment(
            school_id=school.id,
            teacher_id=old_teacher.id,
            class_id=class_5a.id,
            subject_id=subject_russian.id,
            academic_year_id=active_year.id,
            subgroup=0,
        ),
        TeachingAssignment(
            school_id=school.id,
            teacher_id=old_teacher.id,
            class_id=class_5b.id,
            subject_id=subject_math.id,
            academic_year_id=active_year.id,
            subgroup=0,
        ),
        TeachingAssignment(
            school_id=school.id,
            teacher_id=other_teacher.id,
            class_id=class_6a.id,
            subject_id=subject_math.id,
            academic_year_id=active_year.id,
            subgroup=0,
        ),
        TeachingAssignment(
            school_id=school.id,
            teacher_id=old_teacher.id,
            class_id=old_class_5a.id,
            subject_id=subject_math.id,
            academic_year_id=old_year.id,
            subgroup=0,
        ),
    ]

    db_session.add_all(assignments)
    db_session.flush()

    # Старый учитель имеет доступ к выбранным и постороннему классу.
    # Другой учитель также имеет доступ к одному из выбранных классов.
    accesses = [
        TeacherClassAccess(
            teacher_id=old_teacher.id,
            class_id=class_5a.id,
            school_id=school.id,
            academic_year_id=active_year.id,
        ),
        TeacherClassAccess(
            teacher_id=old_teacher.id,
            class_id=class_5b.id,
            school_id=school.id,
            academic_year_id=active_year.id,
        ),
        TeacherClassAccess(
            teacher_id=old_teacher.id,
            class_id=class_6a.id,
            school_id=school.id,
            academic_year_id=active_year.id,
        ),
        TeacherClassAccess(
            teacher_id=other_teacher.id,
            class_id=class_5a.id,
            school_id=school.id,
            academic_year_id=active_year.id,
        ),
        TeacherClassAccess(
            teacher_id=old_teacher.id,
            class_id=old_class_5a.id,
            school_id=school.id,
            academic_year_id=old_year.id,
        ),
    ]

    db_session.add_all(accesses)
    db_session.flush()

    # Расписание связано с назначением, которое будет перенесено.
    schedule = Schedule(
        assignment_id=assignments[0].id,
        date=date(2026, 11, 4),
        lesson_number=1,
        room="101",
        lesson_type="Урок",
    )

    db_session.add(schedule)
    db_session.flush()

    return {
        "school": school,
        "active_year": active_year,
        "old_year": old_year,
        "class_5a": class_5a,
        "class_5b": class_5b,
        "class_6a": class_6a,
        "old_class_5a": old_class_5a,
        "old_teacher": old_teacher,
        "new_teacher": new_teacher,
        "other_teacher": other_teacher,
        "assignments": assignments,
        "schedule": schedule,
    }
