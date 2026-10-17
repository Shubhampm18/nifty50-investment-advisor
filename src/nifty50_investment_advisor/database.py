
"""SQLite persistence for validated research reports."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from nifty50_investment_advisor.reports import ResearchReport


def _default_database_path() -> Path:
    """Return a stable local database path in the project root."""
    # database.py is in src/nifty50_investment_advisor/.
    # parents[0] = nifty50_investment_advisor
    # parents[1] = src
    # parents[2] = project root
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "investment_advisor.db"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign-key enforcement."""
    path = Path(db_path) if db_path is not None else _default_database_path()
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
            CREATE TABLE IF NOT EXISTS trade_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                proposed_price REAL NOT NULL CHECK (proposed_price > 0),
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
