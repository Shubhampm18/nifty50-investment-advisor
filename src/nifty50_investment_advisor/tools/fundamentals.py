
"""Retrieve available company fundamentals for Indian equities."""

import math
import re
from typing import Any

import yfinance as yf
from langchain_core.tools import tool


def _number(value: Any) -> float | None:
    """Convert a value to a finite float, or return None."""
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    """Return a non-empty string or None."""
    if value is None:
        return None

    result = str(value).strip()
    return result or None


@tool
def get_company_fundamentals(symbol: str) -> dict[str, Any]:
    """Retrieve available company fundamentals from Yahoo Finance.

    Use Yahoo Finance symbols such as RELIANCE.NS or TCS.NS.
    This tool is intended for individual listed companies, not the
    NIFTY 50 index.

    Args:
        symbol: Yahoo Finance ticker for an Indian listed company.

    Returns:
        Available company profile, valuation, profitability,
        revenue, earnings, and balance-sheet metrics.
        Missing fields are returned as None.
    """
    symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z0-9&._-]{1,25}", symbol):
        return {
            "ok": False,
            "symbol": symbol,
            "error": "Invalid symbol format.",
        }

    if symbol in {"^NSEI", "NIFTY50", "NIFTY 50"}:
        return {
            "ok": False,
            "symbol": symbol,
            "error": (
                "Company fundamentals require an individual company "
                "ticker, such as RELIANCE.NS or TCS.NS."
            ),
        }

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        if not info or not any(
            info.get(field) is not None
            for field in ("longName", "shortName", "marketCap", "sector")
        ):
            return {
                "ok": False,
                "symbol": symbol,
                "error": (
                    "Yahoo Finance returned insufficient company "
                    "information. Check the symbol or try again later."
                ),
                "source": "Yahoo Finance via yfinance",
            }

        financial_metrics = {
            "market_cap": "marketCap",
            "trailing_pe": "trailingPE",
            "forward_pe": "forwardPE",
            "price_to_book": "priceToBook",
            "enterprise_value": "enterpriseValue",
            "revenue": "totalRevenue",
            "revenue_per_share": "revenuePerShare",
            "gross_margins": "grossMargins",
            "operating_margins": "operatingMargins",
            "profit_margins": "profitMargins",
            "return_on_equity": "returnOnEquity",
            "return_on_assets": "returnOnAssets",
            "total_debt": "totalDebt",
            "total_cash": "totalCash",
            "earnings_growth": "earningsGrowth",
            "revenue_growth": "revenueGrowth",
            "trailing_eps": "trailingEps",
            "forward_eps": "forwardEps",
            "dividend_yield": "dividendYield",
            "beta": "beta",
        }

        metrics = {
            output_name: _number(info.get(source_name))
            for output_name, source_name in financial_metrics.items()
        }

        return {
            "ok": True,
            "symbol": symbol,
            "company": _text(info.get("longName"))
            or _text(info.get("shortName")),
            "sector": _text(info.get("sector")),
            "industry": _text(info.get("industry")),
            "currency": _text(info.get("currency")),
            "country": _text(info.get("country")),
            "website": _text(info.get("website")),
            "employees": info.get("fullTimeEmployees"),
            "metrics": metrics,
            "source": "Yahoo Finance via yfinance",
            "limitations": [
                "Financial fields may be missing, delayed, or revised.",
                "Valuation ratios depend on the definitions and periods "
                "used by the data provider.",
                "Growth and profitability ratios may refer to different "
                "reporting periods.",
                "This data is for educational research, not a standalone "
                "investment recommendation.",
            ],
        }

    except Exception as exc:
        return {
            "ok": False,
            "symbol": symbol,
            "error": (
                f"Company-fundamentals retrieval failed: "
                f"{type(exc).__name__}"
            ),
            "source": "Yahoo Finance via yfinance",
        }
