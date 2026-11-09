"""Tests for quote refresh and paper portfolio valuation."""

from nifty50_investment_advisor.portfolio_valuation import (
    build_portfolio_valuation,
    refresh_portfolio_quotes,
)


def test_price_refresh_retains_per_ticker_errors_and_dates():
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        if ticker == "TCS.NS":
            return {"ok": False, "error": "No data", "source": "Test"}
        return {
            "ok": True,
            "latest_close": 110.0,
            "latest_date": "2026-10-22T00:00:00+05:30",
            "source": "Test source",
        }

    quotes = refresh_portfolio_quotes(
        [{"ticker": "RELIANCE.NS"}, {"ticker": "TCS.NS"}],
        quote_fetcher=fetch,
    )

    assert calls == ["RELIANCE.NS", "TCS.NS"]
    assert quotes["RELIANCE.NS"] == {
        "ok": True,
        "price": 110.0,
        "as_of": "2026-10-22T00:00:00+05:30",
        "source": "Test source",
    }
    assert quotes["TCS.NS"]["ok"] is False


def test_valuation_calculates_returns_only_when_every_holding_is_priced():
    summary = {
        "cash_balance": 9_470.2,
        "initial_cash": 10_000.0,
        "realized_pnl": 73.2,
        "total_fees": 9.8,
        "holdings": [
            {
                "ticker": "RELIANCE.NS",
                "quantity": 6,
                "average_cost": 100.5,
                "cost_basis": 603.0,
            },
            {
                "ticker": "TCS.NS",
                "quantity": 1,
                "average_cost": 300.0,
                "cost_basis": 300.0,
            },
        ],
    }
    partial = build_portfolio_valuation(
        summary,
        {"RELIANCE.NS": {"ok": True, "price": 110, "as_of": "2026-10-22"}},
    )
    assert partial["valuation_complete"] is False
    assert partial["total_value"] is None
    assert partial["total_pnl"] is None
    assert partial["holdings"][0]["unrealized_pnl"] == 57.0
    assert partial["holdings"][1]["market_value"] is None

    complete = build_portfolio_valuation(
        summary,
        {
            "RELIANCE.NS": {"ok": True, "price": 110},
            "TCS.NS": {"ok": True, "price": 310},
        },
    )
    assert complete["valuation_complete"] is True
    assert complete["total_value"] == 10_440.2
    assert complete["total_pnl"] == 440.2
    assert complete["total_return_percent"] == 4.4


def test_empty_portfolio_value_is_cash_without_quotes():
    value = build_portfolio_valuation(
        {
            "cash_balance": 5_000.0,
            "initial_cash": 5_000.0,
            "holdings": [],
        },
        {},
    )
    assert value["valuation_complete"] is True
    assert value["total_value"] == 5_000.0
    assert value["total_pnl"] == 0.0
    assert value["total_return_percent"] == 0.0
