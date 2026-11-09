"""Tests for model construction across all four providers (no real calls)."""

from unittest.mock import patch

import pytest

from nifty50_investment_advisor import model_provider
from nifty50_investment_advisor.config import Settings


def _settings(provider: str) -> Settings:
    return Settings(llm_provider=provider, **{f"{provider}_api_key": "test-key"})


@pytest.mark.parametrize(
    ("provider", "patch_target"),
    [
        ("openai", "nifty50_investment_advisor.model_provider.ChatOpenAI"),
        ("groq", "nifty50_investment_advisor.model_provider.ChatGroq"),
        ("google", "nifty50_investment_advisor.model_provider.ChatGoogleGenerativeAI"),
        ("nvidia", "nifty50_investment_advisor.model_provider.ChatNVIDIA"),
    ],
)
def test_provider_constructs_with_temperature_zero(provider, patch_target):
    with patch(patch_target) as model_class:
        model_provider.create_chat_model(_settings(provider))

    kwargs = model_class.call_args.kwargs
    assert kwargs["model"] == Settings(llm_provider=provider).selected_model
    assert kwargs["temperature"] == 0
    assert "api_key" in kwargs or "google_api_key" in kwargs


def test_nvidia_options_include_base_url_and_token_cap():
    settings = Settings(
        llm_provider="nvidia",
        nvidia_api_key="k",
        nvidia_base_url="https://custom.example/v1",
    )
    with patch(
        "nifty50_investment_advisor.model_provider.ChatNVIDIA"
    ) as model_class:
        model_provider.create_chat_model(settings)

    kwargs = model_class.call_args.kwargs
    assert kwargs["base_url"] == "https://custom.example/v1"
    assert kwargs["max_completion_tokens"] == 1024
    assert kwargs["timeout"] == 180
    assert kwargs["model_kwargs"]["reasoning_effort"] == "low"


def test_nvidia_omits_base_url_when_unset():
    with patch(
        "nifty50_investment_advisor.model_provider.ChatNVIDIA"
    ) as model_class:
        model_provider.create_chat_model(_settings("nvidia"))

    assert "base_url" not in model_class.call_args.kwargs


def test_missing_api_key_raises_safe_error():
    settings = Settings(llm_provider="groq", groq_api_key="")
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        model_provider.create_chat_model(settings)


def test_unsupported_provider_raises():
    settings = Settings(llm_provider="openai", openai_api_key="k")
    object.__setattr__(settings, "llm_provider", "unknown-provider")
    with pytest.raises((ValueError, KeyError), match="Unsupported LLM provider|unknown-provider"):
        model_provider.create_chat_model(settings)
