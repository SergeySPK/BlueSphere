import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AIProviderConfig:
    base_url: str
    token: str
    model: str


@dataclass(frozen=True)
class AIConfig:
    primary: AIProviderConfig
    fallback: AIProviderConfig | None
    timeout_seconds: float
    max_output_tokens: int


def _provider_from_env(prefix: str) -> AIProviderConfig | None:
    base_url = os.getenv(f"{prefix}BASE_URL", "").strip()
    token = os.getenv(f"{prefix}TOKEN", "").strip()
    model = os.getenv(f"{prefix}MODEL", "").strip()

    if not any((base_url, token, model)):
        return None

    if not all((base_url, token, model)):
        raise ValueError(
            f"Не полностью настроен AI-провайдер: {prefix}"
        )

    return AIProviderConfig(
        base_url=base_url.rstrip("/"),
        token=token,
        model=model,
    )


def get_ai_config_if_configured() -> AIConfig | None:
    primary = _provider_from_env("AI_")

    if primary is None:
        return None

    fallback = _provider_from_env("AI_FALLBACK_")

    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "60"))
    max_tokens = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "4000"))

    if timeout <= 0:
        raise ValueError("AI_TIMEOUT_SECONDS должен быть больше нуля.")

    if max_tokens <= 0:
        raise ValueError("AI_MAX_OUTPUT_TOKENS должен быть больше нуля.")

    return AIConfig(
        primary=primary,
        fallback=fallback,
        timeout_seconds=timeout,
        max_output_tokens=max_tokens,
    )


def get_ai_config() -> AIConfig:
    config = get_ai_config_if_configured()

    if config is None:
        raise ValueError("Не настроен основной AI-провайдер.")

    return config
