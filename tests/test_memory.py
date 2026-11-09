import sys

import pytest

from nifty50_investment_advisor import agent, cli, config, database, memory
from nifty50_investment_advisor.agent import (
    MAIN_SYSTEM_PROMPT,
    PROJECT_ROOT,
    SENSITIVE_PATH_RULES,
    create_agent_backend,
)
from nifty50_investment_advisor.database import _default_database_path


def _use_temporary_database_project(monkeypatch, tmp_path):
    project_root = tmp_path / "database-project"
    project_root.mkdir()
    monkeypatch.setattr(config, "_project_root", lambda: project_root)
    monkeypatch.setattr(database, "_project_root", lambda: project_root)


def test_preferences_persist_across_memory_backend_recreation(tmp_path):
    memory_directory = tmp_path / "private-memory"
    first_backend = memory.create_memory_backend(memory_directory)
    preference = "# Saved user preferences\n\n- Prefers concise research summaries.\n"

    write_result = first_backend.write("/PREFERENCES.md", preference)
    second_backend = memory.create_memory_backend(memory_directory)
    read_result = second_backend.read("/PREFERENCES.md")

    assert write_result.error is None
    assert read_result.file_data is not None
    assert read_result.file_data["content"] == preference


def test_default_memory_path_is_per_user_and_separate_from_project_and_ledger(
    monkeypatch, tmp_path
):
    _use_temporary_database_project(monkeypatch, tmp_path)
    memory_directory = memory.default_memory_directory().resolve()
    database_path = _default_database_path().resolve()

    assert not memory_directory.is_relative_to(PROJECT_ROOT.resolve())
    assert not database_path.is_relative_to(memory_directory)
    assert memory_directory != database_path.parent


def test_agent_routes_memory_to_isolated_filesystem_backend(monkeypatch, tmp_path):
    _use_temporary_database_project(monkeypatch, tmp_path)
    memory_directory = tmp_path / "memory-outside-project"
    backend = create_agent_backend(memory_directory=memory_directory)
    preference = "# Saved user preferences\n\n- Likes short reports.\n"

    write_result = backend.write(memory.PREFERENCES_MEMORY_PATH, preference)
    stored_path = memory_directory / memory.PREFERENCES_FILENAME
    download_result = backend.download_files([memory.PREFERENCES_MEMORY_PATH])[0]
    delete_result = backend.delete(memory.PREFERENCES_MEMORY_PATH)

    assert write_result.error is None
    assert backend.default.cwd == PROJECT_ROOT.resolve()
    assert backend.routes["/memories/"].cwd == memory_directory.resolve()
    assert stored_path.read_text(encoding="utf-8") == preference
    assert download_result.content == preference.encode("utf-8")
    assert not stored_path.is_relative_to(PROJECT_ROOT.resolve())
    assert not stored_path.is_relative_to(_default_database_path().resolve().parent)
    assert "memory-clear --confirm" in delete_result.error


def test_investment_agent_uses_native_memory_parameter(monkeypatch, tmp_path):
    backend = create_agent_backend(memory_directory=tmp_path / "agent-memory")
    monkeypatch.setattr(agent, "create_chat_model", lambda: object())
    monkeypatch.setattr(agent, "create_agent_backend", lambda: backend)
    monkeypatch.setattr(agent, "create_deep_agent", lambda **kwargs: kwargs)

    configuration = agent.create_investment_agent(include_news_subagent=False)

    assert configuration["memory"] == [memory.PREFERENCES_MEMORY_PATH]
    assert configuration["backend"] is backend
    assert configuration["skills"] == [agent.SKILLS_SOURCE]


def test_memory_cli_inspects_and_requires_confirmation_to_clear(
    tmp_path,
    monkeypatch,
    capsys,
):
    memory_directory = tmp_path / "cli-memory"
    backend = memory.create_memory_backend(memory_directory)
    preference = (
        "# Saved user preferences\n\n"
        "- Interested in semiconductor research.\n"
    )
    assert backend.write("/PREFERENCES.md", preference).error is None

    monkeypatch.setattr(memory, "default_memory_directory", lambda: memory_directory)
    monkeypatch.setattr(
        cli,
        "initialize_database",
        lambda: pytest.fail("Memory commands must not initialize the trading database."),
    )
    monkeypatch.setattr(sys, "argv", ["nifty50-advisor", "memory-show"])
    cli.main()
    assert preference.strip() in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["nifty50-advisor", "memory-clear"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 2
    assert memory.read_preferences(memory_directory) == preference

    monkeypatch.setattr(
        sys,
        "argv",
        ["nifty50-advisor", "memory-clear", "--confirm"],
    )
    cli.main()
    assert "cleared" in capsys.readouterr().out.lower()
    assert memory.read_preferences(memory_directory) == memory.PREFERENCES_TEMPLATE


def test_agent_memory_policy_requires_an_explicit_request():
    assert "only when the current user explicitly asks" in MAIN_SYSTEM_PROMPT
    assert "Ordinary requests, feedback, corrections, and personal" in MAIN_SYSTEM_PROMPT
    assert any(
        rule.mode == "deny" and rule.paths == ["/memories/**"]
        for rule in SENSITIVE_PATH_RULES
    )
