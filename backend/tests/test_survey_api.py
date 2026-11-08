import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

import main
from models import (
    Subject,
    Teacher,
    TeacherClassAccess,
    TeachingAssignment,
    User,
    Class,
    SurveyInstance,
    Administrator,
    SurveyResponse,
    SurveyResponseOption,
    StudentEnrollment,
)


@pytest.fixture
def survey_api_client(db_session):
    """HTTP-клиент API, работающий с тестовой транзакцией."""

    def override_get_db():
        yield db_session

    main.app.dependency_overrides[main.get_db] = override_get_db

    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)


@pytest.fixture
def student_auth_headers(survey_test_data):
    """JWT-заголовок тестового ученика."""

    user = survey_test_data["user"]
    token, _ = main.create_access_token(user)

    return {"Authorization": f"Bearer {token}"}


def test_student_can_access_own_survey(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
):
    data = survey_test_data
    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    # Получаем доступные классы.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/survey-classes",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": class_code,
            "name": data["class"].name,
        }
    ]

    # Получаем даты опросов своего класса.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "survey_date": survey_date,
            "status": "open",
        }
    ]

    # Получаем статистику опроса.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    assert response.status_code == 200

    statistics = response.json()

    assert statistics["class_code"] == class_code
    assert statistics["class_name"] == data["class"].name
    assert statistics["survey_date"] == survey_date
    assert len(statistics["questions"]) == 3

    # В статистике нет идентификаторов учеников и отдельных ответов.
    assert "student_id" not in str(statistics)
    assert "response_id" not in str(statistics)


@pytest.fixture
def teacher_auth_headers(survey_test_data, db_session):
    """Создаёт учителя с назначением на тестовый класс."""
    data = survey_test_data

    user = User(
        sferum_id="999999998",
        full_name="Тестовый учитель",
    )
    db_session.add(user)
    db_session.flush()

    teacher = Teacher(
        user_id=user.id,
        school_id=data["school"].id,
    )
    db_session.add(teacher)
    db_session.flush()

    subject = Subject(
        school_id=data["school"].id,
        name="Тестовый предмет",
    )
    db_session.add(subject)
    db_session.flush()

    assignment = TeachingAssignment(
        school_id=data["school"].id,
        teacher_id=teacher.id,
        class_id=data["class"].id,
        subject_id=subject.id,
        academic_year_id=data["academic_year"].id,
        subgroup=0,
    )
    db_session.add(assignment)
    db_session.flush()

    teacher_access = TeacherClassAccess(
        teacher_id=teacher.id,
        class_id=data["class"].id,
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
    )
    db_session.add(teacher_access)
    db_session.flush()

    token, _ = main.create_access_token(user)

    return {"Authorization": f"Bearer {token}"}


def test_teacher_can_access_assigned_class_survey(
    survey_test_data,
    survey_api_client,
    teacher_auth_headers,
):
    data = survey_test_data
    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/survey-classes",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": class_code,
            "name": data["class"].name,
        }
    ]

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["class_code"] == class_code
    assert len(response.json()["questions"]) == 3


def test_teacher_with_class_access_without_assignment_can_access_survey(
    survey_test_data,
    survey_api_client,
    db_session,
):
    data = survey_test_data

    # Создаём пользователя.
    user = User(
        sferum_id="999999997",
        full_name="Учитель только с доступом к классу",
    )
    db_session.add(user)
    db_session.flush()

    # Создаём учителя без предметных назначений.
    teacher = Teacher(
        user_id=user.id,
        school_id=data["school"].id,
    )
    db_session.add(teacher)
    db_session.flush()

    # Выдаём доступ только к одному классу.
    access = TeacherClassAccess(
        teacher_id=teacher.id,
        class_id=data["class"].id,
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
    )
    db_session.add(access)
    db_session.flush()

    token, _ = main.create_access_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    # Класс должен отображаться в списке доступных опросов.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/survey-classes",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": class_code,
            "name": data["class"].name,
        }
    ]

    # Учитель должен получить агрегированную статистику.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["class_code"] == class_code
    assert len(response.json()["questions"]) == 3


def test_teacher_cannot_access_unassigned_class(
    survey_test_data,
    survey_api_client,
    teacher_auth_headers,
    db_session,
):
    data = survey_test_data

    # Создаём второй класс в той же школе и учебном году.
    other_class = Class(
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
        code="other",
        name="Другой класс",
    )
    db_session.add(other_class)
    db_session.flush()

    # Создаём для него опрос.
    other_survey = SurveyInstance(
        class_id=other_class.id,
        survey_date=data["instance"].survey_date,
        opens_at=data["instance"].opens_at,
        closes_at=data["instance"].closes_at,
        status="open",
    )
    db_session.add(other_survey)
    db_session.flush()

    school_id = data["school"].id
    survey_date = other_survey.survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/other/surveys/{survey_date}",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "У вас нет доступа к этому опросу"}


@pytest.fixture
def admin_auth_headers(survey_test_data, db_session):
    """JWT-заголовок тестового администратора."""
    data = survey_test_data

    user = User(
        sferum_id="999999997",
        full_name="Тестовый администратор",
    )
    db_session.add(user)
    db_session.flush()

    administrator = Administrator(
        user_id=user.id,
        school_id=data["school"].id,
        position="Директор",
    )
    db_session.add(administrator)
    db_session.flush()

    token, _ = main.create_access_token(user)

    return {"Authorization": f"Bearer {token}"}


def test_administrator_can_access_all_school_surveys(
    survey_test_data,
    survey_api_client,
    admin_auth_headers,
    db_session,
):
    data = survey_test_data

    # Создаём второй класс и опрос для него.
    other_class = Class(
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
        code="other",
        name="Другой класс",
    )
    db_session.add(other_class)
    db_session.flush()

    other_survey = SurveyInstance(
        class_id=other_class.id,
        survey_date=data["instance"].survey_date,
        opens_at=data["instance"].opens_at,
        closes_at=data["instance"].closes_at,
        status="open",
    )
    db_session.add(other_survey)
    db_session.flush()

    school_id = data["school"].id

    # Администратор должен видеть оба класса.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/survey-classes",
        headers=admin_auth_headers,
    )

    assert response.status_code == 200

    classes = response.json()
    assert len(classes) == 2
    assert {item["code"] for item in classes} == {"test", "other"}

    # Администратор должен иметь доступ к статистике первого класса.
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/test/surveys/{survey_date}",
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["class_code"] == "test"


def test_unauthorized_user_cannot_access_surveys(
    survey_test_data,
    survey_api_client,
):
    data = survey_test_data

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    urls = [
        f"/api/schools/{school_id}/survey-classes",
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
    ]

    for url in urls:
        response = survey_api_client.get(url)

        assert response.status_code == 401


def test_statistics_count_only_submitted_responses(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
    db_session,
):
    data = survey_test_data
    questions = data["questions"]
    options = data["options"]

    # Создаём отправленный ответ на первый вопрос.
    submitted_response = SurveyResponse(
        instance_question_id=questions[0].id,
        student_id=data["student"].id,
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(submitted_response)
    db_session.flush()

    # Выбираем первый вариант ответа.
    db_session.add(
        SurveyResponseOption(
            response_id=submitted_response.id,
            option_id=options[0][0].id,
            instance_question_id=questions[0].id,
        )
    )

    # Создаём черновик второго вопроса без отправки.
    draft_response = SurveyResponse(
        instance_question_id=questions[1].id,
        student_id=data["student"].id,
        status="draft",
    )
    db_session.add(draft_response)
    db_session.flush()

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    assert response.status_code == 200

    statistics = response.json()["questions"]

    # Первый вопрос: один отправленный ответ.
    first_question = statistics[0]
    assert first_question["respondents_count"] == 1

    selected_option = next(
        option
        for option in first_question["options"]
        if option["title"] == options[0][0].title
    )

    assert selected_option["responses_count"] == 1
    assert selected_option["percentage"] == 100.0

    # Второй вопрос: черновик не должен учитываться.
    second_question = statistics[1]
    assert second_question["respondents_count"] == 0
    assert all(option["responses_count"] == 0 for option in second_question["options"])


def test_student_with_ended_enrollment_cannot_access_survey(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
    db_session,
):
    data = survey_test_data

    # Завершаем зачисление до даты проведения опроса.
    data["enrollment"].end_date = data["instance"].survey_date - timedelta(days=1)
    db_session.flush()

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    # Класс больше не должен отображаться ученику.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/survey-classes",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == []

    # Доступ к статистике должен быть запрещён.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    assert response.status_code == 403


def test_statistics_show_zero_values_without_responses(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
):
    data = survey_test_data

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    assert response.status_code == 200

    statistics = response.json()["questions"]

    for question in statistics:
        assert question["respondents_count"] == 0

        for option in question["options"]:
            assert option["responses_count"] == 0
            assert option["percentage"] == 0.0


def test_multiple_choice_percentages_can_exceed_100(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
    db_session,
):
    data = survey_test_data

    question = data["questions"][1]
    selected_options = data["options"][1][:2]

    # Ученик отправил ответ, выбрав два варианта.
    submitted_response = SurveyResponse(
        instance_question_id=question.id,
        student_id=data["student"].id,
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(submitted_response)
    db_session.flush()

    for option in selected_options:
        db_session.add(
            SurveyResponseOption(
                response_id=submitted_response.id,
                option_id=option.id,
                instance_question_id=question.id,
            )
        )

    db_session.flush()

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    assert response.status_code == 200

    question_statistics = response.json()["questions"][1]

    assert question_statistics["respondents_count"] == 1

    selected_titles = {option.title for option in selected_options}

    for option in question_statistics["options"]:
        if option["title"] in selected_titles:
            assert option["responses_count"] == 1
            assert option["percentage"] == 100.0
        else:
            assert option["responses_count"] == 0
            assert option["percentage"] == 0.0

    # Два выбранных варианта по 100% дают в сумме 200%.
    total_percentage = sum(
        option["percentage"] for option in question_statistics["options"]
    )
    assert total_percentage == 200.0


def test_student_access_uses_historical_enrollment_not_current_class(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
    db_session,
):
    data = survey_test_data

    # Создаём новый класс, в который ученик переведён сейчас.
    new_class = Class(
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
        code="new",
        name="Новый класс",
    )
    db_session.add(new_class)
    db_session.flush()

    # Меняем текущий класс ученика.
    # Историческое зачисление в старый класс при этом сохраняется.
    data["student"].class_id = new_class.id
    db_session.flush()

    school_id = data["school"].id
    old_class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{old_class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    # Доступ должен определяться историческим зачислением.
    assert response.status_code == 200
    assert response.json()["class_code"] == old_class_code


def test_student_with_multiple_matching_enrollments_is_denied(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
    db_session,
):
    data = survey_test_data
    survey_date = data["instance"].survey_date

    # Завершаем первое зачисление после даты опроса.
    # Оно продолжает действовать на дату опроса.
    data["enrollment"].end_date = survey_date + timedelta(days=10)
    db_session.flush()

    # Создаём второй класс.
    other_class = Class(
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
        code="other",
        name="Другой класс",
    )
    db_session.add(other_class)
    db_session.flush()

    # Создаём второе зачисление, также действующее на дату опроса.
    second_enrollment = StudentEnrollment(
        student_id=data["student"].id,
        class_id=other_class.id,
        start_date=survey_date - timedelta(days=10),
        end_date=survey_date + timedelta(days=20),
    )
    db_session.add(second_enrollment)
    db_session.flush()

    school_id = data["school"].id
    class_code = data["class"].code

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date.isoformat()}",
        headers=student_auth_headers,
    )

    # Два зачисления действуют на дату опроса — доступ запрещён.
    assert response.status_code == 403


def test_expired_open_survey_is_closed_in_api(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
):
    data = survey_test_data
    instance = data["instance"]

    instance.opens_at = datetime.now(timezone.utc) - timedelta(days=2)
    instance.closes_at = datetime.now(timezone.utc) - timedelta(days=1)

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = instance.survey_date.isoformat()

    # Проверяем статус в списке опросов.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "closed"

    # Проверяем статус в статистике.
    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_future_open_survey_remains_open(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
):
    data = survey_test_data
    instance = data["instance"]

    instance.opens_at = datetime.now(timezone.utc) + timedelta(days=1)
    instance.closes_at = datetime.now(timezone.utc) + timedelta(days=2)

    school_id = data["school"].id
    class_code = data["class"].code

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "open"


def test_open_survey_with_invalid_school_timezone_is_closed_in_api(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
):
    data = survey_test_data

    data["school"].timezone = "Invalid/Timezone"

    school_id = data["school"].id
    class_code = data["class"].code

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "closed"


def test_open_survey_without_school_timezone_is_closed_in_api(
    survey_test_data,
    survey_api_client,
    student_auth_headers,
):
    data = survey_test_data

    data["school"].timezone = None

    school_id = data["school"].id
    class_code = data["class"].code

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        headers=student_auth_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "closed"


def test_teacher_with_assignment_without_class_access_can_access_surveys(
    survey_test_data,
    survey_api_client,
    db_session,
):
    data = survey_test_data

    user = User(
        sferum_id="999999996",
        full_name="Учитель только с назначением",
    )
    db_session.add(user)
    db_session.flush()

    teacher = Teacher(
        user_id=user.id,
        school_id=data["school"].id,
    )
    db_session.add(teacher)
    db_session.flush()

    subject = Subject(
        school_id=data["school"].id,
        name="Тестовый предмет",
    )
    db_session.add(subject)
    db_session.flush()

    assignment = TeachingAssignment(
        school_id=data["school"].id,
        teacher_id=teacher.id,
        class_id=data["class"].id,
        subject_id=subject.id,
        academic_year_id=data["academic_year"].id,
        subgroup=0,
    )
    db_session.add(assignment)
    db_session.flush()

    # TeacherClassAccess намеренно не создаём.

    token, _ = main.create_access_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    school_id = data["school"].id
    class_code = data["class"].code
    survey_date = data["instance"].survey_date.isoformat()

    response = survey_api_client.get(
        f"/api/schools/{school_id}/survey-classes",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": class_code,
            "name": data["class"].name,
        }
    ]

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1

    response = survey_api_client.get(
        f"/api/schools/{school_id}/classes/{class_code}/surveys/{survey_date}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["class_code"] == class_code
