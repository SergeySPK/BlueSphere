import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
import logging

from ai_prompts import build_reference_aliases, build_system_prompt, build_user_prompt
from ai_provider import (
    AIProviderIdentity,
    generate_json,
    generate_json_with_metadata,
)
from ai_schemas import (
    AIAnalysisInput,
    AIAnalysisOutput,
    AIModelAnalysisOutput,
    AIModelRecommendationOutput,
    AIRecommendationOutput,
    validate_ai_output_against_input,
)

logger = logging.getLogger(__name__)

MAX_REPAIR_RESPONSE_CHARS = 20_000
MAX_REPAIR_ERROR_CHARS = 2_000


class AIResponseValidationError(RuntimeError):
    """AI вернул некорректный ответ после попытки исправления."""


@dataclass(frozen=True)
class AIAnalysisResult:
    """Проверенный результат анализа и сведения об использованных провайдерах."""

    output: AIAnalysisOutput
    provider_usages: tuple[AIProviderIdentity, ...]


def _convert_model_recommendations(
    recommendations: list,
    source: AIAnalysisInput,
) -> list:
    """
    Преобразует символьные ссылки модели в реальные ID.

    Рекомендации с неизвестными ссылками отбрасываются.
    Остальной результат, включая дневную нагрузку, сохраняется.
    """
    aliases = build_reference_aliases(source)

    teacher_ids_by_ref = {
        ref: teacher_id
        for teacher_id, ref in aliases["teachers"].items()
    }

    lessons_by_ref = {
        ref: lesson
        for lesson in source.lessons
        for ref in [aliases["lessons"][lesson.schedule_id]]
    }

    converted = []

    for recommendation in recommendations:
        teacher_id = None
        schedule_id = None

        if recommendation.kind == "class":
            pass

        elif recommendation.kind == "teacher":
            teacher_id = teacher_ids_by_ref.get(
                recommendation.teacher_ref
            )

            if teacher_id is None:
                logger.warning(
                    "AI-рекомендация отброшена: неизвестный teacher_ref=%s",
                    recommendation.teacher_ref,
                )
                continue

            teacher_has_target_day_lesson = any(
                lesson.teacher_id == teacher_id
                and lesson.date == source.target_date
                for lesson in source.lessons
            )

            if not teacher_has_target_day_lesson:
                logger.warning(
                    "AI-рекомендация отброшена: у teacher_ref=%s "
                    "нет уроков в target_date",
                    recommendation.teacher_ref,
                )
                continue

        elif recommendation.kind == "lesson":
            lesson = lessons_by_ref.get(recommendation.lesson_ref)

            if lesson is None or lesson.date != source.target_date:
                logger.warning(
                    "AI-рекомендация отброшена: неизвестный "
                    "или недопустимый lesson_ref=%s",
                    recommendation.lesson_ref,
                )
                continue

            schedule_id = lesson.schedule_id

            # Учителя для урока определяет Python, а не модель.
            teacher_id = lesson.teacher_id

        converted.append(
            AIRecommendationOutput(
                date=source.target_date,
                kind=recommendation.kind,
                priority=recommendation.priority,
                title=recommendation.title,
                recommendation_text=recommendation.recommendation_text,
                rationale=recommendation.rationale,
                teacher_id=teacher_id,
                schedule_id=schedule_id,
            )
        )

    return converted


def _validate_response(
    raw_response: str,
    source: AIAnalysisInput,
) -> AIAnalysisOutput:
    """Разбирает JSON, отдельно проверяет нагрузку и рекомендации."""

    payload: Any = json.loads(raw_response)

    if not isinstance(payload, dict):
        raise ValueError(
            "Корневой элемент ответа должен быть JSON-объектом."
        )

    raw_recommendations = payload.get("recommendations")

    if not isinstance(raw_recommendations, list):
        raise ValueError(
            "Поле recommendations должно быть JSON-массивом."
        )

    # Сначала строго проверяем весь основной контракт и daily_loads.
    # Рекомендации временно убираем из общей проверки, чтобы ошибка
    # одного элемента не уничтожала корректную дневную нагрузку.
    payload_without_recommendations = {
        **payload,
        "recommendations": [],
    }

    model_output = AIModelAnalysisOutput.model_validate(
        payload_without_recommendations
    )

    # Каждый элемент проверяется независимо.
    # Некорректные рекомендации пропускаются, остальные сохраняются.
    valid_recommendations = []

    for index, raw_recommendation in enumerate(raw_recommendations):
        if not isinstance(raw_recommendation, dict):
            raise ValueError(
                f"Рекомендация с индексом {index} должна быть JSON-объектом."
            )

        invalid_reference_type = any(
            raw_recommendation.get(field) is not None
            and not isinstance(raw_recommendation[field], str)
            for field in ("teacher_ref", "lesson_ref")
        )

        if invalid_reference_type:
            logger.warning(
                "AI-рекомендация отброшена: некорректный тип "
                "teacher_ref или lesson_ref, индекс=%s",
                index,
            )
            continue

        recommendation = AIModelRecommendationOutput.model_validate(
            raw_recommendation
        )

        valid_recommendations.append(recommendation)

    # Если хотя бы одна рекомендация фактически уменьшает
    # нагрузку целевого дня, daily_load обязан это отражать.
    has_load_reduction_recommendation = any(
        item.reduces_target_load
        for item in valid_recommendations
    )

    daily_reduce_load = model_output.daily_loads[0].reduce_load

    if has_load_reduction_recommendation and daily_reduce_load is not True:
        raise ValueError(
            "Рекомендация уменьшает нагрузку target_date, "
            "но daily_load.reduce_load не равен true"
        )

    converted_recommendations = _convert_model_recommendations(
        valid_recommendations,
        source,
    )

    output = AIAnalysisOutput(
        schema_version=model_output.schema_version,
        daily_loads=[
            {
                "date": source.target_date,
                **model_output.daily_loads[0].model_dump(),
            }
        ],
        recommendations=converted_recommendations,
    )

    return validate_ai_output_against_input(output, source)


def _build_repair_message(error: Exception) -> str:
    """Формирует короткую инструкцию для единственной попытки исправления."""

    if isinstance(error, ValidationError):
        details = error.errors(
            include_input=False,
            include_context=False,
            include_url=False,
        )
        error_description = json.dumps(
            details,
            ensure_ascii=False,
        )
    else:
        error_description = str(error)

    error_description = error_description[:MAX_REPAIR_ERROR_CHARS]

    return (
        "Предыдущий ответ не прошёл проверку JSON или схемы.\n"
        "Исправь ответ с учётом ошибки ниже.\n"
        "Верни полный JSON-объект строго по исходному системному "
        "сообщению и исходным входным данным.\n"
        "Не добавляй пояснения, Markdown-обёртку или новые поля.\n\n"
        f"Ошибка проверки:\n{error_description}"
    )


async def _analyze_day(
    source: AIAnalysisInput,
    *,
    capture_provider_metadata: bool,
) -> tuple[AIAnalysisOutput, tuple[AIProviderIdentity, ...]]:
    if not isinstance(source, AIAnalysisInput):
        raise TypeError(
            "source должен быть экземпляром AIAnalysisInput."
        )

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(),
        },
        {
            "role": "user",
            "content": build_user_prompt(source),
        },
    ]

    provider_usages = []

    for attempt in range(2):
        if capture_provider_metadata:
            provider_response = await generate_json_with_metadata(messages)
            raw_response = provider_response.content
            provider_usages.append(provider_response.identity)
        else:
            raw_response = await generate_json(messages)

        try:
            output = _validate_response(raw_response, source)
            return output, tuple(provider_usages)

        except (
            json.JSONDecodeError,
            ValidationError,
            ValueError,
            TypeError,
        ) as error:
            if isinstance(error, ValidationError):
                error_details = json.dumps(
                    error.errors(
                        include_input=False,
                        include_context=False,
                        include_url=False,
                    ),
                    ensure_ascii=False,
                )
            else:
                error_details = str(error)

            logger.warning(
                "AI response validation failed: attempt=%s/2, "
                "error_type=%s, details=%s",
                attempt + 1,
                type(error).__name__,
                error_details[:MAX_REPAIR_ERROR_CHARS],
            )

            if attempt == 1:
                raise AIResponseValidationError(
                    "AI не смог вернуть корректный ответ "
                    "после одной попытки исправления."
                ) from error

            messages.append(
                {
                    "role": "assistant",
                    "content": raw_response[:MAX_REPAIR_RESPONSE_CHARS],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": _build_repair_message(error),
                }
            )

    raise AIResponseValidationError(
        "Не удалось получить корректный результат AI-анализа."
    )


async def analyze_day(source: AIAnalysisInput) -> AIAnalysisOutput:
    """
    Совместимый интерфейс.

    Возвращает только AIAnalysisOutput, как и прежняя реализация.
    """

    output, _ = await _analyze_day(
        source,
        capture_provider_metadata=False,
    )
    return output


async def analyze_day_with_metadata(
    source: AIAnalysisInput,
) -> AIAnalysisResult:
    """
    Анализирует день и возвращает фактически использованные провайдеры.

    Учитывает и первоначальный запрос, и запрос исправления ответа.
    """

    output, provider_usages = await _analyze_day(
        source,
        capture_provider_metadata=True,
    )

    return AIAnalysisResult(
        output=output,
        provider_usages=provider_usages,
    )
