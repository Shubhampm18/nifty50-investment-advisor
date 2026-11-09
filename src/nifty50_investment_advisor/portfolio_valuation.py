"""Market-price refresh and deterministic paper-portfolio valuation."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nifty50_investment_advisor.tools.market_data import get_market_data

QuoteFetcher = Callable[[str], Mapping[str, Any]]


def _fetch_quote(ticker: str) -> Mapping[str, Any]:
    return get_market_data.invoke(
        {"symbol": ticker, "period": "5d", "interval": "1d"}
    )


def refresh_portfolio_quotes(
    holdings: Sequence[Mapping[str, Any]],
    *,
    quote_fetcher: QuoteFetcher | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch a last returned daily close for each holding, isolating failures."""
    fetch = quote_fetcher or _fetch_quote
    quotes: dict[str, dict[str, Any]] = {}
    for holding in holdings:
        ticker = str(holding.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        try:
            result = fetch(ticker)
            if not isinstance(result, Mapping):
                raise TypeError("Market data returned an unexpected result type.")
            price = result.get("latest_close")
            if result.get("ok") is not True:
                quotes[ticker] = {
                    "ok": False,
                    "error": str(result.get("error", "Quote retrieval failed.")),
                    "source": result.get("source"),
                }
            elif (
                isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not math.isfinite(float(price))
                or float(price) <= 0
            ):
                quotes[ticker] = {
                    "ok": False,
                    "error": "The quote did not contain a valid positive close.",
                    "source": result.get("source"),
                }
            else:
                quotes[ticker] = {
                    "ok": True,
                    "price": float(price),
                    "as_of": result.get("latest_date"),
                    "source": result.get("source", "Market data provider"),
                }
        except Exception as exc:  # noqa: BLE001 - retain other holding quotes
            quotes[ticker] = {
                "ok": False,
                "error": f"Quote retrieval failed ({type(exc).__name__}).",
            }
    return quotes


def build_portfolio_valuation(
    summary: Mapping[str, Any],
    quotes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Mark holdings to supplied closes; never substitute missing prices."""
    valued_holdings: list[dict[str, Any]] = []
    known_market_value = 0.0
    all_priced = True

    for original in summary.get("holdings", []):
        item = dict(original)
        ticker = str(item["ticker"]).upper()
        quote = quotes.get(ticker, {})
        if quote.get("ok") is not True:
            all_priced = False
            item.update(
                {
                    "market_price": None,
                    "quote_as_of": None,
                    "market_value": None,
                    "unrealized_pnl": None,
                    "unrealized_return_percent": None,
                    "valuation_status": str(
                        quote.get("error", "Refresh required for this holding.")
                    ),
                }
            )
            valued_holdings.append(item)
            continue

        price = float(quote["price"])
        market_value = round(int(item["quantity"]) * price, 2)
        cost_basis = float(item["cost_basis"])
        unrealized = round(market_value - cost_basis, 2)
        known_market_value += market_value
        item.update(
            {
                "market_price": price,
                "quote_as_of": quote.get("as_of"),
                "quote_source": quote.get("source"),
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "unrealized_return_percent": (
                    round(unrealized / cost_basis * 100, 2)
                    if cost_basis > 0
                    else None
                ),
                "valuation_status": "priced",
            }
        )
        valued_holdings.append(item)

    cash = float(summary["cash_balance"])
    initial_cash = float(summary["initial_cash"])
    partial_total = round(cash + known_market_value, 2)
    total_value = partial_total if all_priced else None
    total_pnl = round(total_value - initial_cash, 2) if total_value is not None else None
    total_return = (
        round(total_pnl / initial_cash * 100, 2)
        if total_pnl is not None and initial_cash > 0
        else None
    )

    return {
        "holdings": valued_holdings,
        "known_market_value": round(known_market_value, 2),
        "partial_total_value": partial_total,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_return_percent": total_return,
        "valuation_complete": all_priced,
        "realized_pnl": float(summary.get("realized_pnl", 0.0)),
        "total_fees": float(summary.get("total_fees", 0.0)),
        "cash_balance": cash,
        "initial_cash": initial_cash,
    }
