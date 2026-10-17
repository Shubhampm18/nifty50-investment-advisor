"""Construct a real LangChain chat model for the configured provider."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_openai import ChatOpenAI

from nifty50_investment_advisor.config import Settings, get_settings


def create_chat_model(
    settings: Settings | None = None,
) -> BaseChatModel:
    """Create a real chat model using the configured provider and credentials."""

    config = settings or get_settings()
    api_key = config.require_api_key()
    model_name = config.selected_model

    if config.llm_provider == "nvidia":
        nvidia_options: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "temperature": 0,
            "timeout": 180,
            "max_completion_tokens": 1024,
            "model_kwargs": {
                "reasoning_effort": "low",
            },
        }

        if config.nvidia_base_url:
            nvidia_options["base_url"] = config.nvidia_base_url

        return ChatNVIDIA(**nvidia_options)

    common_options: dict[str, Any] = {
        "model": model_name,
        "temperature": 0,
        "timeout": 60,
        "max_retries": 2,
    }

    if config.llm_provider == "openai":
        return ChatOpenAI(
            **common_options,
            api_key=api_key,
        )

    if config.llm_provider == "groq":
        return ChatGroq(
            **common_options,
            api_key=api_key,
        )

    if config.llm_provider == "google":
        return ChatGoogleGenerativeAI(
            **common_options,
            google_api_key=api_key,
        )

    raise ValueError(f"Unsupported LLM provider: {config.llm_provider}")
