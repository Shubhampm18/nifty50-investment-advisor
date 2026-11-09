"""Current NIFTY 50 constituents from the official NSE Indices CSV."""

from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.request import Request, urlopen

NIFTY50_CONSTITUENTS_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"
)
_CACHE_SECONDS = 6 * 60 * 60
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9&-]{1,25}$")


@dataclass(frozen=True)
class Nifty50Constituent:
    """A constituent record returned by the official index file."""

    symbol: str
    company_name: str

    @property
    def yahoo_ticker(self) -> str:
        return f"{self.symbol}.NS"


@dataclass(frozen=True)
class Nifty50Universe:
    """Validated current constituents and the time this process fetched them."""

    constituents: tuple[Nifty50Constituent, ...]
    checked_at: datetime
    stale: bool = False

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(item.yahoo_ticker for item in self.constituents)


_cached_universe: Nifty50Universe | None = None
_cached_monotonic: float | None = None


def _parse_constituents(csv_text: str) -> tuple[Nifty50Constituent, ...]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("The official NIFTY 50 constituent file has no header.")

    fields = {field.strip().casefold(): field for field in reader.fieldnames}
    symbol_field = fields.get("symbol")
    company_field = fields.get("company name")
    if symbol_field is None or company_field is None:
        raise ValueError("The official NIFTY 50 constituent file has an unexpected format.")

    constituents: list[Nifty50Constituent] = []
    seen: set[str] = set()
    for row in reader:
        symbol = (row.get(symbol_field) or "").strip().upper()
        company_name = (row.get(company_field) or "").strip()
        if not symbol and not company_name:
            continue
        if not _SYMBOL_PATTERN.fullmatch(symbol) or not company_name:
            raise ValueError("The official NIFTY 50 file contains an invalid constituent.")
        if symbol in seen:
            raise ValueError("The official NIFTY 50 file contains duplicate symbols.")
        seen.add(symbol)
        constituents.append(
            Nifty50Constituent(symbol=symbol, company_name=company_name)
        )

    if len(constituents) != 50:
        raise ValueError(
            "The official NIFTY 50 file did not contain exactly 50 constituents."
        )
    return tuple(constituents)


def _download_constituents() -> tuple[Nifty50Constituent, ...]:
    request = Request(
        NIFTY50_CONSTITUENTS_URL,
        headers={"User-Agent": "Nifty50InvestmentAdvisor/0.1"},
    )
    with urlopen(request, timeout=15) as response:
        content = response.read(256_000)
    return _parse_constituents(content.decode("utf-8-sig"))


def get_nifty50_universe(*, force_refresh: bool = False) -> Nifty50Universe:
    """Return a validated universe, refreshing the official file every six hours.

    If refresh fails after a successful fetch in this process, return that cached
    set marked stale. With no cache, fail clearly instead of silently reverting
    to an incomplete or outdated ticker list.
    """
    global _cached_universe, _cached_monotonic

    now = time.monotonic()
    if (
        not force_refresh
        and _cached_universe is not None
        and _cached_monotonic is not None
        and now - _cached_monotonic < _CACHE_SECONDS
    ):
        return _cached_universe

    try:
        constituents = _download_constituents()
    except Exception as exc:
        if _cached_universe is not None:
            _cached_universe = Nifty50Universe(
                constituents=_cached_universe.constituents,
                checked_at=_cached_universe.checked_at,
                stale=True,
            )
            _cached_monotonic = now
            return _cached_universe
        raise RuntimeError(
            "Could not load the current NIFTY 50 constituents from NSE Indices. "
            "Check the connection and try again."
        ) from exc

    _cached_universe = Nifty50Universe(
        constituents=constituents,
        checked_at=datetime.now(UTC),
    )
    _cached_monotonic = now
    return _cached_universe


def get_nifty50_constituent(ticker: str) -> Nifty50Constituent | None:
    """Look up a current constituent by Yahoo Finance ticker."""
    normalized = ticker.strip().upper()
    for item in get_nifty50_universe().constituents:
        if item.yahoo_ticker == normalized:
            return item
    return None
