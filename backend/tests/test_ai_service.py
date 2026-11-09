import asyncio
import json
from datetime import date

import pytest

import ai_service
from ai_provider import AIRetryableError, AIProviderIdentity, AIProviderResponse
from ai_schemas import AIAnalysisInput
from ai_service import (
    AIResponseValidationError,
    ValidationError,
    analyze_day,
    analyze_day_with_metadata,
)


@pytest.fixture
def ai_input():
    return AIAnalysisInput(
        school_id=1,
        academic_year_id=2,
        class_id=10,
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 22),
        target_date=date(2026, 11, 10),
        school_timezone="Europe/Moscow",
        assignments=[
            {
                "assignment_id": 100,
                "teacher_id": 20,
                "subject_id": 5,
                "subject_name": "Математика",
                "subgroup": 0,
            },
        ],
        lessons=[
            {
                "schedule_id": 500,
                "assignment_id": 100,
                "date": date(2026, 11, 10),
                "lesson_number": 1,
                "lesson_type": "Контрольная работа",
                "subject_id": 5,
                "subject_name": "Математика",
                "teacher_id": 20,
                "subgroup": 0,
            },
        ],
        surveys=[],
    )


def valid_response():
    return json.dumps(
        {
            "schema_version": "1.0",
            "daily_loads": [
                {
                    "level": 2,
                    "reduce_load": False,
                    "suitable_for_moving": True,
                    "survey_dates_used": [],
                }
            ],
            "recommendations": [
                {
                    "kind": "class",
                    "priority": "normal",
                    "title": "Распределить нагрузку",
                    "recommendation_text": (
                        "**Рекомендация:**\n\n"
                        "Рассмотреть равномерное распределение "
                        "дополнительных заданий."
                    ),
                    "rationale": "В этот день запланирована контрольная.",
                    "teacher_ref": None,
                    "lesson_ref": None,
                    "reduces_target_load": False,
                }
            ],
        },
        ensure_ascii=False,
    )


def test_analyze_day_returns_validated_output(monkeypatch, ai_input):
    calls = []

    async def fake_generate_json(messages):
        calls.append(messages)
        return valid_response()

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert result.daily_loads[0].date == ai_input.target_date
    assert result.daily_loads[0].level == 2
    assert result.daily_loads[0].reduce_load is False
    assert result.daily_loads[0].suitable_for_moving is True
    assert len(result.recommendations) == 1
    assert result.recommendations[0].kind == "class"
    assert len(calls) == 1


def test_analyze_day_repairs_invalid_json(monkeypatch, ai_input):
    responses = iter(
        [
            '{"daily_loads":',
            valid_response(),
        ]
    )
    calls = []

    async def fake_generate_json(messages):
        calls.append(messages)
        return next(responses)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert result.daily_loads[0].date == ai_input.target_date
    assert len(calls) == 2

    repair_messages = calls[1]

    assert repair_messages[-1]["role"] == "user"
    assert "Исправь ответ" in repair_messages[-1]["content"]


def test_analyze_day_rejects_invalid_response_after_repair(
    monkeypatch,
    ai_input,
):
    async def fake_generate_json(messages):
        return '{"unexpected": true}'

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    with pytest.raises(AIResponseValidationError):
        asyncio.run(analyze_day(ai_input))


def test_analyze_day_rejects_model_generated_daily_load_date(
    monkeypatch,
    ai_input,
):
    response_with_date = json.dumps(
        {
            "schema_version": "1.0",
            "daily_loads": [
                {
                    "date": "2023-10-15",
                    "level": 2,
                    "survey_dates_used": [],
                }
            ],
            "recommendations": [],
        }
    )

    responses = iter(
        [
            response_with_date,
            response_with_date,
        ]
    )

    async def fake_generate_json(messages):
        return next(responses)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    with pytest.raises(AIResponseValidationError):
        asyncio.run(analyze_day(ai_input))


def test_analyze_day_does_not_retry_provider_error(
    monkeypatch,
    ai_input,
):
    calls = 0

    async def fake_generate_json(messages):
        nonlocal calls
        calls += 1
        raise AIRetryableError("Провайдер временно недоступен.")

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    with pytest.raises(AIRetryableError):
        asyncio.run(analyze_day(ai_input))

    assert calls == 1


def test_analyze_day_rejects_wrong_input_type():
    with pytest.raises(TypeError, match="AIAnalysisInput"):
        asyncio.run(analyze_day({}))


def test_analyze_day_with_metadata_returns_provider(
    monkeypatch,
    ai_input,
):
    async def fake_generate_json_with_metadata(messages):
        return AIProviderResponse(
            content=valid_response(),
            identity=AIProviderIdentity(
                provider="primary.example",
                model="primary-model",
            ),
        )

    monkeypatch.setattr(
        ai_service,
        "generate_json_with_metadata",
        fake_generate_json_with_metadata,
    )

    result = asyncio.run(
        analyze_day_with_metadata(ai_input)
    )

    assert result.output.daily_loads[0].date == ai_input.target_date
    assert len(result.provider_usages) == 1
    assert result.provider_usages[0].provider == "primary.example"
    assert result.provider_usages[0].model == "primary-model"


def test_analyze_day_with_metadata_tracks_provider_during_repair(
    monkeypatch,
    ai_input,
):
    responses = iter(
        [
            AIProviderResponse(
                content='{"daily_loads":',
                identity=AIProviderIdentity(
                    provider="primary.example",
                    model="primary-model",
                ),
            ),
            AIProviderResponse(
                content=valid_response(),
                identity=AIProviderIdentity(
                    provider="fallback.example",
                    model="fallback-model",
                ),
            ),
        ]
    )

    async def fake_generate_json_with_metadata(messages):
        return next(responses)

    monkeypatch.setattr(
        ai_service,
        "generate_json_with_metadata",
        fake_generate_json_with_metadata,
    )

    result = asyncio.run(
        analyze_day_with_metadata(ai_input)
    )

    assert result.output.daily_loads[0].date == ai_input.target_date

    assert len(result.provider_usages) == 2

    assert result.provider_usages[0].provider == "primary.example"
    assert result.provider_usages[1].provider == "fallback.example"


def test_analyze_day_converts_teacher_reference(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "teacher",
            "priority": "normal",
            "title": "Распределить нагрузку",
            "recommendation_text": "Рассмотреть перераспределение занятий.",
            "rationale": None,
            "teacher_ref": "T1",
            "lesson_ref": None,
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert len(result.recommendations) == 1

    recommendation = result.recommendations[0]

    assert recommendation.teacher_id == 20
    assert recommendation.schedule_id is None
    assert recommendation.date == ai_input.target_date


def test_analyze_day_converts_lesson_reference(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "lesson",
            "priority": "normal",
            "title": "Обратить внимание на урок",
            "recommendation_text": "Рассмотреть распределение нагрузки.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": "L1",
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert len(result.recommendations) == 1

    recommendation = result.recommendations[0]

    assert recommendation.schedule_id == 500
    assert recommendation.teacher_id == 20
    assert recommendation.date == ai_input.target_date


def test_analyze_day_discards_unknown_teacher_reference(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "teacher",
            "priority": "normal",
            "title": "Распределить нагрузку",
            "recommendation_text": "Рассмотреть перераспределение занятий.",
            "rationale": None,
            "teacher_ref": "T999999",
            "lesson_ref": None,
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert result.daily_loads[0].level == 2
    assert result.daily_loads[0].date == ai_input.target_date
    assert result.recommendations == []


def test_analyze_day_discards_unknown_lesson_reference(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "lesson",
            "priority": "normal",
            "title": "Обратить внимание на урок",
            "recommendation_text": "Рассмотреть распределение нагрузки.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": "L999999",
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert result.daily_loads[0].level == 2
    assert result.daily_loads[0].date == ai_input.target_date
    assert result.recommendations == []


def test_analyze_day_sets_recommendation_date_from_target_date(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())
    payload["recommendations"] = [
        {
            "kind": "class",
            "priority": "normal",
            "title": "Рекомендация классу",
            "recommendation_text": "Распределить нагрузку равномернее.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": None,
            "reduces_target_load": False,
        },
        {
            "kind": "teacher",
            "priority": "high",
            "title": "Рекомендация учителю",
            "recommendation_text": "Проверить нагрузку учителя.",
            "rationale": None,
            "teacher_ref": "T1",
            "lesson_ref": None,
            "reduces_target_load": False,
        },
        {
            "kind": "lesson",
            "priority": "normal",
            "title": "Рекомендация уроку",
            "recommendation_text": "Обратить внимание на контрольную.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": "L1",
            "reduces_target_load": False,
        },
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert len(result.recommendations) == 3

    assert all(
        recommendation.date == ai_input.target_date
        for recommendation in result.recommendations
    )

    assert result.recommendations[0].date == ai_input.target_date
    assert result.recommendations[0].teacher_id is None
    assert result.recommendations[0].schedule_id is None

    assert result.recommendations[1].date == ai_input.target_date
    assert result.recommendations[1].teacher_id == 20
    assert result.recommendations[1].schedule_id is None

    assert result.recommendations[2].date == ai_input.target_date
    assert result.recommendations[2].teacher_id == 20
    assert result.recommendations[2].schedule_id == 500


def test_analyze_day_rejects_legacy_recommendation_date_index(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())
    payload["recommendations"][0]["recommendation_date_index"] = 1

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    with pytest.raises(AIResponseValidationError):
        asyncio.run(analyze_day(ai_input))


def test_analyze_day_rejects_model_generated_recommendation_date(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"][0]["date"] = "2023-10-01"

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    with pytest.raises(AIResponseValidationError):
        asyncio.run(analyze_day(ai_input))


def test_analyze_day_repairs_recommendation_with_survey_data(
    monkeypatch,
    ai_input,
):
    invalid_payload = json.loads(valid_response())
    invalid_payload["recommendations"][0]["rationale"] = (
        "В опросе ученики сообщили о высокой нагрузке."
    )

    responses = iter(
        [
            json.dumps(invalid_payload),
            valid_response(),
        ]
    )
    calls = []

    async def fake_generate_json(messages):
        calls.append(messages)
        return next(responses)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert len(calls) == 2
    assert len(result.recommendations) == 1
    assert "опрос" not in result.recommendations[0].rationale.lower()


def test_analyze_day_fails_after_two_invalid_recommendations(
    monkeypatch,
    ai_input,
):
    invalid_payload = json.loads(valid_response())
    invalid_payload["recommendations"][0]["recommendation_text"] = (
        "Перенести контрольную на 2026-11-11."
    )

    responses = iter(
        [
            json.dumps(invalid_payload),
            json.dumps(invalid_payload),
        ]
    )
    calls = []

    async def fake_generate_json(messages):
        calls.append(messages)
        return next(responses)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    with pytest.raises(AIResponseValidationError):
        asyncio.run(analyze_day(ai_input))

    assert len(calls) == 2


def test_invalid_numeric_references_do_not_discard_valid_results(
    monkeypatch,
    ai_input,
):
    """Числовые ссылки отбрасывают только свои рекомендации."""

    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "teacher",
            "priority": "normal",
            "title": "Рекомендация с числовой ссылкой учителя",
            "recommendation_text": "Эта рекомендация должна быть отброшена.",
            "rationale": None,
            "teacher_ref": 1,
            "lesson_ref": None,
        },
        {
            "kind": "lesson",
            "priority": "normal",
            "title": "Рекомендация с числовой ссылкой урока",
            "recommendation_text": "Эта рекомендация тоже должна быть отброшена.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": 2,
        },
        {
            "kind": "class",
            "priority": "normal",
            "title": "Корректная рекомендация классу",
            "recommendation_text": "Распределить задания равномернее.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": None,
            "reduces_target_load": False,
        },
    ]

    calls = 0

    async def fake_generate_json(messages):
        nonlocal calls
        calls += 1
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    # Корректная дневная нагрузка сохранилась.
    assert result.daily_loads[0].level == 2
    assert result.daily_loads[0].date == ai_input.target_date

    # Обе рекомендации с числовыми ссылками отброшены.
    # Корректная рекомендация класса сохранена.
    assert len(result.recommendations) == 1
    assert result.recommendations[0].kind == "class"
    assert result.recommendations[0].teacher_id is None
    assert result.recommendations[0].schedule_id is None

    # Исправление ответа у провайдера не запрашивалось.
    assert calls == 1


def test_teacher_reference_is_converted_to_database_id(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "teacher",
            "priority": "normal",
            "title": "Распределить нагрузку",
            "recommendation_text": "Рассмотреть перераспределение занятий.",
            "rationale": None,
            "teacher_ref": "T1",
            "lesson_ref": None,
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert len(result.recommendations) == 1
    assert result.recommendations[0].teacher_id == 20
    assert result.recommendations[0].schedule_id is None
    assert result.recommendations[0].date == ai_input.target_date


def test_lesson_reference_is_converted_to_database_ids(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "lesson",
            "priority": "normal",
            "title": "Обратить внимание на урок",
            "recommendation_text": "Рассмотреть распределение нагрузки.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": "L1",
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert len(result.recommendations) == 1
    assert result.recommendations[0].schedule_id == 500
    assert result.recommendations[0].teacher_id == 20
    assert result.recommendations[0].date == ai_input.target_date


def test_unknown_teacher_reference_does_not_discard_daily_load(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "teacher",
            "priority": "normal",
            "title": "Распределить нагрузку",
            "recommendation_text": "Рассмотреть перераспределение занятий.",
            "rationale": None,
            "teacher_ref": "T999999",
            "lesson_ref": None,
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert result.daily_loads[0].level == 2
    assert result.daily_loads[0].date == ai_input.target_date
    assert result.recommendations == []


def test_unknown_lesson_reference_does_not_discard_daily_load(
    monkeypatch,
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"] = [
        {
            "kind": "lesson",
            "priority": "normal",
            "title": "Обратить внимание на урок",
            "recommendation_text": "Рассмотреть распределение нагрузки.",
            "rationale": None,
            "teacher_ref": None,
            "lesson_ref": "L999999",
            "reduces_target_load": False,
        }
    ]

    async def fake_generate_json(messages):
        return json.dumps(payload)

    monkeypatch.setattr(
        ai_service,
        "generate_json",
        fake_generate_json,
    )

    result = asyncio.run(analyze_day(ai_input))

    assert result.daily_loads[0].level == 2
    assert result.recommendations == []


def test_validate_response_accepts_consistent_load_reduction(
    ai_input,
):
    payload = json.loads(valid_response())

    payload["daily_loads"][0]["reduce_load"] = True
    payload["recommendations"][0]["reduces_target_load"] = True

    result = ai_service._validate_response(
        json.dumps(payload, ensure_ascii=False),
        ai_input,
    )

    assert result.daily_loads[0].reduce_load is True
    assert len(result.recommendations) == 1

    # Внутреннее поле не должно попадать в сохранённую рекомендацию.
    assert not hasattr(
        result.recommendations[0],
        "reduces_target_load",
    )


def test_validate_response_rejects_inconsistent_load_reduction(
    ai_input,
):
    payload = json.loads(valid_response())

    payload["daily_loads"][0]["reduce_load"] = False
    payload["recommendations"][0]["reduces_target_load"] = True

    with pytest.raises(
        ValueError,
        match="reduce_load не равен true",
    ):
        ai_service._validate_response(
            json.dumps(payload, ensure_ascii=False),
            ai_input,
        )


def test_validate_response_rejects_date_in_recommendation(
    ai_input,
):
    payload = json.loads(valid_response())

    payload["recommendations"][0]["recommendation_text"] = (
        "Перенести контрольную на 2026-11-11."
    )

    with pytest.raises(ValidationError):
        ai_service._validate_response(
            json.dumps(payload, ensure_ascii=False),
            ai_input,
        )
