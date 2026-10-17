"""Verify that the configured LLM provider can answer a real request."""

import sys

from pydantic import ValidationError

from nifty50_investment_advisor.config import get_settings
from nifty50_investment_advisor.model_provider import create_chat_model


def main() -> int:
    """Run a real model connectivity test."""
    try:
        settings = get_settings()

        # Print provider and model, never credentials.
        summary = settings.get_provider_summary()
        print(f"Provider: {summary['provider']}")
        print(f"Model: {summary['model']}")
        print(f"API key configured: {summary['api_key_configured']}")

        model = create_chat_model(settings)

        print("\nSending a real request to the configured provider...")

        response = model.invoke("Reply with exactly this text: LLM_CONNECTION_OK")

        content = response.content

        if isinstance(content, str):
            response_text = content.strip()
        elif isinstance(content, list):
            response_text = " ".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            ).strip()
        else:
            response_text = ""

        if not response_text:
            print("ERROR: The model returned no readable text.")
            return 1

        print("\nLive API request succeeded.")
        print(f"Response: {response_text}")

        # Some models may add punctuation or a short explanation.
        # The actual response is displayed rather than fabricated.
        return 0

    except ValidationError as exc:
        print("Configuration validation failed.")
        print(exc)
        return 1

    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 1

    except Exception as exc:
        # Do not dump request headers or credential-bearing objects.
        print(f"Live LLM request failed: {type(exc).__name__}: {exc}")
        print(
            "Check the provider, model ID, API key, account access, "
            "network connection, and provider rate limits."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
