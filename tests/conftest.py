"""Shared test isolation: keep the developer's real .env out of unit tests.

Settings reads ``.env`` from the current directory by default, which would
inject the developer's provider/model choices into every test that builds a
Settings object. The settings tests construct Settings without naming an
env file, so they must not depend on the local .env existing or matching.
"""

import pytest

from nifty50_investment_advisor import config


@pytest.fixture(autouse=True)
def _isolate_settings_env_file(monkeypatch):
    patched_config = config.Settings.model_config.copy()
    patched_config["env_file"] = None
    monkeypatch.setattr(
        config.Settings, "model_config", patched_config, raising=False
    )
