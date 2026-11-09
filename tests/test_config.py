"""Persistence configuration tests use only temporary paths and process env."""

import sqlite3
from argparse import ArgumentParser
from pathlib import Path

from nifty50_investment_advisor import cli, config, database
from nifty50_investment_advisor.config import get_persistence_settings
from nifty50_investment_advisor.portfolio import create_portfolio


def _use_temporary_project(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    caller_directory = tmp_path / "caller"
    project_root.mkdir()
    caller_directory.mkdir()
    monkeypatch.setattr(config, "_project_root", lambda: project_root)
    monkeypatch.setattr(database, "_project_root", lambda: project_root)
    monkeypatch.chdir(caller_directory)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("INITIAL_PAPER_CASH", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    return project_root, caller_directory


def _write_project_dotenv(project_root, *, database_path, initial_cash):
    (project_root / ".env").write_text(
        f"DATABASE_PATH={database_path}\nINITIAL_PAPER_CASH={initial_cash}\n",
        encoding="utf-8",
    )


def test_persistence_settings_load_without_llm_configuration(monkeypatch, tmp_path):
    project_root, caller_directory = _use_temporary_project(monkeypatch, tmp_path)
    _write_project_dotenv(
        project_root,
        database_path="configured/ledger.sqlite3",
        initial_cash="76543.25",
    )

    settings = get_persistence_settings()

    assert settings.database_path.as_posix() == "configured/ledger.sqlite3"
    assert settings.initial_paper_cash == 76543.25
    database.initialize_database()
    portfolio_id = create_portfolio(name="From project dotenv")

    configured_path = project_root / "configured" / "ledger.sqlite3"
    assert configured_path.is_file()
    assert not (caller_directory / "configured" / "ledger.sqlite3").exists()
    with sqlite3.connect(configured_path) as connection:
        row = connection.execute(
            "SELECT initial_cash FROM paper_portfolios WHERE id = ?",
            (portfolio_id,),
        ).fetchone()
    assert row == (76543.25,)


def test_process_environment_overrides_project_dotenv(monkeypatch, tmp_path):
    project_root, _ = _use_temporary_project(monkeypatch, tmp_path)
    _write_project_dotenv(
        project_root,
        database_path="from-dotenv/ledger.sqlite3",
        initial_cash="11111",
    )
    monkeypatch.setenv("DATABASE_PATH", "from-environment/ledger.sqlite3")
    monkeypatch.setenv("INITIAL_PAPER_CASH", "22222")

    settings = get_persistence_settings()
    database.initialize_database()
    create_portfolio(name="From environment")

    environment_path = project_root / "from-environment" / "ledger.sqlite3"
    dotenv_path = project_root / "from-dotenv" / "ledger.sqlite3"
    assert settings.database_path.as_posix() == "from-environment/ledger.sqlite3"
    assert settings.initial_paper_cash == 22222
    assert environment_path.is_file()
    assert not dotenv_path.exists()
    with sqlite3.connect(environment_path) as connection:
        row = connection.execute(
            "SELECT initial_cash FROM paper_portfolios"
        ).fetchone()
    assert row == (22222.0,)


def test_configured_relative_database_path_and_explicit_override(
    monkeypatch, tmp_path
):
    project_root, working_directory = _use_temporary_project(monkeypatch, tmp_path)
    monkeypatch.setenv("DATABASE_PATH", "configured/ledger.sqlite3")

    database.initialize_database()

    configured_path = project_root / "configured" / "ledger.sqlite3"
    assert configured_path.is_file()
    assert not (working_directory / "configured" / "ledger.sqlite3").exists()

    explicit_path = tmp_path / "caller-selected.sqlite3"
    database.initialize_database(explicit_path)

    assert explicit_path.is_file()
    with sqlite3.connect(explicit_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "paper_portfolios" in tables


def test_portfolio_default_cash_uses_setting_and_explicit_cash_wins(
    monkeypatch, tmp_path
):
    _use_temporary_project(monkeypatch, tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "cash.sqlite3"))
    monkeypatch.setenv("INITIAL_PAPER_CASH", "43210")

    configured_id = create_portfolio(name="Configured cash")
    explicit_id = create_portfolio(name="Explicit cash", initial_cash=12345)

    with sqlite3.connect(tmp_path / "cash.sqlite3") as connection:
        rows = connection.execute(
            "SELECT name, initial_cash FROM paper_portfolios ORDER BY id"
        ).fetchall()

    assert rows == [
        ("Configured cash", 43210.0),
        ("Explicit cash", 12345.0),
    ]
    assert configured_id == 1
    assert explicit_id == 2


def test_cli_portfolio_cash_default_uses_shared_setting(monkeypatch, tmp_path):
    _use_temporary_project(monkeypatch, tmp_path)
    monkeypatch.setenv("INITIAL_PAPER_CASH", "98765.5")
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    cli._add_portfolio_commands(subparsers)

    args = parser.parse_args(["portfolio-create"])

    assert args.cash == 98765.5


def test_relative_explicit_database_override_resolves_from_caller_directory(
    monkeypatch, tmp_path
):
    _, caller_directory = _use_temporary_project(monkeypatch, tmp_path)
    explicit_path = Path("caller-selected/override.sqlite3")

    database.initialize_database(explicit_path)

    assert (caller_directory / explicit_path).is_file()

