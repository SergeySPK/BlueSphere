from datetime import date

import pytest
from pydantic import ValidationError

from ai_schemas import (
    AIAnalysisInput,
    AIAnalysisOutput,
    validate_ai_output_against_input,
)


@pytest.fixture
def ai_input():
    return AIAnalysisInput(
        school_id=1,
        academic_year_id=1,
        class_id=10,
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 22),
        target_date=date(2026, 11, 3),
        school_timezone="Europe/Moscow",
        assignments=[
            {
                "assignment_id": 50,
                "teacher_id": 20,
                "subject_id": 5,
                "subject_name": "Математика",
                "subgroup": 0,
            },
            {
                "assignment_id": 51,
                "teacher_id": 21,
                "subject_id": 6,
                "subject_name": "Физика",
                "subgroup": 0,
            },
            {
                # Учитель назначен в класс, но уроков в периоде нет.
                "assignment_id": 52,
                "teacher_id": 22,
                "subject_id": 7,
                "subject_name": "История",
                "subgroup": 0,
            },
        ],
        lessons=[
            {
                "schedule_id": 100,
                "assignment_id": 50,
                "date": date(2026, 11, 3),
                "lesson_number": 1,
                "lesson_type": "Контрольная работа",
                "subject_id": 5,
                "subject_name": "Математика",
                "teacher_id": 20,
                "subgroup": 0,
            },
            {
                "schedule_id": 101,
                "assignment_id": 51,
                "date": date(2026, 11, 4),
                "lesson_number": 2,
                "lesson_type": "Практическая работа",
                "subject_id": 6,
                "subject_name": "Физика",
                "teacher_id": 21,
                "subgroup": 0,
            },
        ],
        surveys=[
            {
                "survey_date": date(2026, 11, 2),
                "status": "closed",
                "questions": [
                    {
                        "title": "Общее самочувствие",
                        "answer_type": "single",
                        "respondents_count": 10,
                        "options": [
                            {
                                "title": "Хорошо",
                                "responses_count": 8,
                                "percentage": 80.0,
                            },
                            {
                                "title": "Плохо",
                                "responses_count": 2,
                                "percentage": 20.0,
                            },
                        ],
                    }
                ],
            }
        ],
    )


def make_output(
    *,
    target_date=date(2026, 11, 3),
    survey_dates=None,
    recommendations=None,
):
    return AIAnalysisOutput(
        daily_loads=[
            {
                "date": target_date,
                "level": 2,
                "survey_dates_used": survey_dates or [],
            }
        ],
        recommendations=recommendations or [],
    )


def test_valid_ai_output(ai_input):
    output = make_output(
        survey_dates=[date(2026, 11, 2)],
        recommendations=[
            {
                "date": date(2026, 11, 3),
                "kind": "lesson",
                "schedule_id": 100,
                "teacher_id": 20,
                "priority": "high",
                "title": "Проверить распределение контрольных",
                "recommendation_text": "Рассмотреть перенос работы.",
            },
            {
                "date": date(2026, 11, 4),
                "kind": "teacher",
                "teacher_id": 21,
                "title": "Проверить нагрузку",
                "recommendation_text": "Распределить контрольные равномернее.",
            },
        ],
    )

    assert validate_ai_output_against_input(output, ai_input) == output


def test_level_out_of_range():
    with pytest.raises(ValidationError):
        AIAnalysisOutput(
            daily_loads=[
                {
                    "date": date(2026, 11, 3),
                    "level": 5,
                }
            ],
            recommendations=[],
        )


def test_unknown_schedule_id(ai_input):
    output = make_output(
        recommendations=[
            {
                "date": date(2026, 11, 3),
                "kind": "lesson",
                "schedule_id": 999,
                "title": "Перенести урок",
                "recommendation_text": "Перенести занятие.",
            }
        ],
    )

    with pytest.raises(ValueError, match="Неизвестный schedule_id"):
        validate_ai_output_against_input(output, ai_input)


def test_future_survey_is_rejected_in_input(ai_input):
    source_data = ai_input.model_dump()
    source_data["surveys"].append(
        {
            "survey_date": date(2026, 11, 3),
            "status": "closed",
            "questions": [],
        }
    )

    with pytest.raises(ValidationError, match="нельзя передавать"):
        AIAnalysisInput.model_validate(source_data)


def test_unknown_teacher_id_is_rejected(ai_input):
    output = make_output(
        recommendations=[
            {
                "date": date(2026, 11, 3),
                "kind": "teacher",
                "teacher_id": 999,
                "title": "Рекомендация",
                "recommendation_text": "Проверить нагрузку.",
            }
        ],
    )

    with pytest.raises(ValueError, match="Неизвестный teacher_id"):
        validate_ai_output_against_input(output, ai_input)


def test_assigned_teacher_without_lessons_is_valid(ai_input):
    output = make_output(
        recommendations=[
            {
                "date": date(2026, 11, 5),
                "kind": "teacher",
                "teacher_id": 22,
                "title": "Проверить планирование",
                "recommendation_text": "Проверить будущую нагрузку.",
            }
        ],
    )

    assert validate_ai_output_against_input(output, ai_input) == output


def test_unknown_assignment_is_rejected(ai_input):
    source_data = ai_input.model_dump()
    source_data["lessons"][0]["assignment_id"] = 999

    with pytest.raises(ValidationError, match="не найдено назначение"):
        AIAnalysisInput.model_validate(source_data)


def test_lesson_must_match_assignment(ai_input):
    source_data = ai_input.model_dump()
    source_data["lessons"][0]["teacher_id"] = 21

    with pytest.raises(ValidationError, match="не соответствуют"):
        AIAnalysisInput.model_validate(source_data)


def test_invalid_timezone_is_rejected(ai_input):
    source_data = ai_input.model_dump()
    source_data["school_timezone"] = "Invalid/Timezone"

    with pytest.raises(ValidationError, match="Некорректный часовой пояс"):
        AIAnalysisInput.model_validate(source_data)


def test_target_date_must_be_inside_period(ai_input):
    source_data = ai_input.model_dump()
    source_data["target_date"] = date(2026, 11, 23)

    with pytest.raises(ValidationError, match="вне периода"):
        AIAnalysisInput.model_validate(source_data)


def test_output_must_contain_exactly_one_daily_load():
    with pytest.raises(ValidationError, match="ровно для одной даты"):
        AIAnalysisOutput(
            daily_loads=[],
            recommendations=[],
        )


def test_output_date_must_match_target_date(ai_input):
    output = make_output(
        target_date=date(2026, 11, 4),
    )

    with pytest.raises(ValueError, match="Ожидалась нагрузка"):
        validate_ai_output_against_input(output, ai_input)


def test_unscheduled_day_must_not_be_generated_by_ai(ai_input):
    target_date = date(2026, 11, 5)

    source = ai_input.model_copy(
        update={
            "target_date": target_date,
        }
    )

    output = make_output(
        target_date=target_date,
    )

    with pytest.raises(ValueError, match="нет уроков"):
        validate_ai_output_against_input(output, source)


def test_multiple_choice_percentages_can_exceed_100(ai_input):
    survey_data = ai_input.surveys[0].model_dump()
    survey_data["questions"] = [
        {
            "title": "Предметы",
            "answer_type": "multiple",
            "respondents_count": 10,
            "options": [
                {
                    "title": "Математика",
                    "responses_count": 8,
                    "percentage": 80.0,
                },
                {
                    "title": "Физика",
                    "responses_count": 7,
                    "percentage": 70.0,
                },
            ],
        }
    ]

    survey = type(ai_input.surveys[0]).model_validate(survey_data)

    assert sum(
        option.percentage
        for option in survey.questions[0].options
    ) == 150.0


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        AIAnalysisOutput(
            daily_loads=[
                {
                    "date": date(2026, 11, 3),
                    "level": 2,
                }
            ],
            recommendations=[],
            arbitrary_database_command="DROP TABLE schedule",
        )
