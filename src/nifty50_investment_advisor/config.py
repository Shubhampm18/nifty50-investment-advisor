"""Validated application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["openai", "groq", "google", "nvidia"]

DEFAULT_MODELS: dict[ProviderName, str] = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "google": "gemini-2.5-flash",
    "nvidia": "z-ai/glm-5.3-flash",
}


DEFAULT_INITIAL_PAPER_CASH = 100_000.00


def _project_root() -> Path:
    """Return the repository root independently of the caller's cwd."""
    return Path(__file__).resolve().parents[2]


class PersistenceSettings(BaseSettings):
    """Storage settings that can be loaded without configuring an LLM."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    initial_paper_cash: float = Field(default=DEFAULT_INITIAL_PAPER_CASH, gt=0)
    database_path: Path = Path("data/paper_trading.db")


class Settings(PersistenceSettings):
    """Full application settings sourced from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    llm_provider: ProviderName
    llm_model: str | None = None

    openai_model: str | None = None
    groq_model: str | None = None
    google_model: str | None = None
    nvidia_model: str | None = None

    openai_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    nvidia_api_key: SecretStr | None = None

    nvidia_base_url: str | None = None

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        """Allow provider names to be supplied in any letter case."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "llm_model",
        "openai_model",
        "groq_model",
        "google_model",
        "nvidia_model",
        mode="before",
    )
    @classmethod
    def normalize_model_name(cls, value: object) -> object:
        """Treat whitespace-only model names as unset."""
        if isinstance(value, str):
            return value.strip() or None
        return value

    @property
    def selected_model(self) -> str:
        """Return the model selected for the active provider."""
        if self.llm_model:
            return self.llm_model

        provider_model = {
            "openai": self.openai_model,
            "groq": self.groq_model,
            "google": self.google_model,
            "nvidia": self.nvidia_model,
        }[self.llm_provider]

        return provider_model or DEFAULT_MODELS[self.llm_provider]

    @property
    def selected_api_key(self) -> SecretStr | None:
        """Return the API key belonging to the active provider."""
        return {
            "openai": self.openai_api_key,
            "groq": self.groq_api_key,
            "google": self.google_api_key,
            "nvidia": self.nvidia_api_key,
        }[self.llm_provider]

    def require_api_key(self) -> str:
        """Return the active provider's key or raise a safe error."""
        secret = self.selected_api_key

        if secret is None or not secret.get_secret_value().strip():
            variable_name = {
                "openai": "OPENAI_API_KEY",
                "groq": "GROQ_API_KEY",
                "google": "GOOGLE_API_KEY",
                "nvidia": "NVIDIA_API_KEY",
            }[self.llm_provider]

            raise ValueError(
                f"Missing API key for provider '{self.llm_provider}'. "
                f"Set {variable_name} in your local .env file."
            )

        return secret.get_secret_value()

    def get_provider_summary(self) -> dict[str, str]:
        """Return safe diagnostic information without exposing credentials."""
        return {
            "provider": self.llm_provider,
            "model": self.selected_model,
            "api_key_configured": str(
                self.selected_api_key is not None
                and bool(self.selected_api_key.get_secret_value().strip())
            ),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings once per process."""
    return Settings()


def get_persistence_settings() -> PersistenceSettings:
    """Load storage settings without requiring any provider or API key.

    Process environment variables take precedence over values in the project
    root's .env, regardless of the current working directory.
    """
    return PersistenceSettings(_env_file=_project_root() / ".env")
