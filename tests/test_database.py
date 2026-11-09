import sqlite3
from datetime import UTC, datetime

from nifty50_investment_advisor.database import (
    get_research_report,
    get_stock_comparison,
    initialize_database,
    list_research_reports,
    list_stock_comparisons,
    save_research_report,
    save_stock_comparison,
)
from nifty50_investment_advisor.portfolio import (
    create_portfolio,
    create_trade_proposal,
    list_trade_proposals,
)
from nifty50_investment_advisor.reports import (
    ComparisonDifference,
    ComparisonObservation,
    ComparisonTickerReport,
    ResearchReport,
    StockComparisonReport,
)


def _valid_report() -> ResearchReport:
    return ResearchReport(
        ticker="RELIANCE.NS",
        company_name="Reliance Industries Limited",
        generated_at=datetime(2026, 10, 22, 12, 30, tzinfo=UTC),
        research_question="What are the current business and market risks?",
        summary="The company operates across several business segments.",
        uncertainty=["Future performance is uncertain."],
        risks=["Market and regulatory conditions may change."],
        conclusion="Review current filings and market conditions before acting.",
    )


def _valid_comparison() -> StockComparisonReport:
    stocks = []
    for ticker, close in (("RELIANCE.NS", 100.0), ("TCS.NS", 200.0)):
        report = ResearchReport(
            ticker=ticker,
            company_name=ticker,
            research_question="Compare returned test evidence.",
            summary=f"Evidence for {ticker}.",
            data={
                "market_data": {
                    "ok": True,
                    "latest_close": close,
                    "latest_date": "2026-10-21",
                    "source": "Test data source",
                }
            },
            uncertainty=["Test uncertainty."],
            risks=["Test risk."],
            conclusion="Test conclusion.",
        )
        stocks.append(
            ComparisonTickerReport(
                ticker=ticker,
                report=report,
                news={"ok": True, "query": f"{ticker} news", "articles": []},
            )
        )
    return StockComparisonReport(
        research_question="Compare returned test evidence.",
        tickers=[stock.ticker for stock in stocks],
        stocks=stocks,
        summary="Test comparison summary.",
        differences=[
            ComparisonDifference(
                category="market_data",
                metric="latest_close",
                observations=[
                    ComparisonObservation(
                        ticker="RELIANCE.NS",
                        value=100,
                        as_of="2026-10-21",
                        source_name="Test data source",
                    ),
                    ComparisonObservation(
                        ticker="TCS.NS",
                        value=200,
                        as_of="2026-10-21",
                        source_name="Test data source",
                    ),
                ],
            )
        ],
        uncertainty=["Test uncertainty."],
        conclusion="Test conclusion.",
    )


def test_initialize_database_creates_research_reports(tmp_path):
    db_path = tmp_path / "fresh.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = {
            row[1]: row[3]
            for row in connection.execute("PRAGMA table_info(research_reports)")
        }

    assert {
        "stock_comparisons",
        "research_reports",
        "paper_portfolios",
        "trade_proposals",
        "paper_trades",
        "paper_holdings",
    } <= tables
    assert columns == {
        "id": 0,
        "ticker": 1,
        "company_name": 0,
        "research_question": 1,
        "generated_at": 1,
        "report_json": 1,
        "created_at": 1,
    }


def test_cost_schema_migration_preserves_existing_rows(tmp_path):
    db_path = tmp_path / "pre-cost-ledger.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE trade_proposals (id INTEGER PRIMARY KEY, rationale TEXT)"
        )
        connection.execute(
            "CREATE TABLE paper_trades (id INTEGER PRIMARY KEY, total_value REAL)"
        )
        connection.execute(
            "INSERT INTO trade_proposals (id, rationale) VALUES (1, 'existing')"
        )
        connection.execute(
            "INSERT INTO paper_trades (id, total_value) VALUES (1, 100.0)"
        )

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        proposal_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(trade_proposals)")
        }
        trade_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(paper_trades)")
        }
        assert connection.execute(
            "SELECT id, rationale, transaction_cost_bps FROM trade_proposals"
        ).fetchone() == (1, "existing", 0.0)
        assert connection.execute(
            "SELECT id, total_value, fee_bps, fee_amount, realized_pnl FROM paper_trades"
        ).fetchone() == (1, 100.0, 0.0, 0.0, 0.0)

    assert "transaction_cost_bps" in proposal_columns
    assert {"fee_bps", "fee_amount", "realized_pnl"} <= trade_columns


def test_research_report_save_get_and_list_are_persistent_and_idempotent(tmp_path):
    db_path = tmp_path / "reports.db"
    initialize_database(db_path)
    report = _valid_report()

    report_id = save_research_report(report, db_path=db_path)
    saved = get_research_report(report_id, db_path=db_path)

    assert saved is not None
    assert saved["id"] == report_id
    assert saved["ticker"] == report.ticker
    assert saved["company_name"] == report.company_name
    assert saved["research_question"] == report.research_question
    assert saved["summary"] == report.summary
    assert "stored_at" in saved

    listed = list_research_reports(db_path=db_path)
    assert listed == [
        {
            "id": report_id,
            "ticker": report.ticker,
            "company_name": report.company_name,
            "research_question": report.research_question,
            "generated_at": report.generated_at.isoformat(),
            "stored_at": saved["stored_at"],
        }
    ]

    initialize_database(db_path)
    assert get_research_report(report_id, db_path=db_path) == saved


def test_trade_proposal_can_reference_saved_report(tmp_path):
    db_path = tmp_path / "proposal.db"
    initialize_database(db_path)
    report_id = save_research_report(_valid_report(), db_path=db_path)
    portfolio_id = create_portfolio(
        name="Report-linked Portfolio",
        initial_cash=10_000,
        db_path=db_path,
    )

    proposal_id = create_trade_proposal(
        portfolio_id=portfolio_id,
        ticker="RELIANCE.NS",
        side="BUY",
        quantity=1,
        proposed_price=1_000,
        rationale="Linked to saved research.",
        research_report_id=report_id,
        db_path=db_path,
    )

    proposals = list_trade_proposals(
        portfolio_id=portfolio_id,
        db_path=db_path,
    )
    assert len(proposals) == 1
    assert proposals[0]["id"] == proposal_id
    assert proposals[0]["research_report_id"] == report_id


def test_comparison_save_get_and_list_are_separate_from_single_reports(tmp_path):
    db_path = tmp_path / "comparisons.db"
    initialize_database(db_path)
    report = _valid_comparison()

    comparison_id = save_stock_comparison(report, db_path=db_path)
    saved = get_stock_comparison(comparison_id, db_path=db_path)

    assert saved is not None
    assert saved["id"] == comparison_id
    assert saved["report_type"] == "comparison"
    assert saved["tickers"] == ["RELIANCE.NS", "TCS.NS"]
    assert saved["stocks"][0]["report"]["ticker"] == "RELIANCE.NS"
    assert saved["stocks"][1]["report"]["ticker"] == "TCS.NS"
    assert saved["differences"][0]["observations"][1]["value"] == 200.0
    assert "stored_at" in saved

    listed = list_stock_comparisons(db_path=db_path)
    assert listed == [
        {
            "id": comparison_id,
            "report_type": "comparison",
            "tickers": ["RELIANCE.NS", "TCS.NS"],
            "research_question": report.research_question,
            "generated_at": report.generated_at.isoformat(),
            "stored_at": saved["stored_at"],
        }
    ]
    assert list_research_reports(db_path=db_path) == []

    initialize_database(db_path)
    assert get_stock_comparison(comparison_id, db_path=db_path) == saved
