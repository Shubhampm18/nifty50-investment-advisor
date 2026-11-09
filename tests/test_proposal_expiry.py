"""Proposal expiry tests: approval after the deadline is rejected."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from nifty50_investment_advisor.database import initialize_database
from nifty50_investment_advisor.portfolio import (
    create_portfolio,
    create_trade_proposal,
    list_trade_proposals,
    review_trade_proposal,
)
from nifty50_investment_advisor.database import _connect


@pytest.fixture
def portfolio_db(tmp_path):
    db_path = tmp_path / "test_expiry.db"
    initialize_database(db_path)
    return db_path


def test_new_proposal_carries_expiry_timestamp(portfolio_db):
    portfolio_id = create_portfolio(
        name="Expiry Test", initial_cash=10_000, db_path=portfolio_db
    )
    proposal_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        1,
        100,
        "Expiry check",
        db_path=portfolio_db,
    )
    proposals = list_trade_proposals(portfolio_id, db_path=portfolio_db)
    assert proposals[0]["id"] == proposal_id
    assert proposals[0]["expires_at"] is not None
    # Default expiry is 7 days in the future.
    expires = datetime.fromisoformat(proposals[0]["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    assert expires > datetime.now(UTC)


def test_custom_expiry_days_respected(portfolio_db):
    portfolio_id = create_portfolio(
        name="Custom Expiry", initial_cash=10_000, db_path=portfolio_db
    )
    create_trade_proposal(
        portfolio_id,
        "TCS.NS",
        "BUY",
        1,
        100,
        "1 day expiry",
        db_path=portfolio_db,
        expiry_days=1,
    )
    proposals = list_trade_proposals(portfolio_id, db_path=portfolio_db)
    expires = datetime.fromisoformat(proposals[0]["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    remaining = expires - datetime.now(UTC)
    assert timedelta(hours=12) < remaining <= timedelta(days=1, hours=1)


def test_expired_proposal_cannot_be_approved(portfolio_db):
    portfolio_id = create_portfolio(
        name="Expired", initial_cash=10_000, db_path=portfolio_db
    )
    proposal_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        1,
        100,
        "Will expire",
        db_path=portfolio_db,
    )
    # Backdate the expiry to yesterday.
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    with _connect(portfolio_db) as connection:
        connection.execute(
            "UPDATE trade_proposals SET expires_at = ? WHERE id = ?",
            (past, proposal_id),
        )

    with pytest.raises(ValueError, match="expired"):
        review_trade_proposal(proposal_id, approved=True, db_path=portfolio_db)

    # The proposal is still PENDING and can be rejected after expiry.
    proposals = list_trade_proposals(portfolio_id, db_path=portfolio_db)
    assert proposals[0]["status"] == "PENDING"
    result = review_trade_proposal(proposal_id, approved=False, db_path=portfolio_db)
    assert result["status"] == "REJECTED"


def test_unexpired_proposal_approves_normally(portfolio_db):
    portfolio_id = create_portfolio(
        name="Valid", initial_cash=10_000, db_path=portfolio_db
    )
    proposal_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        1,
        100,
        "Still valid",
        db_path=portfolio_db,
    )
    result = review_trade_proposal(proposal_id, approved=True, db_path=portfolio_db)
    assert result["executed"] is True


def test_old_database_without_expiry_column_migrates(portfolio_db):
    # Simulate an old ledger: drop the column state by re-creating a minimal
    # table without expires_at, then re-initializing.
    db_path = portfolio_db
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS _old_proposals_backup AS SELECT * FROM trade_proposals"
        )
    initialize_database(db_path)
    initialize_database(db_path)  # idempotent re-run
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(trade_proposals)")}
    assert "expires_at" in columns
