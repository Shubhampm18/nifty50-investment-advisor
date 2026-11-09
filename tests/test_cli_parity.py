"""CLI comparison retrieval and valuation refresh tests (isolated, stubbed).

The CLI database functions default to the configured project database, so
each test patches every CLI database accessor to the isolated tmp-path
database instead of touching the persistent ledger.
"""

from __future__ import annotations

from functools import partial

from nifty50_investment_advisor import cli, database, portfolio
from nifty50_investment_advisor.reports import (
    ComparisonTickerReport,
    ResearchReport,
    StockComparisonReport,
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
        uncertainty=["Test uncertainty."],
        conclusion="Test conclusion.",
    )


def _patch_cli_db(monkeypatch, db_path):
    """Route every db accessor the CLI calls to the isolated database."""
    database.initialize_database(db_path)
    for name in (
        "save_stock_comparison",
        "list_stock_comparisons",
        "get_stock_comparison",
        "list_research_reports",
        "get_research_report",
    ):
        fn = getattr(database, name)
        monkeypatch.setattr(cli, name, partial(fn, db_path=db_path))
    monkeypatch.setattr(
        cli, "initialize_database", lambda: database.initialize_database(db_path)
    )
    for name in (
        "create_portfolio",
        "create_trade_proposal",
        "get_portfolio_summary",
        "list_paper_trades",
        "list_portfolios",
        "list_trade_proposals",
        "review_trade_proposal",
    ):
        fn = getattr(portfolio, name)
        monkeypatch.setattr(cli, name, partial(fn, db_path=db_path))


def test_cli_comparison_list_and_show(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "comparison-cli.db"
    _patch_cli_db(monkeypatch, db_path)
    comparison = _valid_comparison()

    return_value = {
        "ok": True,
        "tickers": ["RELIANCE.NS", "TCS.NS"],
        "analysis": "deterministic summary",
        "agent_error": None,
        "report": comparison.model_dump(mode="json"),
    }
    monkeypatch.setattr(cli, "run_stock_comparison", lambda *a, **k: return_value)

    monkeypatch.setattr(
        "sys.argv",
        ["nifty50-advisor", "compare", "RELIANCE.NS", "TCS.NS", "--save"],
    )
    cli.main()
    assert "Stock comparison saved with ID: 1" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["nifty50-advisor", "comparison-list"])
    cli.main()
    out = capsys.readouterr().out
    assert "RELIANCE.NS" in out and "comparison" in out.lower()

    monkeypatch.setattr("sys.argv", ["nifty50-advisor", "comparison-show", "1"])
    cli.main()
    out = capsys.readouterr().out
    assert "report_type" in out or "comparison" in out.lower()


def test_cli_portfolio_show_refresh_stubs_quotes(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "valuation-cli.db"
    _patch_cli_db(monkeypatch, db_path)

    portfolio_id = portfolio.create_portfolio(
        name="V", initial_cash=10_000, db_path=db_path
    )
    buy_id = portfolio.create_trade_proposal(
        portfolio_id,
        "RELIANCE.NS",
        "BUY",
        2,
        100,
        "Seed",
        db_path=db_path,
    )
    portfolio.review_trade_proposal(buy_id, approved=True, db_path=db_path)

    monkeypatch.setattr(
        cli,
        "refresh_portfolio_quotes",
        lambda holdings: {
            "RELIANCE.NS": {
                "ok": True,
                "price": 110.0,
                "as_of": "2026-10-22",
                "source": "Yahoo Finance via yfinance",
            }
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        ["nifty50-advisor", "portfolio-show", str(portfolio_id), "--refresh"],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "market_value" in out
    assert "unrealized_pnl" in out
    assert "220.0" in out
