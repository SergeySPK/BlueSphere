import asyncio
import json
from datetime import date

import pytest

import ai_service
from ai_provider import AIRetryableError, AIProviderIdentity, AIProviderResponse
from ai_schemas import AIAnalysisInput
from ai_service import (
    AIResponseValidationError,
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
                    "date": "2026-11-10",
                    "level": 2,
                    "survey_dates_used": [],
                }
            ],
            "recommendations": [
                {
                    "date": "2026-11-10",
                    "kind": "class",
                    "priority": "normal",
                    "title": "Распределить нагрузку",
                    "recommendation_text": (
                        "**Рекомендация:**\\n\\n"
                        "Рассмотреть равномерное распределение "
                        "дополнительных заданий."
                    ),
                    "rationale": "В этот день запланирована контрольная.",
                    "teacher_id": None,
                    "schedule_id": None,
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


def test_analyze_day_rejects_wrong_target_date(
    monkeypatch,
    ai_input,
):
    wrong_date_response = json.dumps(
        {
            "schema_version": "1.0",
            "daily_loads": [
                {
                    "date": "2026-11-11",
                    "level": 2,
                    "survey_dates_used": [],
                }
            ],
            "recommendations": [],
        }
    )

    responses = iter(
        [
            wrong_date_response,
            wrong_date_response,
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
