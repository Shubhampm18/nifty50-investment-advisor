"""Single-stock ticker resolution and news-query tests (no network, no LLM)."""

from datetime import UTC, datetime

from nifty50_investment_advisor import research
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
            ("SBIN", "State Bank of India"),
            ("TATAMOTORS", "Tata Motors Passenger Vehicles Limited"),
            ("LT", "Larsen & Toubro Limited"),
            ("TITAN", "Titan Company Limited"),
            ("ASHOKLEY", "Ashok Leyland Limited"),
        )
    ),
    checked_at=datetime(2026, 10, 23, tzinfo=UTC),
)


def test_legacy_company_names_still_resolve():
    assert research._report_ticker("Review Reliance Industries", TEST_UNIVERSE) == "RELIANCE.NS"
    assert research._report_ticker("What is TCS doing?", TEST_UNIVERSE) == "TCS.NS"
    assert research._report_ticker("Infosys earnings outlook", TEST_UNIVERSE) == "INFY.NS"
    assert research._report_ticker("HDFC Bank technicals", TEST_UNIVERSE) == "HDFCBANK.NS"
    assert research._report_ticker("ICICI Bank results", TEST_UNIVERSE) == "ICICIBANK.NS"
    assert research._report_ticker("Bharti Airtel news", TEST_UNIVERSE) == "BHARTIARTL.NS"


def test_index_phrases_resolve():
    assert research._report_ticker("Bank Nifty today outlook", TEST_UNIVERSE) == "^NSEBANK"
    assert research._report_ticker("Sensex closing summary", TEST_UNIVERSE) == "^BSESN"
    assert research._report_ticker("NIFTY 50 outlook today", TEST_UNIVERSE) == "^NSEI"
    assert research._report_ticker("Indian stock market today", TEST_UNIVERSE) == "^NSEI"


def test_universe_company_names_resolve():
    assert research._report_ticker("State Bank of India analysis", TEST_UNIVERSE) == "SBIN.NS"
    assert research._report_ticker("Larsen & Toubro outlook", TEST_UNIVERSE) == "LT.NS"
    assert research._report_ticker("Titan Company results", TEST_UNIVERSE) == "TITAN.NS"
    assert research._report_ticker("Ashok Leyland commercial vehicles", TEST_UNIVERSE) == "ASHOKLEY.NS"


def test_full_company_name_with_suffix_resolves():
    assert (
        research._report_ticker(
            "Research Tata Motors Passenger Vehicles Limited business", TEST_UNIVERSE
        )
        == "TATAMOTORS.NS"
    )


def test_explicit_yahoo_symbols_resolve():
    assert research._report_ticker("Review SBIN.NS", TEST_UNIVERSE) == "SBIN.NS"
    assert research._report_ticker("review reliance.ns", TEST_UNIVERSE) == "RELIANCE.NS"


def test_short_aliases_resolve():
    assert research._report_ticker("SBI latest news", TEST_UNIVERSE) == "SBIN.NS"
    assert research._report_ticker("hdfc analysis", TEST_UNIVERSE) == "HDFCBANK.NS"


def test_exact_symbol_word_resolves():
    assert research._report_ticker("What happened to SBIN today?", TEST_UNIVERSE) == "SBIN.NS"


def test_unresolvable_questions_fall_back_to_india_market():
    assert research._report_ticker("Should I buy crypto?", TEST_UNIVERSE) == "INDIA-MARKET"
    assert research._report_ticker("Tell me a joke", TEST_UNIVERSE) == "INDIA-MARKET"
    assert research._report_ticker("", TEST_UNIVERSE) == "INDIA-MARKET"


def test_universe_failure_keeps_explicit_symbol_resolution():
    # When the official member file cannot be reached, explicit Yahoo
    # symbols and index phrases must still resolve (legacy behavior).
    assert research._report_ticker("Review RELIANCE.NS", None) == "RELIANCE.NS"
    assert research._report_ticker("bank nifty outlook") in {"^NSEBANK"}


def test_news_query():
    assert research._news_query("Summarize the latest NIFTY 50 news.") == (
        "NIFTY 50 Indian stock market latest news"
    )
    assert research._news_query("Reliance earnings reaction") == (
        "Reliance Industries stock India latest news"
    )
    assert research._news_query("What did the RBI do to rates?") == (
        "Reserve Bank of India monetary policy latest news"
    )
    assert research._news_query("Totally unrelated question") == (
        "Indian stock market latest financial and economic news"
    )


def test_news_query_legacy_entities():
    assert "Bank Nifty" in research._news_query("Bank Nifty stocks")
    assert "Sensex" in research._news_query("BSE Sensex movement")
    assert "Infosys" in research._news_query("Infosys quarterly results")
