
"""Safe SQLite-backed paper portfolio and trade proposal operations."""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from nifty50_investment_advisor.database import (
    _connect,
    initialize_database,
)

DEFAULT_INITIAL_CASH = 1_000_000.00
DEFAULT_PORTFOLIO_NAME = "My NIFTY 50 Portfolio"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _positive_integer(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer.")
    return value


def _positive_amount(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a positive number.")

    amount = float(value)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError(f"{field} must be a finite positive number.")

    return amount


def _clean_ticker(ticker: str) -> str:
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker must be a non-empty string.")
    return ticker.strip().upper()


@contextmanager
def _transaction(
    db_path: str | Path | None = None,
) -> Iterator[sqlite3.Connection]:
    """Run database changes atomically, acquiring a write lock first."""
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_portfolio(
    name: str = DEFAULT_PORTFOLIO_NAME,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    db_path: str | Path | None = None,
) -> int:
    """Create a virtual portfolio and return its ID."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Portfolio name cannot be empty.")

    if isinstance(initial_cash, bool) or not isinstance(
        initial_cash, (int, float)
    ):
        raise ValueError("Initial cash must be a non-negative number.")

    initial_cash = float(initial_cash)
    if not math.isfinite(initial_cash) or initial_cash < 0:
        raise ValueError("Initial cash must be finite and non-negative.")

    initialize_database(db_path)

    try:
        with _transaction(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_portfolios
                    (name, initial_cash, cash_balance, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name.strip(), initial_cash, initial_cash, _now()),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"A portfolio named '{name.strip()}' may already exist."
        ) from exc


def get_portfolio(
    portfolio_id: int,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return one portfolio, or None if it does not exist."""
    initialize_database(db_path)

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, name, initial_cash, cash_balance, created_at
            FROM paper_portfolios
            WHERE id = ?
            """,
            (portfolio_id,),
        ).fetchone()

    return dict(row) if row else None


def list_portfolios(
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List portfolios, newest first."""
    initialize_database(db_path)

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, name, initial_cash, cash_balance, created_at
            FROM paper_portfolios
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def create_trade_proposal(
    portfolio_id: int,
    ticker: str,
    side: str,
    quantity: int,
    proposed_price: float,
    rationale: str,
    research_report_id: int | None = None,
    db_path: str | Path | None = None,
) -> int:
    """
    Submit a pending proposal. This function never executes a trade.

    A human must explicitly approve the proposal through
    review_trade_proposal() before cash or holdings can change.
    """
    ticker = _clean_ticker(ticker)
    side = side.strip().upper() if isinstance(side, str) else ""
    if side not in {"BUY", "SELL"}:
        raise ValueError("Side must be BUY or SELL.")

    quantity = _positive_integer(quantity, "Quantity")
    proposed_price = _positive_amount(proposed_price, "Proposed price")

    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("A non-empty rationale is required.")

    if research_report_id is not None:
        research_report_id = _positive_integer(
            research_report_id, "Research report ID"
        )

    initialize_database(db_path)

    with _transaction(db_path) as connection:
        portfolio = connection.execute(
            "SELECT id FROM paper_portfolios WHERE id = ?",
            (portfolio_id,),
        ).fetchone()

        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} does not exist.")

        if research_report_id is not None:
            report = connection.execute(
                """
                SELECT id, ticker
                FROM research_reports
                WHERE id = ?
                """,
                (research_report_id,),
            ).fetchone()

            if report is None:
                raise ValueError(
                    f"Research report {research_report_id} does not exist."
                )

            if report["ticker"].upper() != ticker:
                raise ValueError(
                    "The research report ticker does not match "
                    "the proposed trade ticker."
                )

        cursor = connection.execute(
            """
            INSERT INTO trade_proposals (
                portfolio_id, ticker, side, quantity, proposed_price,
                status, rationale, research_report_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
            """,
            (
                portfolio_id,
                ticker,
                side,
                quantity,
                proposed_price,
                rationale.strip(),
                research_report_id,
                _now(),
            ),
        )

        return int(cursor.lastrowid)


def list_trade_proposals(
    portfolio_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List proposals with optional portfolio and status filters."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Limit must be an integer between 1 and 500.")

    if status is not None:
        status = status.strip().upper()
        if status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ValueError("Status must be PENDING, APPROVED, or REJECTED.")

    initialize_database(db_path)

    query = "SELECT * FROM trade_proposals WHERE 1 = 1"
    parameters: list[Any] = []

    if portfolio_id is not None:
        query += " AND portfolio_id = ?"
        parameters.append(portfolio_id)

    if status is not None:
        query += " AND status = ?"
        parameters.append(status)

    query += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)

    with _connect(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [dict(row) for row in rows]


def review_trade_proposal(
    proposal_id: int,
    approved: bool,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Approve or reject a pending proposal.

    Approval executes a simulated trade at the proposed price.
    Cash, holdings, trade history, and proposal status are updated
    in one transaction. Rejected proposals have no financial effect.
    """
    proposal_id = _positive_integer(proposal_id, "Proposal ID")

    if not isinstance(approved, bool):
        raise ValueError("Approved must be True or False.")

    initialize_database(db_path)

    with _transaction(db_path) as connection:
        proposal = connection.execute(
            """
            SELECT *
            FROM trade_proposals
            WHERE id = ?
            """,
            (proposal_id,),
        ).fetchone()

        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} does not exist.")

        if proposal["status"] != "PENDING":
            raise ValueError(
                f"Proposal {proposal_id} has already been reviewed."
            )

        reviewed_at = _now()

        if not approved:
            connection.execute(
                """
                UPDATE trade_proposals
                SET status = 'REJECTED', reviewed_at = ?
                WHERE id = ? AND status = 'PENDING'
                """,
                (reviewed_at, proposal_id),
            )
            return {
                "proposal_id": proposal_id,
                "status": "REJECTED",
                "executed": False,
            }

        portfolio = connection.execute(
            """
            SELECT *
            FROM paper_portfolios
            WHERE id = ?
            """,
            (proposal["portfolio_id"],),
        ).fetchone()

        if portfolio is None:
            raise ValueError("The proposal's portfolio does not exist.")

        ticker = proposal["ticker"]
        side = proposal["side"]
        quantity = int(proposal["quantity"])
        price = float(proposal["proposed_price"])
        total_value = round(quantity * price, 2)

        holding = connection.execute(
            """
            SELECT quantity, average_cost
            FROM paper_holdings
            WHERE portfolio_id = ? AND ticker = ?
            """,
            (proposal["portfolio_id"], ticker),
        ).fetchone()

        cash = round(float(portfolio["cash_balance"]), 2)
        trade_id: int

        if side == "BUY":
            if cash + 1e-9 < total_value:
                raise ValueError(
                    f"Insufficient cash: available ₹{cash:,.2f}, "
                    f"required ₹{total_value:,.2f}."
                )

            new_cash = round(cash - total_value, 2)
            old_quantity = int(holding["quantity"]) if holding else 0
            old_average_cost = (
                float(holding["average_cost"]) if holding else 0.0
            )
            new_quantity = old_quantity + quantity
            new_average_cost = round(
                (
                    old_quantity * old_average_cost
                    + quantity * price
                ) / new_quantity,
                4,
            )

            connection.execute(
                """
                UPDATE paper_portfolios
                SET cash_balance = ?
                WHERE id = ?
                """,
                (new_cash, proposal["portfolio_id"]),
            )

            connection.execute(
                """
                INSERT INTO paper_holdings
                    (portfolio_id, ticker, quantity, average_cost)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(portfolio_id, ticker)
                DO UPDATE SET
                    quantity = excluded.quantity,
                    average_cost = excluded.average_cost
                """,
                (
                    proposal["portfolio_id"],
                    ticker,
                    new_quantity,
                    new_average_cost,
                ),
            )

        else:  # SELL
            if holding is None or int(holding["quantity"]) < quantity:
                available = int(holding["quantity"]) if holding else 0
                raise ValueError(
                    f"Insufficient shares of {ticker}: "
                    f"available {available}, requested {quantity}."
                )

            remaining = int(holding["quantity"]) - quantity
            new_cash = round(cash + total_value, 2)

            connection.execute(
                """
                UPDATE paper_portfolios
                SET cash_balance = ?
                WHERE id = ?
                """,
                (new_cash, proposal["portfolio_id"]),
            )

            if remaining == 0:
                connection.execute(
                    """
                    DELETE FROM paper_holdings
                    WHERE portfolio_id = ? AND ticker = ?
                    """,
                    (proposal["portfolio_id"], ticker),
                )
            else:
                connection.execute(
                    """
                    UPDATE paper_holdings
                    SET quantity = ?
                    WHERE portfolio_id = ? AND ticker = ?
                    """,
                    (remaining, proposal["portfolio_id"], ticker),
                )

        cursor = connection.execute(
            """
            INSERT INTO paper_trades (
                portfolio_id, proposal_id, ticker, side, quantity,
                execution_price, total_value, executed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal["portfolio_id"],
                proposal_id,
                ticker,
                side,
                quantity,
                price,
                total_value,
                reviewed_at,
            ),
        )
        trade_id = int(cursor.lastrowid)

        updated = connection.execute(
            """
            UPDATE trade_proposals
            SET status = 'APPROVED', reviewed_at = ?
            WHERE id = ? AND status = 'PENDING'
            """,
            (reviewed_at, proposal_id),
        )

        if updated.rowcount != 1:
            raise ValueError("Proposal is no longer pending.")

        return {
            "proposal_id": proposal_id,
            "trade_id": trade_id,
            "portfolio_id": proposal["portfolio_id"],
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "execution_price": price,
            "total_value": total_value,
            "cash_balance": new_cash,
            "status": "APPROVED",
            "executed": True,
        }


def get_portfolio_summary(
    portfolio_id: int,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return cash, holdings, and basic portfolio totals.

    Market value and unrealized profit/loss are intentionally omitted:
    they require current market prices, not just average purchase costs.
    """
    portfolio = get_portfolio(portfolio_id, db_path)
    if portfolio is None:
        raise ValueError(f"Portfolio {portfolio_id} does not exist.")

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT ticker, quantity, average_cost
            FROM paper_holdings
            WHERE portfolio_id = ?
            ORDER BY ticker
            """,
            (portfolio_id,),
        ).fetchall()

    holdings = []
    invested_cost = 0.0

    for row in rows:
        item = dict(row)
        item["cost_basis"] = round(
            item["quantity"] * item["average_cost"], 2
        )
        invested_cost += item["cost_basis"]
        holdings.append(item)

    return {
        "portfolio": portfolio,
        "cash_balance": round(float(portfolio["cash_balance"]), 2),
        "holdings": holdings,
        "holdings_count": len(holdings),
        "invested_cost_basis": round(invested_cost, 2),
        "initial_cash": float(portfolio["initial_cash"]),
    }


def list_paper_trades(
    portfolio_id: int | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List executed paper trades, newest first."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Limit must be an integer between 1 and 500.")

    initialize_database(db_path)

    query = "SELECT * FROM paper_trades WHERE 1 = 1"
    parameters: list[Any] = []

    if portfolio_id is not None:
        query += " AND portfolio_id = ?"
        parameters.append(portfolio_id)

    query += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)

    with _connect(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [dict(row) for row in rows]
