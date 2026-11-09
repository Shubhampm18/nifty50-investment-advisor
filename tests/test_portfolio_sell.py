"""Portfolio SELL paths and validation error tests."""

import pytest

from nifty50_investment_advisor.database import (
    initialize_database,
    save_research_report,
)
from nifty50_investment_advisor.portfolio import (
    create_portfolio,
    create_trade_proposal,
    get_portfolio_summary,
    list_paper_trades,
    review_trade_proposal,
)
from nifty50_investment_advisor.reports import ResearchReport


@pytest.fixture
def portfolio_db(tmp_path):
    db_path = tmp_path / "test_sell.db"
    initialize_database(db_path)
    return db_path


def _create_with_holding(portfolio_db, quantity=10, price=100):
    portfolio_id = create_portfolio(
        name="Sell Test",
        initial_cash=50_000,
        db_path=portfolio_db,
    )
    buy_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        quantity,
        price,
        "Seed holding",
        db_path=portfolio_db,
    )
    review_trade_proposal(buy_id, approved=True, db_path=portfolio_db)
    return portfolio_id


def test_sell_more_than_held_fails_and_stays_pending(portfolio_db):
    portfolio_id = _create_with_holding(portfolio_db, quantity=5)

    sell_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "SELL",
        10,
        120,
        "Oversell attempt",
        db_path=portfolio_db,
    )
    with pytest.raises(ValueError, match="Insufficient shares"):
        review_trade_proposal(sell_id, approved=True, db_path=portfolio_db)

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    assert summary["holdings"][0]["quantity"] == 5
    trades = list_paper_trades(portfolio_id, db_path=portfolio_db)
    assert len(trades) == 1  # only the seed BUY


def test_sell_without_holding_fails(portfolio_db):
    portfolio_id = create_portfolio(
        name="No Holdings",
        initial_cash=10_000,
        db_path=portfolio_db,
    )
    sell_id = create_trade_proposal(
        portfolio_id,
        "TCS.NS",
        "SELL",
        1,
        300,
        "No holding to sell",
        db_path=portfolio_db,
    )
    with pytest.raises(ValueError, match="Insufficient shares"):
        review_trade_proposal(sell_id, approved=True, db_path=portfolio_db)


def test_sell_to_zero_deletes_holding_and_credits_cash(portfolio_db):
    portfolio_id = _create_with_holding(portfolio_db, quantity=3, price=100)
    summary_before = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    cash_before = summary_before["cash_balance"]

    sell_id = create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "SELL",
        3,
        110,
        "Full exit",
        db_path=portfolio_db,
    )
    result = review_trade_proposal(sell_id, approved=True, db_path=portfolio_db)

    assert result["executed"] is True
    assert result["cash_balance"] == cash_before + 330.0
    assert result["realized_pnl"] == 30.0

    summary = get_portfolio_summary(portfolio_id, db_path=portfolio_db)
    assert summary["holdings"] == []
    assert summary["realized_pnl"] == 30.0


def test_missing_portfolio_rejected(portfolio_db):
    with pytest.raises(ValueError, match="does not exist"):
        create_trade_proposal(
            999,
            "RELIANCE.NS",
            "BUY",
            1,
            100,
            "Missing portfolio",
            db_path=portfolio_db,
        )


def test_report_ticker_mismatch_rejected(portfolio_db):
    portfolio_id = create_portfolio(
        name="Mismatch Test",
        initial_cash=10_000,
        db_path=portfolio_db,
    )
    report = ResearchReport(
        ticker="TCS.NS",
        company_name="TCS",
        research_question="TCS outlook?",
        summary="TCS summary.",
        uncertainty=["Uncertain."],
        risks=["Risky."],
        conclusion="Hold.",
    )
    report_id = save_research_report(report, db_path=portfolio_db)

    with pytest.raises(ValueError, match="ticker does not match"):
        create_trade_proposal(
            portfolio_id,
            "RELIANCE.NS",
            "BUY",
            1,
            100,
            "Wrong report ticker",
            research_report_id=report_id,
            db_path=portfolio_db,
        )


def test_missing_report_id_rejected(portfolio_db):
    portfolio_id = create_portfolio(
        name="Missing Report Test",
        initial_cash=10_000,
        db_path=portfolio_db,
    )
    with pytest.raises(ValueError, match="does not exist"):
        create_trade_proposal(
            portfolio_id,
            "RELIANCE.NS",
            "BUY",
            1,
            100,
            "Missing report",
            research_report_id=999,
            db_path=portfolio_db,
        )


@pytest.mark.parametrize(
    ("side", "quantity", "price"),
    [
        ("HOLD", 1, 100),
        ("BUY", 0, 100),
        ("BUY", -1, 100),
        ("BUY", 1, 0),
        ("BUY", 1, -50),
    ],
)
def test_invalid_proposal_arguments_rejected(portfolio_db, side, quantity, price):
    portfolio_id = create_portfolio(
        name="Invalid Args",
        initial_cash=10_000,
        db_path=portfolio_db,
    )
    with pytest.raises(ValueError):
        create_trade_proposal(
            portfolio_id,
            "RELIANCE.NS",
            side,
            quantity,
            price,
            "Invalid argument test",
            db_path=portfolio_db,
        )
