import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from ai_config import AIProviderConfig, get_ai_config


logger = logging.getLogger(__name__)


class AIProviderError(Exception):
    """Базовая ошибка AI-провайдера."""


class AIRetryableError(AIProviderError):
    """Временная ошибка: можно попробовать резервный сервис."""


class AINonRetryableError(AIProviderError):
    """Постоянная ошибка конфигурации или запроса."""


@dataclass(frozen=True)
class AIProviderIdentity:
    """Безопасные метаданные фактически использованного провайдера."""

    provider: str
    model: str


@dataclass(frozen=True)
class AIProviderResponse:
    """Ответ провайдера вместе с его метаданными."""

    content: str
    identity: AIProviderIdentity


def _provider_identity(provider: AIProviderConfig) -> AIProviderIdentity:
    hostname = urlparse(provider.base_url).hostname or "configured"

    return AIProviderIdentity(
        provider=hostname[:50],
        model=provider.model[:100],
    )


def _extract_content(response_data: dict[str, Any]) -> str:
    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise AINonRetryableError(
            "AI-провайдер вернул ответ неизвестного формата."
        ) from error

    if not isinstance(content, str) or not content.strip():
        raise AINonRetryableError(
            "AI-провайдер вернул пустой ответ."
        )

    return content.strip()


async def _send_request(
    provider: AIProviderConfig,
    messages: list[dict[str, str]],
    *,
    timeout_seconds: float,
    max_output_tokens: int,
) -> str:
    url = f"{provider.base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {provider.token}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds
        ) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

    except (httpx.TimeoutException, httpx.TransportError) as error:
        raise AIRetryableError(
            "Не удалось получить ответ от AI-провайдера."
        ) from error

    if response.status_code == 429 or response.status_code >= 500:
        raise AIRetryableError(
            f"Временная ошибка AI-провайдера: HTTP {response.status_code}."
        )

    if response.status_code in (401, 403):
        raise AINonRetryableError(
            "AI-провайдер отклонил авторизацию."
        )

    if response.status_code >= 400:
        raise AINonRetryableError(
            f"AI-провайдер отклонил запрос: HTTP {response.status_code}."
        )

    try:
        response_data = response.json()
    except ValueError as error:
        raise AINonRetryableError(
            "AI-провайдер вернул некорректный JSON."
        ) from error

    return _extract_content(response_data)


async def generate_json_with_metadata(
    messages: list[dict[str, str]],
) -> AIProviderResponse:
    """
    Генерирует JSON и возвращает метаданные фактического провайдера.

    Fallback используется только при AIRetryableError основного провайдера.
    """

    config = get_ai_config()

    try:
        content = await _send_request(
            config.primary,
            messages,
            timeout_seconds=config.timeout_seconds,
            max_output_tokens=config.max_output_tokens,
        )

        return AIProviderResponse(
            content=content,
            identity=_provider_identity(config.primary),
        )

    except AIRetryableError:
        if config.fallback is None:
            raise

        logger.warning(
            "Основной AI-провайдер временно недоступен. "
            "Используется резервный провайдер."
        )

    content = await _send_request(
        config.fallback,
        messages,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens,
    )

    return AIProviderResponse(
        content=content,
        identity=_provider_identity(config.fallback),
    )


async def generate_json(
    messages: list[dict[str, str]],
) -> str:
    """
    Совместимый интерфейс для существующего кода.

    Возвращает только текст, как и прежняя реализация.
    """

    response = await generate_json_with_metadata(messages)
    return response.content
