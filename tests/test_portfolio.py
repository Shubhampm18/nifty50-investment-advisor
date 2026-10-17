
import pytest

from nifty50_investment_advisor.database import initialize_database
from nifty50_investment_advisor.portfolio import (
    create_portfolio,
    create_trade_proposal,
    get_portfolio_summary,
    list_paper_trades,
    list_trade_proposals,
    review_trade_proposal,
)


@pytest.fixture
def portfolio_db(tmp_path):
    """Create an isolated SQLite database for each test."""
    db_path = tmp_path / "test_portfolio.db"
    initialize_database(db_path)
    return db_path


def test_proposal_creation_does_not_execute_trade(portfolio_db):
    portfolio_id = create_portfolio(
        name="Test Portfolio",
        initial_cash=50_000,
        db_path=portfolio_db,
    )

    proposal_id = create_trade_proposal(
        portfolio_id=portfolio_id,
        ticker="RELIANCE.NS",
        side="BUY",
        quantity=1,
        proposed_price=1_250,
        rationale="Test proposal",
        db_path=portfolio_db,
    )

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    proposals = list_trade_proposals(
        portfolio_id=portfolio_id,
        status="PENDING",
        db_path=portfolio_db,
    )
    trades = list_paper_trades(
        portfolio_id=portfolio_id,
        db_path=portfolio_db,
    )

    assert proposal_id > 0
    assert summary["cash_balance"] == 50_000
    assert summary["holdings"] == []
    assert len(proposals) == 1
    assert proposals[0]["status"] == "PENDING"
    assert trades == []


def test_approved_proposal_updates_portfolio_once(portfolio_db):
    portfolio_id = create_portfolio(
        name="Approval Test",
        initial_cash=50_000,
        db_path=portfolio_db,
    )

    proposal_id = create_trade_proposal(
        portfolio_id=portfolio_id,
        ticker="RELIANCE.NS",
        side="BUY",
        quantity=1,
        proposed_price=1_250,
        rationale="Test approved purchase",
        db_path=portfolio_db,
    )

    result = review_trade_proposal(
        proposal_id=proposal_id,
        approved=True,
        db_path=portfolio_db,
    )

    assert result["status"] == "APPROVED"
    assert result["executed"] is True
    assert result["cash_balance"] == 48_750

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    trades = list_paper_trades(
        portfolio_id=portfolio_id,
        db_path=portfolio_db,
    )

    assert summary["cash_balance"] == 48_750
    assert summary["holdings"][0]["ticker"] == "RELIANCE.NS"
    assert summary["holdings"][0]["quantity"] == 1
    assert len(trades) == 1

    with pytest.raises(ValueError, match="already been reviewed"):
        review_trade_proposal(
            proposal_id=proposal_id,
            approved=True,
            db_path=portfolio_db,
        )

    summary_after_retry = get_portfolio_summary(
        portfolio_id,
        db_path=portfolio_db,
    )
    trades_after_retry = list_paper_trades(
        portfolio_id=portfolio_id,
        db_path=portfolio_db,
    )

    assert summary_after_retry["cash_balance"] == 48_750
    assert len(trades_after_retry) == 1


def test_rejected_proposal_does_not_execute_trade(portfolio_db):
    portfolio_id = create_portfolio(
        name="Rejection Test",
        initial_cash=50_000,
        db_path=portfolio_db,
    )

    proposal_id = create_trade_proposal(
        portfolio_id=portfolio_id,
        ticker="TCS.NS",
        side="BUY",
        quantity=1,
        proposed_price=3_000,
        rationale="Test rejected purchase",
        db_path=portfolio_db,
    )

    result = review_trade_proposal(
        proposal_id=proposal_id,
        approved=False,
        db_path=portfolio_db,
    )

    assert result["status"] == "REJECTED"
    assert result["executed"] is False

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    trades = list_paper_trades(
        portfolio_id=portfolio_id,
        db_path=portfolio_db,
    )
    proposals = list_trade_proposals(
        portfolio_id=portfolio_id,
        status="REJECTED",
        db_path=portfolio_db,
    )

    assert summary["cash_balance"] == 50_000
    assert summary["holdings"] == []
    assert trades == []
    assert len(proposals) == 1


def test_approval_fails_with_insufficient_cash(portfolio_db):
    portfolio_id = create_portfolio(
        name="Insufficient Cash Test",
        initial_cash=1_000,
        db_path=portfolio_db,
    )

    proposal_id = create_trade_proposal(
        portfolio_id=portfolio_id,
        ticker="RELIANCE.NS",
        side="BUY",
        quantity=1,
        proposed_price=1_250,
        rationale="Test insufficient cash",
        db_path=portfolio_db,
    )

    with pytest.raises(ValueError):
        review_trade_proposal(
            proposal_id=proposal_id,
            approved=True,
            db_path=portfolio_db,
        )

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    trades = list_paper_trades(
        portfolio_id=portfolio_id,
        db_path=portfolio_db,
    )
    proposals = list_trade_proposals(
        portfolio_id=portfolio_id,
        status="PENDING",
        db_path=portfolio_db,
    )

    assert summary["cash_balance"] == 1_000
    assert summary["holdings"] == []
    assert trades == []
    assert len(proposals) == 1
    assert proposals[0]["status"] == "PENDING"
