"""Real historical market-data retrieval for Indian equities."""

import math
import re
from typing import Any, Literal

import yfinance as yf
from langchain_core.tools import tool

Period = Literal["5d", "1mo", "3mo", "6mo", "1y"]
Interval = Literal["1d", "1wk"]


def _number(value: Any) -> float | None:
    """Convert a value to a finite float, or return None."""
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


@tool
def get_market_data(
    symbol: str = "^NSEI",
    period: Period = "1mo",
    interval: Interval = "1d",
) -> dict[str, Any]:
    """Retrieve real historical market data from Yahoo Finance.

    Use ^NSEI for the NIFTY 50 index. For Indian listed stocks,
    use Yahoo Finance symbols such as RELIANCE.NS or TCS.NS.

    Args:
        symbol: ^NSEI for NIFTY 50 or an Indian equity ticker.
        period: Historical window: 5d, 1mo, 3mo, 6mo, or 1y.
        interval: Daily (1d) or weekly (1wk) observations.

    Returns:
        Retrieved closing prices, recent observations, percentage
        change, and source information.
    """
    symbol = symbol.strip().upper()

    if symbol in {"NIFTY50", "NIFTY 50"}:
        symbol = "^NSEI"

    if not re.fullmatch(r"[A-Z0-9&._^-]{1,25}", symbol):
        return {
            "ok": False,
            "symbol": symbol,
            "error": "Invalid symbol format.",
        }

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=False,
            actions=False,
            timeout=20,
        )

        if history.empty:
            return {
                "ok": False,
                "symbol": symbol,
                "error": (
                    "Yahoo Finance returned no historical data. "
                    "Check the symbol or try again later."
                ),
                "source": "Yahoo Finance via yfinance",
            }

        # Handle MultiIndex columns if returned by the data provider.
        if hasattr(history.columns, "levels"):
            history.columns = [
                column[0] if isinstance(column, tuple) else column for column in history.columns
            ]

        history = history.dropna(subset=["Close"])

        if history.empty:
            return {
                "ok": False,
                "symbol": symbol,
                "error": "No valid closing prices were returned.",
                "source": "Yahoo Finance via yfinance",
            }

        latest = history.iloc[-1]
        previous = history.iloc[-2] if len(history) > 1 else None

        latest_close = _number(latest.get("Close"))
        previous_close = _number(previous.get("Close")) if previous is not None else None

        change_percent = None

        if latest_close is not None and previous_close is not None and previous_close != 0:
            change_percent = ((latest_close - previous_close) / previous_close) * 100

        recent_observations = []

        for timestamp, row in history.tail(10).iterrows():
            recent_observations.append(
                {
                    "date": timestamp.isoformat(),
                    "open": _number(row.get("Open")),
                    "high": _number(row.get("High")),
                    "low": _number(row.get("Low")),
                    "close": _number(row.get("Close")),
                    "volume": _number(row.get("Volume")),
                }
            )

        return {
            "ok": True,
            "symbol": symbol,
            "period_requested": period,
            "interval": interval,
            "latest_date": history.index[-1].isoformat(),
            "latest_close": latest_close,
            "previous_close": previous_close,
            "change_percent": change_percent,
            "observations_returned": len(history),
            "recent_observations": recent_observations,
            "source": "Yahoo Finance via yfinance",
            "disclaimer": (
                "Historical market data may be delayed, incomplete, "
                "or revised. This is not guaranteed live exchange data."
            ),
        }

    except Exception as exc:
        # Avoid returning exception details that may expose internal
        # information. The error type is sufficient for initial diagnosis.
        return {
            "ok": False,
            "symbol": symbol,
            "error": f"Market-data retrieval failed: {type(exc).__name__}",
            "source": "Yahoo Finance via yfinance",
        }
