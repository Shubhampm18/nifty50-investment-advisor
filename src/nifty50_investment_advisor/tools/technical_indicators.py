
"""Calculate technical indicators from real historical Indian equity data."""

import math
import re
from typing import Any

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool


def _finite_number(value: Any) -> float | None:
    """Return a finite float, or None for missing/invalid values."""
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _calculate_indicators(history: pd.DataFrame) -> dict[str, Any]:
    """Calculate indicators using historical closing prices."""
    if history.empty or "Close" not in history.columns:
        return {
            "ok": False,
            "error": "No valid historical closing prices are available.",
        }

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()

    if close.empty:
        return {
            "ok": False,
            "error": "No valid historical closing prices are available.",
        }

    returns = close.pct_change().dropna()

    sma20 = close.rolling(window=20, min_periods=20).mean()
    sma50 = close.rolling(window=50, min_periods=50).mean()

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()

    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(
        span=9,
        adjust=False,
        min_periods=9,
    ).mean()

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    average_gain = gains.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    average_loss = losses.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()

    relative_strength = average_gain / average_loss
    rsi = 100 - (100 / (1 + relative_strength))

    # Handle a series with gains but no losses.
    rsi = rsi.mask(
        (average_loss == 0) & (average_gain > 0),
        100.0,
    )

    # A completely flat series has RSI 50 by convention.
    rsi = rsi.mask(
        (average_loss == 0) & (average_gain == 0),
        50.0,
    )

    latest_close = _finite_number(close.iloc[-1])

    latest_sma20 = _finite_number(sma20.iloc[-1])
    latest_sma50 = _finite_number(sma50.iloc[-1])
    latest_ema12 = _finite_number(ema12.iloc[-1])
    latest_ema26 = _finite_number(ema26.iloc[-1])
    latest_rsi = _finite_number(rsi.iloc[-1])
    latest_macd = _finite_number(macd_line.iloc[-1])
    latest_signal = _finite_number(signal_line.iloc[-1])

    latest_macd_histogram = None
    if latest_macd is not None and latest_signal is not None:
        latest_macd_histogram = latest_macd - latest_signal

    # Sample standard deviation of daily returns, annualized using
    # the conventional 252 trading days per year.
    annualized_volatility = None
    if len(returns) >= 2:
        daily_std = _finite_number(returns.std(ddof=1))
        if daily_std is not None:
            annualized_volatility = daily_std * math.sqrt(252) * 100

    def trend_vs_average(average: float | None) -> str:
        if latest_close is None or average is None:
            return "insufficient_data"
        if latest_close > average:
            return "above"
        if latest_close < average:
            return "below"
        return "equal"

    return {
        "ok": True,
        "latest_close": latest_close,
        "latest_date": close.index[-1].isoformat(),
        "observations_used": len(close),
        "indicators": {
            "sma_20": latest_sma20,
            "sma_50": latest_sma50,
            "ema_12": latest_ema12,
            "ema_26": latest_ema26,
            "rsi_14": latest_rsi,
            "macd_line": latest_macd,
            "macd_signal": latest_signal,
            "macd_histogram": latest_macd_histogram,
            "annualized_volatility_percent": annualized_volatility,
        },
        "price_vs_moving_averages": {
            "sma_20": trend_vs_average(latest_sma20),
            "sma_50": trend_vs_average(latest_sma50),
        },
        "source": "Yahoo Finance via yfinance",
        "disclaimer": (
            "Indicators are calculated from historical closing prices. "
            "They describe past data, do not predict returns reliably, "
            "and are not standalone investment recommendations."
        ),
    }


@tool
def get_technical_indicators(
    symbol: str = "^NSEI",
    period: str = "6mo",
) -> dict[str, Any]:
    """Retrieve historical prices and calculate technical indicators.

    Use ^NSEI for NIFTY 50. Indian equity examples include
    RELIANCE.NS and TCS.NS.

    Args:
        symbol: Yahoo Finance symbol for the index or an Indian equity.
        period: Historical window: 3mo, 6mo, or 1y.

    Returns:
        Latest technical indicators, moving-average comparisons,
        observation date, data source, and limitations.
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

    if period not in {"3mo", "6mo", "1y"}:
        return {
            "ok": False,
            "symbol": symbol,
            "error": "Period must be 3mo, 6mo, or 1y.",
        }

    try:
        history = yf.Ticker(symbol).history(
            period=period,
            interval="1d",
            auto_adjust=True,
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

        # Handle MultiIndex columns if supplied by the data provider.
        if isinstance(history.columns, pd.MultiIndex):
            history.columns = [
                column[0] for column in history.columns
            ]

        result = _calculate_indicators(history)
        result["symbol"] = symbol
        result["period_requested"] = period
        return result

    except Exception as exc:
        return {
            "ok": False,
            "symbol": symbol,
            "error": (
                "Technical-indicator retrieval failed: "
                f"{type(exc).__name__}"
            ),
            "source": "Yahoo Finance via yfinance",
        }
