
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


def test_user_cost_assumptions_affect_cash_basis_and_realized_profit(portfolio_db):
    portfolio_id = create_portfolio(
        name="Cost Assumptions",
        initial_cash=10_000,
        db_path=portfolio_db,
    )
    buy_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        10,
        100,
        "Test fee-inclusive cost basis",
        db_path=portfolio_db,
        transaction_cost_bps=50,
    )
    buy = review_trade_proposal(buy_id, approved=True, db_path=portfolio_db)
    assert buy["fee_amount"] == 5.0
    assert buy["cash_balance"] == 8_995.0

    sell_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "SELL",
        4,
        120,
        "Test realized P&L net of costs",
        db_path=portfolio_db,
        transaction_cost_bps=100,
    )
    sell = review_trade_proposal(sell_id, approved=True, db_path=portfolio_db)
    assert sell["fee_amount"] == 4.8
    assert sell["realized_pnl"] == 73.2
    assert sell["cash_balance"] == 9_470.2

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    assert summary["holdings"][0]["quantity"] == 6
    assert summary["holdings"][0]["average_cost"] == 100.5
    assert summary["realized_pnl"] == 73.2
    assert summary["total_fees"] == 9.8
    trades = list_paper_trades(portfolio_id, db_path=portfolio_db)
    assert [trade["fee_bps"] for trade in reversed(trades)] == [50.0, 100.0]


def test_transaction_cost_rate_is_validated(portfolio_db):
    portfolio_id = create_portfolio(
        name="Invalid Fee Rate",
        initial_cash=1_000,
        db_path=portfolio_db,
    )
    for invalid in (-1, 10_001, float("inf")):
        with pytest.raises(ValueError, match="0 to 10,000 bps"):
            create_trade_proposal(
                portfolio_id,
                "RELIANCE.NS",
                "BUY",
                1,
                100,
                "Invalid cost rate",
                db_path=portfolio_db,
                transaction_cost_bps=invalid,
            )
