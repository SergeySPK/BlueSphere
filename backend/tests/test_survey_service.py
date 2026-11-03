import pytest

from survey_instance_service import (
    close_expired_survey_instances,
    create_survey_notifications,
    create_survey_instances_for_date,
)

from sqlalchemy import select
from types import SimpleNamespace
from models import (
    SurveyResponse,
    SurveyResponseOption,
    StudentEnrollment,
    Class,
    SurveyInstance,
    SurveyNotification,
    SurveyQuestion,
)
import survey_service
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone, date

def test_get_available_survey(survey_test_data, survey_service_session):
    data = survey_test_data

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is not None
    assert result["instance_id"] == data["instance"].id
    assert result["class_id"] == data["class"].id
    assert result["questions_count"] == 3


def test_get_next_question_returns_first_question(
    survey_test_data,
    survey_service_session,
):
    data = survey_test_data

    result = survey_service.get_next_question(
        data["max_user_id"],
        data["instance"].id,
    )

    assert result is not None
    assert result["question_id"] == data["questions"][0].id
    assert result["answer_type"] == "single"


def test_save_single_answer(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    question = data["questions"][0]
    option = data["options"][0][0]

    result = survey_service.save_single_answer(
        data["max_user_id"],
        data["instance"].id,
        question.id,
        option.id,
    )

    assert result == "submitted"

    response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert response is not None
    assert response.status == "submitted"
    assert response.submitted_at is not None

    selected_option = db_session.scalar(
        select(SurveyResponseOption).where(
            SurveyResponseOption.response_id == response.id,
        )
    )

    assert selected_option is not None
    assert selected_option.option_id == option.id


def _submit_first_question(data):
    """Завершает первый вопрос, чтобы перейти ко второму."""
    return survey_service.save_single_answer(
        data["max_user_id"],
        data["instance"].id,
        data["questions"][0].id,
        data["options"][0][0].id,
    )


def _selected_option_ids(db_session, response):
    return set(
        db_session.scalars(
            select(SurveyResponseOption.option_id).where(
                SurveyResponseOption.response_id == response.id
            )
        ).all()
    )


def test_multiple_answer_saves_draft(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    _submit_first_question(data)

    question = data["questions"][1]
    first_option = data["options"][1][0]
    second_option = data["options"][1][1]

    result1 = survey_service.toggle_multiple_answer(
        data["max_user_id"],
        data["instance"].id,
        question.id,
        first_option.id,
    )
    result2 = survey_service.toggle_multiple_answer(
        data["max_user_id"],
        data["instance"].id,
        question.id,
        second_option.id,
    )

    assert result1 == "saved"
    assert result2 == "saved"

    response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert response is not None
    assert response.status == "draft"
    assert response.submitted_at is None
    assert _selected_option_ids(db_session, response) == {
        first_option.id,
        second_option.id,
    }


def test_multiple_answer_rejects_third_regular_option(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    _submit_first_question(data)

    question = data["questions"][1]
    options = data["options"][1]

    for option in options[:2]:
        result = survey_service.toggle_multiple_answer(
            data["max_user_id"],
            data["instance"].id,
            question.id,
            option.id,
        )
        assert result == "saved"

    result = survey_service.toggle_multiple_answer(
        data["max_user_id"],
        data["instance"].id,
        question.id,
        options[2].id,
    )

    assert result == "saved"

    # Третий вариант здесь эксклюзивный, поэтому он заменяет обычные.
    response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )
    assert _selected_option_ids(db_session, response) == {options[2].id}

    # После снятия эксклюзивного варианта можно выбрать два обычных.
    survey_service.toggle_multiple_answer(
        data["max_user_id"],
        data["instance"].id,
        question.id,
        options[2].id,
    )

    for option in options[:2]:
        assert (
            survey_service.toggle_multiple_answer(
                data["max_user_id"],
                data["instance"].id,
                question.id,
                option.id,
            )
            == "saved"
        )

    result = survey_service.toggle_multiple_answer(
        data["max_user_id"],
        data["instance"].id,
        question.id,
        options[0].id,
    )

    assert result == "saved"

    assert _selected_option_ids(db_session, response) == {options[1].id}


def test_exclusive_option_replaces_regular_options(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    _submit_first_question(data)

    question = data["questions"][1]
    regular_option = data["options"][1][0]
    exclusive_option = data["options"][1][2]

    assert (
        survey_service.toggle_multiple_answer(
            data["max_user_id"],
            data["instance"].id,
            question.id,
            regular_option.id,
        )
        == "saved"
    )

    assert (
        survey_service.toggle_multiple_answer(
            data["max_user_id"],
            data["instance"].id,
            question.id,
            exclusive_option.id,
        )
        == "saved"
    )

    response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert _selected_option_ids(db_session, response) == {exclusive_option.id}

    assert (
        survey_service.toggle_multiple_answer(
            data["max_user_id"],
            data["instance"].id,
            question.id,
            regular_option.id,
        )
        == "saved"
    )

    assert _selected_option_ids(db_session, response) == {regular_option.id}


def test_submit_multiple_answer_is_idempotent(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    _submit_first_question(data)

    question = data["questions"][1]
    option = data["options"][1][0]

    assert (
        survey_service.toggle_multiple_answer(
            data["max_user_id"],
            data["instance"].id,
            question.id,
            option.id,
        )
        == "saved"
    )

    result = survey_service.submit_multiple_answer(
        data["max_user_id"], data["instance"].id, question.id
    )
    assert result == "submitted"

    assert (
        survey_service.submit_multiple_answer(
            data["max_user_id"], data["instance"].id, question.id
        )
        == "already_submitted"
    )

    assert (
        survey_service.toggle_multiple_answer(
            data["max_user_id"],
            data["instance"].id,
            question.id,
            data["options"][1][1].id,
        )
        == "already_submitted"
    )

    response = db_session.scalar(
        select(SurveyResponse).where(
            SurveyResponse.instance_question_id == question.id,
            SurveyResponse.student_id == data["student"].id,
        )
    )

    assert response.status == "submitted"
    assert _selected_option_ids(db_session, response) == {option.id}


def test_questions_are_completed_in_order(
    survey_test_data,
    survey_service_session,
):
    data = survey_test_data
    instance_id = data["instance"].id
    user_id = data["max_user_id"]

    # Изначально доступен первый вопрос.
    result = survey_service.get_next_question(user_id, instance_id)
    assert result["question_id"] == data["questions"][0].id

    # Отправляем ответ на первый вопрос.
    assert (
        survey_service.save_single_answer(
            user_id,
            instance_id,
            data["questions"][0].id,
            data["options"][0][0].id,
        )
        == "submitted"
    )

    # Теперь доступен второй вопрос.
    result = survey_service.get_next_question(user_id, instance_id)
    assert result["question_id"] == data["questions"][1].id

    # Создаём черновик второго вопроса.
    assert (
        survey_service.toggle_multiple_answer(
            user_id,
            instance_id,
            data["questions"][1].id,
            data["options"][1][0].id,
        )
        == "saved"
    )

    # Пока ответ не отправлен, следующий вопрос недоступен.
    result = survey_service.get_next_question(user_id, instance_id)
    assert result["question_id"] == data["questions"][1].id

    # Отправляем ответ на второй вопрос.
    assert (
        survey_service.submit_multiple_answer(
            user_id,
            instance_id,
            data["questions"][1].id,
        )
        == "submitted"
    )

    # Теперь доступен третий вопрос.
    result = survey_service.get_next_question(user_id, instance_id)
    assert result["question_id"] == data["questions"][2].id


def test_survey_is_unavailable_before_opening(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].opens_at = now + timedelta(hours=1)
    data["instance"].closes_at = now + timedelta(hours=2)
    db_session.flush()

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is None


def test_survey_is_unavailable_after_closing(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].opens_at = now - timedelta(days=2)
    data["instance"].closes_at = now - timedelta(days=1)
    db_session.flush()

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is None


def test_survey_is_unavailable_without_school_timezone(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    data["school"].timezone = None
    db_session.flush()

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is None


def test_survey_is_unavailable_with_invalid_school_timezone(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    data["school"].timezone = "Invalid/Timezone"
    db_session.flush()

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is None


def test_survey_unavailable_without_matching_enrollment(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data

    # Зачисление начинается после даты опроса.
    data["enrollment"].start_date = data["instance"].survey_date + timedelta(days=1)
    db_session.flush()

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is None


def test_survey_unavailable_with_multiple_matching_enrollments(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    survey_date = data["instance"].survey_date

    # Завершаем первую запись после даты опроса.
    data["enrollment"].end_date = survey_date + timedelta(days=10)

    # Добавляем вторую запись с пересекающимся периодом.
    second_enrollment = StudentEnrollment(
        student_id=data["student"].id,
        class_id=data["class"].id,
        start_date=survey_date - timedelta(days=10),
        end_date=survey_date + timedelta(days=20),
    )
    db_session.add(second_enrollment)
    db_session.flush()

    result = survey_service.get_available_survey(data["max_user_id"])

    assert result is None


def test_no_next_question_after_all_questions_completed(
    survey_test_data,
    survey_service_session,
):
    data = survey_test_data
    user_id = data["max_user_id"]
    instance_id = data["instance"].id

    # Первый вопрос — одиночный ответ.
    assert (
        survey_service.save_single_answer(
            user_id,
            instance_id,
            data["questions"][0].id,
            data["options"][0][0].id,
        )
        == "submitted"
    )

    # Второй и третий вопросы — множественный выбор.
    for question_index in (1, 2):
        question = data["questions"][question_index]
        option = data["options"][question_index][0]

        assert (
            survey_service.toggle_multiple_answer(
                user_id,
                instance_id,
                question.id,
                option.id,
            )
            == "saved"
        )

        assert (
            survey_service.submit_multiple_answer(
                user_id,
                instance_id,
                question.id,
            )
            == "submitted"
        )

    # После завершения всех вопросов продолжения нет.
    result = survey_service.get_next_question(user_id, instance_id)

    assert result is None


def test_is_survey_open_inside_interval():
    opens_at = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc)
    closes_at = datetime(2026, 11, 1, 12, 59, tzinfo=timezone.utc)
    now = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)

    instance = SimpleNamespace(
        opens_at=opens_at,
        closes_at=closes_at,
    )

    assert survey_service._is_survey_open(instance, "Asia/Yekaterinburg", now) is True


def test_is_survey_open_at_interval_boundaries():
    opens_at = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc)
    closes_at = datetime(2026, 11, 1, 12, 59, tzinfo=timezone.utc)

    instance = SimpleNamespace(
        opens_at=opens_at,
        closes_at=closes_at,
    )

    # Ровно в момент открытия.
    assert (
        survey_service._is_survey_open(instance, "Asia/Yekaterinburg", opens_at) is True
    )

    # Ровно в момент закрытия.
    assert (
        survey_service._is_survey_open(instance, "Asia/Yekaterinburg", closes_at)
        is True
    )


def test_is_survey_open_outside_interval():
    opens_at = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc)
    closes_at = datetime(2026, 11, 1, 12, 59, tzinfo=timezone.utc)

    instance = SimpleNamespace(
        opens_at=opens_at,
        closes_at=closes_at,
    )

    before_opening = opens_at - timedelta(seconds=1)
    after_closing = closes_at + timedelta(seconds=1)

    assert (
        survey_service._is_survey_open(instance, "Asia/Yekaterinburg", before_opening)
        is False
    )

    assert (
        survey_service._is_survey_open(instance, "Asia/Yekaterinburg", after_closing)
        is False
    )


def test_is_survey_open_rejects_naive_datetimes():
    aware_date = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc)
    naive_date = datetime(2026, 10, 31, 13, 0)

    instance_with_naive_opening = SimpleNamespace(
        opens_at=naive_date,
        closes_at=aware_date + timedelta(hours=24),
    )

    instance_with_naive_closing = SimpleNamespace(
        opens_at=aware_date,
        closes_at=naive_date + timedelta(hours=24),
    )

    now = aware_date + timedelta(hours=1)

    assert (
        survey_service._is_survey_open(
            instance_with_naive_opening, "Asia/Yekaterinburg", now
        )
        is False
    )

    assert (
        survey_service._is_survey_open(
            instance_with_naive_closing, "Asia/Yekaterinburg", now
        )
        is False
    )


def test_is_survey_open_rejects_naive_now():
    opens_at = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc)

    instance = SimpleNamespace(
        opens_at=opens_at,
        closes_at=opens_at + timedelta(hours=24),
    )

    naive_now = datetime(2026, 10, 31, 14, 0)

    assert (
        survey_service._is_survey_open(instance, "Asia/Yekaterinburg", naive_now)
        is False
    )


def test_get_next_question_returns_none_before_opening(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].opens_at = now + timedelta(hours=1)
    data["instance"].closes_at = now + timedelta(hours=2)
    db_session.flush()

    result = survey_service.get_next_question(
        data["max_user_id"],
        data["instance"].id,
    )

    assert result is None


def test_get_next_question_returns_none_after_closing(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    now = datetime.now(timezone.utc)

    data["instance"].opens_at = now - timedelta(days=2)
    data["instance"].closes_at = now - timedelta(days=1)
    db_session.flush()

    result = survey_service.get_next_question(
        data["max_user_id"],
        data["instance"].id,
    )

    assert result is None


def test_get_next_question_returns_none_without_school_timezone(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    data["school"].timezone = None
    db_session.flush()

    result = survey_service.get_next_question(
        data["max_user_id"],
        data["instance"].id,
    )

    assert result is None


def test_get_next_question_returns_none_with_invalid_school_timezone(
    survey_test_data,
    survey_service_session,
    db_session,
):
    data = survey_test_data
    data["school"].timezone = "Invalid/Timezone"
    db_session.flush()

    result = survey_service.get_next_question(
        data["max_user_id"],
        data["instance"].id,
    )

    assert result is None


def test_close_expired_survey_instance(
    survey_test_data,
    db_session,
):
    data = survey_test_data
    instance = data["instance"]

    now = datetime.now(timezone.utc)
    instance.closes_at = now - timedelta(minutes=1)
    db_session.flush()

    closed_count = close_expired_survey_instances(
        db_session,
        now=now,
    )

    db_session.refresh(instance)

    assert closed_count == 1
    assert instance.status == "closed"


def test_future_survey_instance_remains_open(
    survey_test_data,
    db_session,
):
    data = survey_test_data
    instance = data["instance"]

    now = datetime.now(timezone.utc)
    instance.closes_at = now + timedelta(hours=1)
    db_session.flush()

    closed_count = close_expired_survey_instances(
        db_session,
        now=now,
    )

    db_session.refresh(instance)

    assert closed_count == 0
    assert instance.status == "open"


@pytest.mark.parametrize("status", ["closed", "cancelled"])
def test_close_expired_does_not_change_non_open_status(
    survey_test_data,
    db_session,
    status,
):
    data = survey_test_data
    instance = data["instance"]

    now = datetime.now(timezone.utc)
    instance.status = status
    instance.closes_at = now - timedelta(minutes=1)
    db_session.flush()

    closed_count = close_expired_survey_instances(
        db_session,
        now=now,
    )

    db_session.refresh(instance)

    assert closed_count == 0
    assert instance.status == status


def test_close_expired_rejects_naive_now(
    survey_test_data,
    db_session,
):
    now = datetime.now()

    with pytest.raises(ValueError, match="часовой пояс"):
        close_expired_survey_instances(
            db_session,
            now=now,
        )


def test_create_survey_notifications_for_enrolled_student(
    survey_test_data,
    db_session,
):
    data = survey_test_data

    result = create_survey_notifications(
        db_session,
        data["instance"],
    )

    assert result == {"created": 1, "skipped": 0}

    notification = db_session.scalar(
        select(SurveyNotification).where(
            SurveyNotification.instance_id == data["instance"].id,
            SurveyNotification.student_id == data["student"].id,
        )
    )

    assert notification is not None
    assert notification.status == "pending"
    assert notification.attempt_count == 0


def test_create_survey_notifications_ignores_expired_enrollment(
    survey_test_data,
    db_session,
):
    data = survey_test_data

    another_class = Class(
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
        code="previous",
        name="Предыдущий класс",
    )
    db_session.add(another_class)
    db_session.flush()

    previous_enrollment = StudentEnrollment(
        student_id=data["student"].id,
        class_id=another_class.id,
        start_date=data["instance"].survey_date - timedelta(days=60),
        end_date=data["instance"].survey_date - timedelta(days=1),
    )
    db_session.add(previous_enrollment)
    db_session.flush()

    result = create_survey_notifications(
        db_session,
        data["instance"],
    )

    assert result == {"created": 1, "skipped": 0}


def test_create_survey_notifications_uses_historical_enrollment(
    survey_test_data,
    db_session,
):
    data = survey_test_data

    another_class = Class(
        school_id=data["school"].id,
        academic_year_id=data["academic_year"].id,
        code="current",
        name="Текущий класс",
    )
    db_session.add(another_class)
    db_session.flush()

    # Текущий класс ученика отличается от класса опроса.
    # Единственная историческая запись зачисления относится
    # к классу опроса, поэтому уведомление должно создаваться.
    data["student"].class_id = another_class.id
    db_session.flush()

    result = create_survey_notifications(
        db_session,
        data["instance"],
    )

    assert result == {"created": 1, "skipped": 0}


def test_create_survey_notifications_is_idempotent(
    survey_test_data,
    db_session,
):
    data = survey_test_data

    first_result = create_survey_notifications(
        db_session,
        data["instance"],
    )

    second_result = create_survey_notifications(
        db_session,
        data["instance"],
    )

    assert first_result == {"created": 1, "skipped": 0}
    assert second_result == {"created": 0, "skipped": 1}

    notifications = db_session.scalars(
        select(SurveyNotification).where(
            SurveyNotification.instance_id == data["instance"].id,
            SurveyNotification.student_id == data["student"].id,
        )
    ).all()

    assert len(notifications) == 1


def test_create_survey_notifications_ignores_demo_student(
    survey_test_data,
    db_session,
):
    data = survey_test_data

    data["user"].is_demo = True
    db_session.flush()

    result = create_survey_notifications(
        db_session,
        data["instance"],
    )

    assert result == {"created": 0, "skipped": 1}

    notification = db_session.scalar(
        select(SurveyNotification).where(
            SurveyNotification.instance_id == data["instance"].id,
            SurveyNotification.student_id == data["student"].id,
        )
    )

    assert notification is None



def test_close_expired_survey_instance_at_exact_deadline(
    survey_test_data,
    db_session,
):
    """Опрос закрывается ровно в момент closes_at."""
    instance = survey_test_data["instance"]
    now = datetime.now(timezone.utc)

    instance.closes_at = now
    instance.status = "open"
    db_session.flush()

    result = close_expired_survey_instances(
        db_session,
        now=now,
    )

    db_session.refresh(instance)

    assert result >= 1
    assert instance.status == "closed"


def test_create_survey_instance_skips_before_18(
    survey_test_data,
    db_session,
    monkeypatch,
):
    """До 18:00 новый опрос не создаётся."""
    data = survey_test_data
    survey_date = date.today() + timedelta(days=2)
    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    db_session.add(
        SurveyQuestion(
            title="Тестовый вопрос",
            bot_text="Тестовый вопрос",
            answer_type="single",
            options_source="static",
            min_answer=1,
            max_answer=1,
            sort_order=1,
            is_active=True,
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        "survey_instance_service.get_classes_with_schedule",
        lambda session, target_date: [
            (
                data["class"].id,
                data["class"].code,
                data["class"].name,
                "Asia/Yekaterinburg",
            )
        ],
    )

    monkeypatch.setattr(
        "survey_instance_service.prepare_question_options",
        lambda session, question, class_id, target_date: [],
    )

    now = datetime.combine(
        survey_date,
        datetime.min.time().replace(hour=17, minute=59),
        tzinfo=school_timezone,
    )

    result = create_survey_instances_for_date(
        db_session,
        survey_date,
        now=now,
    )

    assert result["created"] == []
    assert len(result["skipped"]) == 1
    assert "Время открытия" in result["skipped"][0]["reason"]


def test_create_survey_instance_at_18_and_is_idempotent(
    survey_test_data,
    db_session,
    monkeypatch,
):
    """В 18:00 опрос создаётся, повторный запуск не создаёт дубликат."""
    data = survey_test_data
    survey_date = date.today() + timedelta(days=3)
    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    db_session.add(
        SurveyQuestion(
            title="Тестовый вопрос",
            bot_text="Тестовый вопрос",
            answer_type="single",
            options_source="static",
            min_answer=1,
            max_answer=1,
            sort_order=1,
            is_active=True,
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        "survey_instance_service.get_classes_with_schedule",
        lambda session, target_date: [
            (
                data["class"].id,
                data["class"].code,
                data["class"].name,
                "Asia/Yekaterinburg",
            )
        ],
    )

    monkeypatch.setattr(
        "survey_instance_service.prepare_question_options",
        lambda session, question, class_id, target_date: [],
    )

    now = datetime.combine(
        survey_date,
        datetime.min.time().replace(hour=18),
        tzinfo=school_timezone,
    )

    result = create_survey_instances_for_date(
        db_session,
        survey_date,
        now=now,
    )

    assert len(result["created"]) == 1
    assert result["skipped"] == []
    assert result["errors"] == []

    instance = db_session.scalar(
        select(SurveyInstance).where(
            SurveyInstance.class_id == data["class"].id,
            SurveyInstance.survey_date == survey_date,
        )
    )

    assert instance is not None
    assert instance.status == "open"
    assert instance.opens_at == now
    assert instance.closes_at == datetime.combine(
        survey_date + timedelta(days=1),
        datetime.min.time().replace(hour=18),
        tzinfo=school_timezone,
    )

    # Повторный запуск не должен создать второй экземпляр.
    second_result = create_survey_instances_for_date(
        db_session,
        survey_date,
        now=now,
    )

    assert second_result["created"] == []
    assert len(second_result["skipped"]) == 1
    assert "уже существует" in second_result["skipped"][0]["reason"]


def test_create_survey_instance_skips_at_exact_deadline(
    survey_test_data,
    db_session,
    monkeypatch,
):
    """В 18:00 следующего дня просроченный опрос не создаётся."""
    data = survey_test_data
    survey_date = date.today() + timedelta(days=4)
    school_timezone = ZoneInfo("Asia/Yekaterinburg")

    db_session.add(
        SurveyQuestion(
            title="Тестовый вопрос",
            bot_text="Тестовый вопрос",
            answer_type="single",
            options_source="static",
            min_answer=1,
            max_answer=1,
            sort_order=1,
            is_active=True,
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        "survey_instance_service.get_classes_with_schedule",
        lambda session, target_date: [
            (
                data["class"].id,
                data["class"].code,
                data["class"].name,
                "Asia/Yekaterinburg",
            )
        ],
    )

    monkeypatch.setattr(
        "survey_instance_service.prepare_question_options",
        lambda session, question, class_id, target_date: [],
    )

    deadline = datetime.combine(
        survey_date + timedelta(days=1),
        datetime.min.time().replace(hour=18),
        tzinfo=school_timezone,
    )

    result = create_survey_instances_for_date(
        db_session,
        survey_date,
        now=deadline,
    )

    assert result["created"] == []
    assert len(result["skipped"]) == 1
    assert "Срок проведения" in result["skipped"][0]["reason"]
