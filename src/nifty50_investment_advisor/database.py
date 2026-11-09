
"""SQLite persistence for validated research reports."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from nifty50_investment_advisor.config import get_persistence_settings
from nifty50_investment_advisor.reports import (
    ResearchReport,
    StockComparisonReport,
)


def _project_root() -> Path:
    """Return the project root used to resolve configured relative paths."""
    return Path(__file__).resolve().parents[2]


def _default_database_path() -> Path:
    """Resolve the configured database path, relative to the project root."""
    configured_path = get_persistence_settings().database_path.expanduser()
    if configured_path.is_absolute():
        return configured_path
    return _project_root() / configured_path


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign-key enforcement."""
    # Explicit overrides retain normal Path resolution from the caller's cwd.
    path = Path(db_path).expanduser() if db_path is not None else _default_database_path()
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path | None = None) -> None:
    """Create the database schema if it does not already exist."""
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                initial_cash REAL NOT NULL CHECK (initial_cash >= 0),
                cash_balance REAL NOT NULL CHECK (cash_balance >= 0),
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                research_question TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tickers_json TEXT NOT NULL,
                research_question TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                proposed_price REAL NOT NULL CHECK (proposed_price > 0),
                transaction_cost_bps REAL NOT NULL DEFAULT 0
                    CHECK (transaction_cost_bps >= 0),
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
                rationale TEXT NOT NULL,
                research_report_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                reviewed_at TEXT,
                FOREIGN KEY (portfolio_id)
                    REFERENCES paper_portfolios(id),
                FOREIGN KEY (research_report_id)
                    REFERENCES research_reports(id)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                proposal_id INTEGER NOT NULL UNIQUE,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                execution_price REAL NOT NULL CHECK (execution_price > 0),
                total_value REAL NOT NULL CHECK (total_value > 0),
                fee_bps REAL NOT NULL DEFAULT 0 CHECK (fee_bps >= 0),
                fee_amount REAL NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
                realized_pnl REAL NOT NULL DEFAULT 0,
                executed_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                FOREIGN KEY (portfolio_id)
                    REFERENCES paper_portfolios(id),
                FOREIGN KEY (proposal_id)
                    REFERENCES trade_proposals(id)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_holdings (
                portfolio_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                average_cost REAL NOT NULL CHECK (average_cost > 0),
                PRIMARY KEY (portfolio_id, ticker),
                FOREIGN KEY (portfolio_id)
                    REFERENCES paper_portfolios(id)
            )
            """
        )

        # Add cost fields to existing local ledgers without dropping history.
        proposal_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(trade_proposals)"
            ).fetchall()
        }
        if "transaction_cost_bps" not in proposal_columns:
            connection.execute(
                "ALTER TABLE trade_proposals ADD COLUMN "
                "transaction_cost_bps REAL NOT NULL DEFAULT 0"
            )

        trade_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(paper_trades)"
            ).fetchall()
        }
        for column, definition in (
            ("fee_bps", "REAL NOT NULL DEFAULT 0"),
            ("fee_amount", "REAL NOT NULL DEFAULT 0"),
            ("realized_pnl", "REAL NOT NULL DEFAULT 0"),
        ):
            if column not in trade_columns:
                connection.execute(
                    f"ALTER TABLE paper_trades ADD COLUMN {column} {definition}"
                )



def save_research_report(
    report: ResearchReport | dict[str, Any],
    db_path: str | Path | None = None,
) -> int:
    """Validate and save a report; return its database ID."""
    validated = (
        report
        if isinstance(report, ResearchReport)
        else ResearchReport.model_validate(report)
    )

    report_json = validated.model_dump_json()
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO research_reports (
                ticker,
                company_name,
                research_question,
                generated_at,
                report_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                validated.ticker,
                validated.company_name,
                validated.research_question,
                validated.generated_at.isoformat(),
                report_json,
            ),
        )
        report_id = cursor.lastrowid

    if report_id is None:
        raise RuntimeError("SQLite did not return an ID for the saved report.")

    return int(report_id)


def get_research_report(
    report_id: int,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve a saved report by ID, or return None if it does not exist."""
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, report_json, created_at
            FROM research_reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()

    if row is None:
        return None

    report = json.loads(row["report_json"])
    report["id"] = row["id"]
    report["stored_at"] = row["created_at"]
    return report


def list_research_reports(
    limit: int = 20,
    ticker: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List recent reports, optionally filtered by ticker."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500.")

    query = """
        SELECT id, ticker, company_name, research_question,
               generated_at, created_at
        FROM research_reports
    """
    parameters: list[Any] = []

    if ticker:
        query += " WHERE ticker = ?"
        parameters.append(ticker.strip().upper())

    query += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)

    with _connect(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [
        {
            "id": row["id"],
            "ticker": row["ticker"],
            "company_name": row["company_name"],
            "research_question": row["research_question"],
            "generated_at": row["generated_at"],
            "stored_at": row["created_at"],
        }
        for row in rows
    ]


def save_stock_comparison(
    report: StockComparisonReport | dict[str, Any],
    db_path: str | Path | None = None,
) -> int:
    """Validate and save a multi-stock comparison in its own typed table."""
    validated = (
        report
        if isinstance(report, StockComparisonReport)
        else StockComparisonReport.model_validate(report)
    )
    report_json = validated.model_dump_json()
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO stock_comparisons (
                tickers_json,
                research_question,
                generated_at,
                report_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                json.dumps(validated.tickers),
                validated.research_question,
                validated.generated_at.isoformat(),
                report_json,
            ),
        )
        comparison_id = cursor.lastrowid

    if comparison_id is None:
        raise RuntimeError("SQLite did not return an ID for the saved comparison.")
    return int(comparison_id)


def get_stock_comparison(
    comparison_id: int,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve a saved typed comparison by ID, or return None if absent."""
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, report_json, created_at
            FROM stock_comparisons
            WHERE id = ?
            """,
            (comparison_id,),
        ).fetchone()

    if row is None:
        return None
    report = StockComparisonReport.model_validate_json(row["report_json"]).model_dump(
        mode="json"
    )
    report["id"] = row["id"]
    report["stored_at"] = row["created_at"]
    report["report_type"] = "comparison"
    return report


def list_stock_comparisons(
    limit: int = 20,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List saved comparisons with their complete ticker sets."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500.")

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, tickers_json, research_question, generated_at, created_at
            FROM stock_comparisons
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "report_type": "comparison",
            "tickers": json.loads(row["tickers_json"]),
            "research_question": row["research_question"],
            "generated_at": row["generated_at"],
            "stored_at": row["created_at"],
        }
        for row in rows
    ]
