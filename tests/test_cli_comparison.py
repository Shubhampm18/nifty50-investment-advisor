"""CLI comparison actions use isolated persistence and stubbed services."""

from __future__ import annotations

from functools import partial

from nifty50_investment_advisor import cli, database
from nifty50_investment_advisor.reports import (
    ComparisonTickerReport,
    ResearchReport,
    StockComparisonReport,
)


def _valid_comparison() -> dict:
    stocks = []
    for ticker in ("RELIANCE.NS", "TCS.NS"):
        individual = ResearchReport(
            ticker=ticker,
            research_question="Compare test evidence.",
            summary=f"Evidence record for {ticker}.",
            uncertainty=["Test uncertainty."],
            risks=["Test risk."],
            conclusion="Test conclusion.",
        )
        stocks.append(
            ComparisonTickerReport(
                ticker=ticker,
                report=individual,
                news={"ok": True, "articles": []},
            )
        )
    return StockComparisonReport(
        research_question="Compare test evidence.",
        tickers=[stock.ticker for stock in stocks],
        stocks=stocks,
        summary="Returned evidence differs; neither ticker is ranked.",
        uncertainty=["Test uncertainty."],
        conclusion="No winner is selected.",
    ).model_dump(mode="json")


def test_cli_comparison_requires_explicit_save(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "comparison-cli.db"
    monkeypatch.setattr(
        cli,
        "initialize_database",
        partial(database.initialize_database, db_path=db_path),
    )
    monkeypatch.setattr(
        cli,
        "save_stock_comparison",
        partial(database.save_stock_comparison, db_path=db_path),
    )
    calls: list[tuple[list[str], str]] = []
    report = _valid_comparison()

    def compare(tickers: list[str], question: str) -> dict:
        calls.append((tickers, question))
        return {
            "ok": True,
            "tickers": report["tickers"],
            "analysis": report["summary"],
            "agent_error": None,
            "report": report,
        }

    monkeypatch.setattr(cli, "run_stock_comparison", compare)
    monkeypatch.setattr(
        "sys.argv",
        [
            "nifty50-advisor",
            "compare",
            "RELIANCE.NS",
            "TCS.NS",
            "--question",
            "Compare returned values.",
        ],
    )

    cli.main()
    assert calls == [(["RELIANCE.NS", "TCS.NS"], "Compare returned values.")]
    assert database.list_stock_comparisons(db_path=db_path) == []
    assert "Stock comparison result" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv",
        [
            "nifty50-advisor",
            "compare",
            "RELIANCE.NS",
            "TCS.NS",
            "--save",
        ],
    )
    cli.main()
    saved = database.list_stock_comparisons(db_path=db_path)
    assert len(saved) == 1
    assert saved[0]["tickers"] == ["RELIANCE.NS", "TCS.NS"]
    assert "Stock comparison saved with ID: 1" in capsys.readouterr().out
