import asyncio

import pytest

import ai_provider
from ai_config import AIConfig, AIProviderConfig
from ai_provider import (
    AINonRetryableError,
    AIRetryableError,
    generate_json,
    generate_json_with_metadata,
)


@pytest.fixture
def provider_config():
    primary = AIProviderConfig(
        base_url="https://primary.example/v1",
        token="primary-token",
        model="primary-model",
    )

    fallback = AIProviderConfig(
        base_url="https://fallback.example/v1",
        token="fallback-token",
        model="fallback-model",
    )

    return AIConfig(
        primary=primary,
        fallback=fallback,
        timeout_seconds=10,
        max_output_tokens=100,
    )


def test_generate_json_with_metadata_uses_primary(
    monkeypatch,
    provider_config,
):
    async def fake_send_request(provider, messages, **kwargs):
        return "primary response"

    monkeypatch.setattr(
        ai_provider,
        "get_ai_config",
        lambda: provider_config,
    )
    monkeypatch.setattr(
        ai_provider,
        "_send_request",
        fake_send_request,
    )

    result = asyncio.run(
        generate_json_with_metadata(
            [{"role": "user", "content": "test"}]
        )
    )

    assert result.content == "primary response"
    assert result.identity.provider == "primary.example"
    assert result.identity.model == "primary-model"


def test_generate_json_with_metadata_uses_fallback(
    monkeypatch,
    provider_config,
):
    calls = []

    async def fake_send_request(provider, messages, **kwargs):
        calls.append(provider)

        if provider == provider_config.primary:
            raise AIRetryableError("Temporary error")

        return "fallback response"

    monkeypatch.setattr(
        ai_provider,
        "get_ai_config",
        lambda: provider_config,
    )
    monkeypatch.setattr(
        ai_provider,
        "_send_request",
        fake_send_request,
    )

    result = asyncio.run(
        generate_json_with_metadata(
            [{"role": "user", "content": "test"}]
        )
    )

    assert result.content == "fallback response"
    assert result.identity.provider == "fallback.example"
    assert result.identity.model == "fallback-model"

    assert calls == [
        provider_config.primary,
        provider_config.fallback,
    ]


def test_generate_json_does_not_use_fallback_for_non_retryable_error(
    monkeypatch,
    provider_config,
):
    calls = []

    async def fake_send_request(provider, messages, **kwargs):
        calls.append(provider)
        raise AINonRetryableError("Invalid authorization")

    monkeypatch.setattr(
        ai_provider,
        "get_ai_config",
        lambda: provider_config,
    )
    monkeypatch.setattr(
        ai_provider,
        "_send_request",
        fake_send_request,
    )

    with pytest.raises(AINonRetryableError):
        asyncio.run(
            generate_json_with_metadata(
                [{"role": "user", "content": "test"}]
            )
        )

    assert calls == [provider_config.primary]


def test_generate_json_without_fallback_propagates_error(
    monkeypatch,
    provider_config,
):
    config_without_fallback = AIConfig(
        primary=provider_config.primary,
        fallback=None,
        timeout_seconds=10,
        max_output_tokens=100,
    )

    async def fake_send_request(provider, messages, **kwargs):
        raise AIRetryableError("Provider unavailable")

    monkeypatch.setattr(
        ai_provider,
        "get_ai_config",
        lambda: config_without_fallback,
    )
    monkeypatch.setattr(
        ai_provider,
        "_send_request",
        fake_send_request,
    )

    with pytest.raises(AIRetryableError):
        asyncio.run(
            generate_json_with_metadata(
                [{"role": "user", "content": "test"}]
            )
        )


def test_generate_json_keeps_string_return_type(
    monkeypatch,
    provider_config,
):
    async def fake_send_request(provider, messages, **kwargs):
        return "plain response"

    monkeypatch.setattr(
        ai_provider,
        "get_ai_config",
        lambda: provider_config,
    )
    monkeypatch.setattr(
        ai_provider,
        "_send_request",
        fake_send_request,
    )

    result = asyncio.run(
        generate_json(
            [{"role": "user", "content": "test"}]
        )
    )

    assert result == "plain response"
    assert isinstance(result, str)
