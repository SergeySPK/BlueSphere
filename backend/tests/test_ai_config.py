import pytest

import ai_config


@pytest.fixture
def clear_ai_environment(monkeypatch):
    """Удаляет все AI-переменные из окружения теста."""

    for name in (
        "AI_BASE_URL",
        "AI_TOKEN",
        "AI_MODEL",
        "AI_FALLBACK_BASE_URL",
        "AI_FALLBACK_TOKEN",
        "AI_FALLBACK_MODEL",
        "AI_TIMEOUT_SECONDS",
        "AI_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_primary_provider(monkeypatch):
    """Настраивает фиктивный основной AI-провайдер."""

    monkeypatch.setenv(
        "AI_BASE_URL",
        "https://primary.example/v1",
    )
    monkeypatch.setenv("AI_TOKEN", "test-primary-token")
    monkeypatch.setenv("AI_MODEL", "test-primary-model")


def test_get_ai_config_if_configured_returns_none_when_ai_is_disabled(
    clear_ai_environment,
):
    config = ai_config.get_ai_config_if_configured()

    assert config is None


def test_get_ai_config_if_configured_returns_primary_provider(
    clear_ai_environment,
    monkeypatch,
):
    _set_primary_provider(monkeypatch)

    config = ai_config.get_ai_config_if_configured()

    assert config is not None
    assert config.primary.base_url == "https://primary.example/v1"
    assert config.primary.token == "test-primary-token"
    assert config.primary.model == "test-primary-model"
    assert config.fallback is None
    assert config.timeout_seconds == 60
    assert config.max_output_tokens == 4000


def test_get_ai_config_if_configured_accepts_custom_limits(
    clear_ai_environment,
    monkeypatch,
):
    _set_primary_provider(monkeypatch)
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("AI_MAX_OUTPUT_TOKENS", "2000")

    config = ai_config.get_ai_config_if_configured()

    assert config.timeout_seconds == 30
    assert config.max_output_tokens == 2000


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("AI_BASE_URL", "https://primary.example/v1"),
        ("AI_TOKEN", "test-token"),
        ("AI_MODEL", "test-model"),
    ],
)
def test_get_ai_config_if_configured_rejects_partial_primary_provider(
    clear_ai_environment,
    monkeypatch,
    variable,
    value,
):
    monkeypatch.setenv(variable, value)

    with pytest.raises(
        ValueError,
        match="Не полностью настроен AI-провайдер",
    ):
        ai_config.get_ai_config_if_configured()


def test_get_ai_config_if_configured_accepts_fallback_provider(
    clear_ai_environment,
    monkeypatch,
):
    _set_primary_provider(monkeypatch)

    monkeypatch.setenv(
        "AI_FALLBACK_BASE_URL",
        "https://fallback.example/v1",
    )
    monkeypatch.setenv(
        "AI_FALLBACK_TOKEN",
        "test-fallback-token",
    )
    monkeypatch.setenv(
        "AI_FALLBACK_MODEL",
        "test-fallback-model",
    )

    config = ai_config.get_ai_config_if_configured()

    assert config.fallback is not None
    assert config.fallback.base_url == "https://fallback.example/v1"
    assert config.fallback.token == "test-fallback-token"
    assert config.fallback.model == "test-fallback-model"


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("AI_FALLBACK_BASE_URL", "https://fallback.example/v1"),
        ("AI_FALLBACK_TOKEN", "test-fallback-token"),
        ("AI_FALLBACK_MODEL", "test-fallback-model"),
    ],
)
def test_get_ai_config_if_configured_rejects_partial_fallback_provider(
    clear_ai_environment,
    monkeypatch,
    variable,
    value,
):
    _set_primary_provider(monkeypatch)
    monkeypatch.setenv(variable, value)

    with pytest.raises(
        ValueError,
        match="Не полностью настроен AI-провайдер",
    ):
        ai_config.get_ai_config_if_configured()


def test_get_ai_config_preserves_required_configuration_contract(
    clear_ai_environment,
):
    with pytest.raises(
        ValueError,
        match="Не настроен основной AI-провайдер",
    ):
        ai_config.get_ai_config()


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("AI_TIMEOUT_SECONDS", "0", "AI_TIMEOUT_SECONDS"),
        ("AI_TIMEOUT_SECONDS", "-1", "AI_TIMEOUT_SECONDS"),
        ("AI_MAX_OUTPUT_TOKENS", "0", "AI_MAX_OUTPUT_TOKENS"),
        ("AI_MAX_OUTPUT_TOKENS", "-1", "AI_MAX_OUTPUT_TOKENS"),
    ],
)
def test_get_ai_config_if_configured_rejects_invalid_limits(
    clear_ai_environment,
    monkeypatch,
    variable,
    value,
    message,
):
    _set_primary_provider(monkeypatch)
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=message):
        ai_config.get_ai_config_if_configured()


def test_get_ai_config_if_configured_rejects_non_numeric_limits(
    clear_ai_environment,
    monkeypatch,
):
    _set_primary_provider(monkeypatch)
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "invalid")

    with pytest.raises(ValueError):
        ai_config.get_ai_config_if_configured()
