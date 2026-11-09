"""Comparison validation and orchestration tests with isolated services."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nifty50_investment_advisor import research
from nifty50_investment_advisor.reports import (
    ComparisonTickerReport,
    ResearchData,
    ResearchReport,
    StockComparisonReport,
)
from nifty50_investment_advisor.universe import Nifty50Constituent, Nifty50Universe

TEST_UNIVERSE = Nifty50Universe(
    constituents=tuple(
        Nifty50Constituent(symbol=symbol, company_name=company)
        for symbol, company in (
            ("RELIANCE", "Reliance Industries Limited"),
            ("TCS", "Tata Consultancy Services Limited"),
            ("INFY", "Infosys Limited"),
            ("HDFCBANK", "HDFC Bank Limited"),
            ("ICICIBANK", "ICICI Bank Limited"),
            ("BHARTIARTL", "Bharti Airtel Limited"),
        )
    ),
    checked_at=datetime(2026, 10, 23, tzinfo=UTC),
)


@pytest.fixture(autouse=True)
def use_test_universe(monkeypatch):
    monkeypatch.setattr(research, "get_nifty50_universe", lambda: TEST_UNIVERSE)


def test_comparison_tickers_are_normalized_and_supported():
    assert research.normalize_comparison_tickers(
        " reliance.ns,  tcs.NS "
    ) == ["RELIANCE.NS", "TCS.NS"]
    assert research.normalize_comparison_tickers(["reliance", "TCS.NS"]) == [
        "RELIANCE.NS",
        "TCS.NS",
    ]


@pytest.mark.parametrize(
    ("tickers", "message"),
    [
        (["RELIANCE.NS"], "2 to 5"),
        (
            [
                "RELIANCE.NS",
                "TCS.NS",
                "INFY.NS",
                "HDFCBANK.NS",
                "ICICIBANK.NS",
                "BHARTIARTL.NS",
            ],
            "2 to 5",
        ),
        (["RELIANCE.NS", " reliance.ns "], "distinct"),
        (["RELIANCE.NS", "UNKNOWN.NS"], "Unsupported"),
        (["RELIANCE.NS", "^NSEI"], "Unsupported"),
    ],
)
def test_comparison_ticker_validation_errors_are_clear(tickers, message):
    with pytest.raises(ValueError, match=message):
        research.normalize_comparison_tickers(tickers)


def _valid_stock_report(ticker: str) -> ResearchReport:
    return ResearchReport(
        ticker=ticker,
        research_question="Compare returned evidence.",
        summary="Evidence record.",
        uncertainty=["Uncertainty."],
        risks=["Risk."],
        conclusion="Conclusion.",
    )


def test_comparison_report_validates_ticker_set_and_nested_records():
    stocks = [
        ComparisonTickerReport(
            ticker=ticker,
            report=_valid_stock_report(ticker),
            news={"ok": True, "articles": []},
        )
        for ticker in ("RELIANCE.NS", "TCS.NS")
    ]
    report = StockComparisonReport(
        research_question="Compare returned evidence.",
        tickers=["RELIANCE.NS", "TCS.NS"],
        stocks=stocks,
        summary="Differences are shown in returned data.",
        uncertainty=["Values have source limitations."],
        conclusion="No winner is selected.",
    )
    assert report.tickers == [stock.ticker for stock in report.stocks]

    with pytest.raises(ValueError, match="distinct"):
        StockComparisonReport.model_validate(
            {
                **report.model_dump(),
                "tickers": ["RELIANCE.NS", "RELIANCE.NS"],
                "stocks": [stocks[0], stocks[0]],
            }
        )

    with pytest.raises(ValueError, match="match"):
        ComparisonTickerReport(ticker="RELIANCE.NS", report=_valid_stock_report("TCS.NS"))

    with pytest.raises(ValidationError):
        StockComparisonReport.model_validate(
            {
                **report.model_dump(),
                "tickers": ["RELIANCE.NS", "UNKNOWN"],
            }
        )

    with pytest.raises(ValidationError):
        StockComparisonReport.model_validate(
            {
                **report.model_dump(),
                "tickers": ["RELIANCE.NS"],
                "stocks": [stocks[0]],
            }
        )


def _retrieved_data(ticker: str, *, market_ok: bool) -> ResearchData:
    market = (
        {
            "ok": True,
            "symbol": ticker,
            "latest_close": 100.0 if ticker == "RELIANCE.NS" else 200.0,
            "previous_close": 99.0,
            "change_percent": 1.01,
            "latest_date": "2026-10-21T00:00:00+05:30",
            "source": "Test market source",
        }
        if market_ok
        else {"ok": False, "symbol": ticker, "error": "Test market failure."}
    )
    return ResearchData(
        market_data=market,
        technical_indicators={
            "ok": True,
            "symbol": ticker,
            "latest_date": "2026-10-21T00:00:00+05:30",
            "indicators": {"rsi_14": 51.0 if ticker == "RELIANCE.NS" else 55.0},
            "source": "Test technical source",
        },
        fundamentals={
            "ok": True,
            "symbol": ticker,
            "company": f"Test {ticker}",
            "metrics": {"trailing_pe": 20.0},
            "source": "Test fundamentals source",
        },
        retrieval_status={
            "market_data": "success" if market_ok else "failed",
            "technical_indicators": "success",
            "fundamentals": "success",
        },
        retrieval_errors={} if market_ok else {"market_data": "Test market failure."},
    )


def test_comparison_retains_ticker_specific_successes_errors_and_periods(monkeypatch):
    retrieval_calls: list[tuple[str, str, str]] = []

    def retrieve(ticker: str, market_period: str, technical_period: str):
        retrieval_calls.append((ticker, market_period, technical_period))
        if ticker == "RELIANCE.NS":
            return _retrieved_data(ticker, market_ok=True)
        return _retrieved_data(ticker, market_ok=False)

    news_queries: list[str] = []

    def retrieve_news(query: str):
        news_queries.append(query)
        if query.startswith("Tata Consultancy"):
            raise RuntimeError("Test news failure")
        return {"ok": True, "query": query, "articles": []}

    monkeypatch.setattr(research, "_retrieve_market_research", retrieve)
    monkeypatch.setattr(research, "retrieve_news", retrieve_news)

    result = research.run_stock_comparison(
        [" reliance.ns ", "tcs.ns"],
        "Compare the returned evidence.",
    )

    assert result["ok"] is True
    assert result["tickers"] == ["RELIANCE.NS", "TCS.NS"]
    report = StockComparisonReport.model_validate(result["report"])
    assert retrieval_calls == [
        ("RELIANCE.NS", "1mo", "6mo"),
        ("TCS.NS", "1mo", "6mo"),
    ]
    assert news_queries[0] != news_queries[1]
    assert news_queries[0].startswith("Reliance Industries Limited")
    assert report.stocks[0].report.data.market_data["latest_close"] == 100.0
    assert report.stocks[0].report.data.retrieval_status["news"] == "success"
    assert report.stocks[1].report.data.retrieval_status["market_data"] == "failed"
    assert report.stocks[1].report.data.retrieval_status["news"] == "failed"
    assert "news" in report.stocks[1].report.data.retrieval_errors
    assert any("TCS.NS" in item for item in report.missing_information)
    rsi = next(item for item in report.differences if item.metric == "rsi_14")
    assert [item.value for item in rsi.observations] == [51.0, 55.0]


def test_comparison_summary_is_deterministic_and_never_calls_llm(monkeypatch):
    monkeypatch.setattr(
        research,
        "_retrieve_market_research",
        lambda ticker, **_kwargs: _retrieved_data(ticker, market_ok=True),
    )
    monkeypatch.setattr(
        research,
        "retrieve_news",
        lambda query: {"ok": True, "query": query, "articles": []},
    )
    monkeypatch.setattr(
        research,
        "create_investment_agent",
        lambda **_kwargs: pytest.fail("Comparison summaries must be deterministic."),
    )

    result = research.run_stock_comparison(["RELIANCE.NS", "TCS.NS"])

    assert result["ok"] is True
    assert "does not rank stocks or select a winner" in result["analysis"]
    assert "market data" in result["analysis"]
    assert result["report"]["universe_checked_at"] == "2026-10-23T00:00:00Z"


def test_unexpected_ticker_retrieval_exception_does_not_drop_other_records(monkeypatch):
    def retrieve(ticker: str, **_kwargs):
        if ticker == "TCS.NS":
            raise RuntimeError("isolated retrieval failure")
        return _retrieved_data(ticker, market_ok=True)

    monkeypatch.setattr(research, "_retrieve_market_research", retrieve)
    monkeypatch.setattr(
        research,
        "retrieve_news",
        lambda query: {"ok": True, "query": query, "articles": []},
    )
    monkeypatch.setattr(
        research,
        "create_investment_agent",
        lambda **_kwargs: pytest.fail("Comparison summaries must be deterministic."),
    )

    result = research.run_stock_comparison(["RELIANCE.NS", "TCS.NS"])
    report = StockComparisonReport.model_validate(result["report"])

    assert [stock.ticker for stock in report.stocks] == ["RELIANCE.NS", "TCS.NS"]
    assert report.stocks[0].report.data.market_data["ok"] is True
    assert report.stocks[1].report.data.market_data["ok"] is False
    assert report.stocks[1].report.data.retrieval_errors["market_data"] == (
        "RuntimeError: isolated retrieval failure"
    )
