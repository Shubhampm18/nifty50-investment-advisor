"""Technical-indicator math tests — pure functions, no network."""

import math

import pandas as pd

from nifty50_investment_advisor.tools.technical_indicators import (
    _calculate_indicators,
    _finite_number,
)


def _history(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=index)


def test_empty_history_returns_failure_dict():
    assert _calculate_indicators(pd.DataFrame())["ok"] is False
    assert _calculate_indicators(pd.DataFrame({"Open": [1.0]}))["ok"] is False
    assert _calculate_indicators(_history([float("nan")] * 5))["ok"] is False


def test_flat_series_has_rsi_50_and_zero_volatility():
    result = _calculate_indicators(_history([100.0] * 60))

    assert result["ok"] is True
    assert result["observations_used"] == 60
    assert result["indicators"]["rsi_14"] == 50.0
    assert result["indicators"]["annualized_volatility_percent"] == 0.0
    assert result["latest_close"] == 100.0
    assert result["indicators"]["macd_histogram"] == 0.0
    assert result["price_vs_moving_averages"]["sma_20"] == "equal"


def test_rising_series_has_rsi_100_and_positive_trends():
    closes = [100.0 + i for i in range(60)]
    result = _calculate_indicators(_history(closes))

    assert result["ok"] is True
    assert result["indicators"]["rsi_14"] == 100.0
    # sma20 over the last 20 closes (140..159) and sma50 over (110..159):
    assert result["indicators"]["sma_20"] == 149.5
    assert result["indicators"]["sma_50"] == 134.5
    assert result["price_vs_moving_averages"] == {"sma_20": "above", "sma_50": "above"}
    assert result["latest_close"] == 159.0


def test_falling_series_has_rsi_0_and_below_trends():
    closes = [200.0 - i for i in range(60)]
    result = _calculate_indicators(_history(closes))

    assert result["ok"] is True
    # All losses, no gains: relative strength is 0, so RSI collapses to 0.
    assert result["indicators"]["rsi_14"] == pytest_approx(0.0, abs=1e-9)
    assert result["indicators"]["sma_20"] == 150.5
    assert result["price_vs_moving_averages"]["sma_20"] == "below"
    assert result["price_vs_moving_averages"]["sma_50"] == "below"


def test_finite_number_handles_edge_values():
    assert _finite_number("3.5") == 3.5
    assert _finite_number(7) == 7
    assert _finite_number("not-a-number") is None
    assert _finite_number(None) is None
    assert _finite_number(float("nan")) is None
    assert _finite_number(float("inf")) is None
    assert _finite_number(float("-inf")) is None


def test_sanitized_finite_none_never_leaks_nan_or_inf():
    # A NaN in the series must never leak into the returned dict as a float;
    # _finite_number maps it to None, and the engine returns JSON-safe values.
    closes = [100.0] * 59 + [float("nan")]
    result = _calculate_indicators(_history(closes))
    assert result["ok"] is True
    for value in result["indicators"].values():
        if value is not None:
            assert math.isfinite(value)


def pytest_approx(expected, abs=0.0):
    import pytest as _pytest

    return _pytest.approx(expected, abs=abs)
