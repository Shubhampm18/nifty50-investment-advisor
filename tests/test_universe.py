"""Tests for the official NIFTY 50 constituent feed handling."""

from __future__ import annotations

import pytest

from nifty50_investment_advisor import universe


def _csv_rows(count: int = 50) -> str:
    rows = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    rows.extend(
        f"Company {index},Industry,SYM{index:02},EQ,INE{index:07}"
        for index in range(count)
    )
    return "\n".join(rows)


def test_official_csv_requires_50_unique_valid_constituents():
    parsed = universe._parse_constituents(_csv_rows())

    assert len(parsed) == 50
    assert parsed[0].symbol == "SYM00"
    assert parsed[0].yahoo_ticker == "SYM00.NS"
    assert parsed[0].company_name == "Company 0"

    with pytest.raises(ValueError, match="exactly 50"):
        universe._parse_constituents(_csv_rows(49))
    with pytest.raises(ValueError, match="duplicate"):
        duplicate_rows = _csv_rows().replace("SYM01,EQ", "SYM00,EQ")
        universe._parse_constituents(duplicate_rows)


def test_universe_refresh_caches_and_marks_prior_data_stale(monkeypatch):
    original = tuple(
        universe.Nifty50Constituent(f"SYM{index:02}", f"Company {index}")
        for index in range(50)
    )
    monkeypatch.setattr(universe, "_cached_universe", None)
    monkeypatch.setattr(universe, "_cached_monotonic", None)
    monkeypatch.setattr(universe, "_download_constituents", lambda: original)

    fresh = universe.get_nifty50_universe(force_refresh=True)
    assert len(fresh.tickers) == 50
    assert fresh.stale is False
    assert universe.get_nifty50_universe() is fresh

    monkeypatch.setattr(
        universe,
        "_download_constituents",
        lambda: (_ for _ in ()).throw(TimeoutError("offline")),
    )
    stale = universe.get_nifty50_universe(force_refresh=True)
    assert stale.tickers == fresh.tickers
    assert stale.checked_at == fresh.checked_at
    assert stale.stale is True


def test_universe_refresh_without_cache_fails_clearly(monkeypatch):
    monkeypatch.setattr(universe, "_cached_universe", None)
    monkeypatch.setattr(universe, "_cached_monotonic", None)
    monkeypatch.setattr(
        universe,
        "_download_constituents",
        lambda: (_ for _ in ()).throw(TimeoutError("offline")),
    )

    with pytest.raises(RuntimeError, match="current NIFTY 50 constituents"):
        universe.get_nifty50_universe(force_refresh=True)
