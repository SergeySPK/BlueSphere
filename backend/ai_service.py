import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ai_prompts import build_system_prompt, build_user_prompt
from ai_provider import (
    AIProviderIdentity,
    generate_json,
    generate_json_with_metadata,
)
from ai_schemas import (
    AIAnalysisInput,
    AIAnalysisOutput,
    validate_ai_output_against_input,
)


MAX_REPAIR_RESPONSE_CHARS = 20_000
MAX_REPAIR_ERROR_CHARS = 2_000


class AIResponseValidationError(RuntimeError):
    """AI вернул некорректный ответ после попытки исправления."""


@dataclass(frozen=True)
class AIAnalysisResult:
    """Проверенный результат анализа и сведения об использованных провайдерах."""

    output: AIAnalysisOutput
    provider_usages: tuple[AIProviderIdentity, ...]


def _validate_response(
    raw_response: str,
    source: AIAnalysisInput,
) -> AIAnalysisOutput:
    """Разбирает JSON и проверяет ответ по схемам и исходному контексту."""

    payload: Any = json.loads(raw_response)

    if not isinstance(payload, dict):
        raise ValueError(
            "Корневой элемент ответа должен быть JSON-объектом."
        )

    output = AIAnalysisOutput.model_validate(payload)

    if len(output.daily_loads) != 1:
        raise ValueError(
            "daily_loads должен содержать ровно одну запись."
        )

    if output.daily_loads[0].date != source.target_date:
        raise ValueError(
            "Дата daily_loads не совпадает с целевой датой анализа."
        )

    for recommendation in output.recommendations:
        if recommendation.date < source.target_date:
            raise ValueError(
                "Дата рекомендации не может быть раньше target_date."
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
