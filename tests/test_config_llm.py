"""Settings precedence and safety tests (no environment is touched)."""

import pytest
from pydantic import ValidationError

from nifty50_investment_advisor.config import Settings


def test_selected_model_precedence_llm_model_wins():
    settings = Settings(
        llm_provider="groq",
        llm_model="custom-model",
        groq_model="per-provider-model",
        **{},
    )
    assert settings.selected_model == "custom-model"


def test_selected_model_falls_back_to_per_provider():
    settings = Settings(
        llm_provider="openai",
        openai_model="openai-override",
    )
    assert settings.selected_model == "openai-override"


def test_selected_model_defaults_per_provider():
    assert (
        Settings(llm_provider="groq").selected_model
        == "llama-3.3-70b-versatile"
    )
    assert (
        Settings(llm_provider="google").selected_model
        == "gemini-2.5-flash"
    )


def test_provider_name_normalized():
    settings = Settings(llm_provider="GROQ")
    assert settings.llm_provider == "groq"


def test_unknown_provider_rejected():
    with pytest.raises(ValidationError):
        Settings(llm_provider="not-a-provider")


def test_whitespace_model_treated_as_unset():
    settings = Settings(
        llm_provider="openai",
        llm_model="   ",
        openai_api_key="test",
    )
    assert settings.llm_model is None
    assert settings.selected_model == "gpt-4o-mini"


def test_provider_summary_hides_secrets():
    settings = Settings(llm_provider="nvidia", nvidia_api_key="super-secret-value")
    summary = settings.get_provider_summary()
    assert summary["provider"] == "nvidia"
    assert summary["model"] == settings.selected_model
    assert summary["api_key_configured"] == "True"
    assert "super-secret-value" not in str(summary.values())


def test_provider_summary_without_key():
    summary = Settings(llm_provider="groq").get_provider_summary()
    assert summary["api_key_configured"] == "False"
