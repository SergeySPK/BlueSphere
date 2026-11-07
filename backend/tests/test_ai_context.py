from datetime import date, datetime, timedelta, timezone

import pytest

from ai_context import collect_ai_analysis_input
from models import (
    AcademicYear,
    Class,
    School,
    Schedule,
    Student,
    StudentEnrollment,
    Subject,
    SurveyInstance,
    SurveyInstanceOption,
    SurveyInstanceQuestion,
    SurveyResponse,
    SurveyResponseOption,
    Teacher,
    TeachingAssignment,
    User,
)


@pytest.fixture
def ai_context_data(db_session):
    """Минимальный набор данных для проверки сбора AI-контекста."""

    school = School(
        region="Тестовый регион",
        city="Тестовый город",
        address="Тестовый адрес",
        short_name="AI Test",
        full_name="Школа для тестов AI",
        timezone="Europe/Moscow",
    )
    db_session.add(school)
    db_session.flush()

    academic_year = AcademicYear(
        school_id=school.id,
        name="2026–2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
        is_active=True,
    )
    db_session.add(academic_year)
    db_session.flush()

    school_class = Class(
        school_id=school.id,
        academic_year_id=academic_year.id,
        code="ai-test",
        name="Тестовый класс",
    )
    db_session.add(school_class)
    db_session.flush()

    teacher_user = User(
        sferum_id="ai-teacher-001",
        full_name="Тестовый учитель",
    )
    db_session.add(teacher_user)
    db_session.flush()

    teacher = Teacher(
        user_id=teacher_user.id,
        school_id=school.id,
    )
    db_session.add(teacher)
    db_session.flush()

    subject = Subject(
        school_id=school.id,
        name="Математика",
    )
    db_session.add(subject)
    db_session.flush()

    assignment = TeachingAssignment(
        school_id=school.id,
        teacher_id=teacher.id,
        class_id=school_class.id,
        subject_id=subject.id,
        academic_year_id=academic_year.id,
        subgroup=0,
    )
    db_session.add(assignment)
    db_session.flush()

    target_date = date(2026, 11, 10)

    schedule = Schedule(
        assignment_id=assignment.id,
        date=target_date,
        lesson_number=1,
        room="101",
        lesson_type="Контрольная работа",
    )
    db_session.add(schedule)
    db_session.flush()

    # Опрос старше 21 дня, но в пределах учебного года.
    survey_date = date(2026, 9, 15)

    closed_survey = SurveyInstance(
        class_id=school_class.id,
        survey_date=survey_date,
        opens_at=datetime(2026, 9, 15, 7, tzinfo=timezone.utc),
        closes_at=datetime(2026, 9, 15, 15, tzinfo=timezone.utc),
        status="closed",
    )
    db_session.add(closed_survey)
    db_session.flush()

    question = SurveyInstanceQuestion(
        instance_id=closed_survey.id,
        title="Какие предметы вызывают тревогу?",
        bot_text="Какие предметы вызывают тревогу?",
        answer_type="multiple",
        min_answer=1,
        max_answer=2,
        sort_order=1,
    )
    db_session.add(question)
    db_session.flush()

    options = [
        SurveyInstanceOption(
            instance_question_id=question.id,
            title="Математика",
            sort_order=1,
            is_exclusive=False,
        ),
        SurveyInstanceOption(
            instance_question_id=question.id,
            title="История",
            sort_order=2,
            is_exclusive=False,
        ),
        SurveyInstanceOption(
            instance_question_id=question.id,
            title="Никакой",
            sort_order=3,
            is_exclusive=True,
        ),
    ]
    db_session.add_all(options)
    db_session.flush()

    # Создаём четырёх учеников:
    # 1. Зачисление закончилось в день опроса — должен учитываться.
    # 2. Действующее зачисление — должен учитываться.
    # 3. Зачисление началось после опроса — не должен учитываться.
    # 4. Действующее зачисление, но ответ остался draft.

    students = []

    enrollment_definitions = [
        ("ai-student-001", "Ученик с завершённым зачислением",
         date(2026, 9, 1), survey_date),
        ("ai-student-002", "Ученик с активным зачислением",
         date(2026, 9, 1), None),
        ("ai-student-003", "Ученик, зачисленный позднее",
         date(2026, 9, 16), None),
        ("ai-student-004", "Ученик с черновиком ответа",
         date(2026, 9, 1), None),
    ]

    for sferum_id, full_name, start_date, end_date in enrollment_definitions:
        user = User(
            sferum_id=sferum_id,
            full_name=full_name,
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
            start_date=start_date,
            end_date=end_date,
        )
        db_session.add(enrollment)
        db_session.flush()

        students.append(student)

    # Два подходящих отправленных ответа.
    response_1 = SurveyResponse(
        instance_question_id=question.id,
        student_id=students[0].id,
        status="submitted",
        submitted_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
    )
    response_2 = SurveyResponse(
        instance_question_id=question.id,
        student_id=students[1].id,
        status="submitted",
        submitted_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
    )

    # Отправленный ответ ученика, который ещё не был зачислен.
    response_3 = SurveyResponse(
        instance_question_id=question.id,
        student_id=students[2].id,
        status="submitted",
        submitted_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
    )

    # Черновик не должен попасть в статистику.
    response_4 = SurveyResponse(
        instance_question_id=question.id,
        student_id=students[3].id,
        status="draft",
        submitted_at=None,
    )

    db_session.add_all([
        response_1,
        response_2,
        response_3,
        response_4,
    ])
    db_session.flush()

    # Ученик 1 выбрал математику и историю.
    # Ученик 2 выбрал математику.
    # Ученик 3 выбрал "Никакой", но его зачисление ещё не действовало.
    # Ученик 4 выбрал историю, но ответ остался черновиком.

    selections = [
        (response_1, options[0]),
        (response_1, options[1]),
        (response_2, options[0]),
        (response_3, options[2]),
        (response_4, options[1]),
    ]

    db_session.add_all([
        SurveyResponseOption(
            response_id=response.id,
            option_id=option.id,
            instance_question_id=question.id,
        )
        for response, option in selections
    ])

    # Открытый опрос не должен передаваться AI.
    open_survey = SurveyInstance(
        class_id=school_class.id,
        survey_date=date(2026, 9, 16),
        opens_at=datetime(2026, 9, 16, 7, tzinfo=timezone.utc),
        closes_at=datetime(2026, 11, 21, 15, tzinfo=timezone.utc),
        status="open",
    )

    # Отменённый опрос также не должен передаваться AI.
    cancelled_survey = SurveyInstance(
        class_id=school_class.id,
        survey_date=date(2026, 9, 17),
        opens_at=datetime(2026, 9, 17, 7, tzinfo=timezone.utc),
        closes_at=datetime(2026, 9, 17, 15, tzinfo=timezone.utc),
        status="cancelled",
    )

    db_session.add_all([open_survey, cancelled_survey])
    db_session.flush()

    return {
        "school": school,
        "academic_year": academic_year,
        "class": school_class,
        "teacher": teacher,
        "subject": subject,
        "assignment": assignment,
        "schedule": schedule,
        "target_date": target_date,
        "survey_date": survey_date,
        "closed_survey": closed_survey,
        "open_survey": open_survey,
        "cancelled_survey": cancelled_survey,
        "question": question,
        "options": options,
        "students": students,
    }


def test_collects_schedule_and_assignments(db_session, ai_context_data):
    data = ai_context_data

    context = collect_ai_analysis_input(
        db_session,
        school_id=data["school"].id,
        class_id=data["class"].id,
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 22),
        target_date=data["target_date"],
        now=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )

    assert context.school_id == data["school"].id
    assert context.academic_year_id == data["academic_year"].id
    assert context.class_id == data["class"].id
    assert context.target_date == data["target_date"]
    assert context.school_timezone == "Europe/Moscow"

    assert len(context.assignments) == 1
    assignment = context.assignments[0]

    assert assignment.assignment_id == data["assignment"].id
    assert assignment.teacher_id == data["teacher"].id
    assert assignment.subject_id == data["subject"].id
    assert assignment.subject_name == "Математика"

    assert len(context.lessons) == 1
    lesson = context.lessons[0]

    assert lesson.schedule_id == data["schedule"].id
    assert lesson.date == data["target_date"]
    assert lesson.lesson_type == "Контрольная работа"


def test_uses_only_closed_surveys_before_target_date(
    db_session,
    ai_context_data,
):
    data = ai_context_data

    context = collect_ai_analysis_input(
        db_session,
        school_id=data["school"].id,
        class_id=data["class"].id,
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 22),
        target_date=data["target_date"],
        now=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )

    assert len(context.surveys) == 1

    survey = context.surveys[0]

    # Проверяем, что опрос старше 21 дня всё равно учитывается.
    assert survey.survey_date == data["survey_date"]
    assert survey.status == "closed"

    assert survey.survey_date < data["target_date"]
    assert survey.survey_date < data["target_date"] - timedelta(days=21)


def test_aggregates_only_eligible_submitted_responses(
    db_session,
    ai_context_data,
):
    data = ai_context_data

    context = collect_ai_analysis_input(
        db_session,
        school_id=data["school"].id,
        class_id=data["class"].id,
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 22),
        target_date=data["target_date"],
        now=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )

    question = context.surveys[0].questions[0]

    # Учитываются два ученика:
    # один с завершившимся в день опроса зачислением,
    # второй с действующим зачислением.
    assert question.respondents_count == 2

    options = {
        option.title: option
        for option in question.options
    }

    assert options["Математика"].responses_count == 2
    assert options["Математика"].percentage == 100.0

    assert options["История"].responses_count == 1
    assert options["История"].percentage == 50.0

    assert options["Никакой"].responses_count == 0
    assert options["Никакой"].percentage == 0.0


def test_ai_context_contains_no_personal_student_data(
    db_session,
    ai_context_data,
):
    data = ai_context_data

    context = collect_ai_analysis_input(
        db_session,
        school_id=data["school"].id,
        class_id=data["class"].id,
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 22),
        target_date=data["target_date"],
        now=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )

    serialized = context.model_dump_json()

    forbidden_values = [
        "student_id",
        "user_id",
        "full_name",
        "sferum_id",
        *[
            student.id
            for student in data["students"]
        ],
    ]

    for value in forbidden_values:
        assert str(value) not in serialized


def test_rejects_target_date_without_lessons(
    db_session,
    ai_context_data,
):
    data = ai_context_data
    empty_date = date(2026, 11, 11)

    with pytest.raises(ValueError, match="нет уроков"):
        collect_ai_analysis_input(
            db_session,
            school_id=data["school"].id,
            class_id=data["class"].id,
            period_start=date(2026, 11, 2),
            period_end=date(2026, 11, 22),
            target_date=empty_date,
            now=datetime(2026, 11, 20, tzinfo=timezone.utc),
        )
