"""Single-stock research orchestration tests with stubbed services."""

from datetime import UTC, datetime
from unittest.mock import patch

from nifty50_investment_advisor import research
from nifty50_investment_advisor.reports import ResearchReport
from nifty50_investment_advisor.universe import Nifty50Constituent, Nifty50Universe

TEST_UNIVERSE = Nifty50Universe(
    constituents=(
        Nifty50Constituent(symbol="RELIANCE", company_name="Reliance Industries Limited"),
        Nifty50Constituent(symbol="TCS", company_name="Tata Consultancy Services Limited"),
    ),
    checked_at=datetime(2026, 10, 23, tzinfo=UTC),
)


def _fake_market_data():
    return {
        "ok": True,
        "market_data": {"ok": True, "latest_close": 2500.0, "latest_date": "2026-10-22"},
        "technical_indicators": {"ok": True, "indicators": {}},
        "fundamentals": {"ok": True, "trailing_pe": 28.0},
        "retrieval_status": {"market_data": "success"},
        "retrieval_errors": {},
    }


def _fake_news_result(articles=None):
    return {
        "ok": True,
        "query": "Reliance Industries stock India latest news",
        "source": "Google News RSS",
        "articles_returned": len(articles or []),
        "articles": articles or [],
        "disclaimer": None,
    }


def _fake_agent_result(content: str = "Test analysis from stub agent."):
    return {
        "messages": [
            type("FakeAIMessage", (), {"type": "ai", "content": content})()
        ]
    }


def _run_research_starts_with_universe(monkeypatch) -> None:
    monkeypatch.setattr(research, "get_nifty50_universe", lambda: TEST_UNIVERSE)


def test_run_research_success_builds_validated_report(monkeypatch):
    _run_research_starts_with_universe(monkeypatch)

    fake_market = _fake_market_data()
    fake_news = _fake_news_result(
        [
            {
                "title": "Reliance shares rise",
                "publisher": "Example",
                "published": "2026-10-22T10:00:00Z",
                "summary": "Shares rose.",
                "url": "https://example.com/reliance-rise",
            }
        ]
    )

    with (
        patch.object(research, "_retrieve_market_research", return_value=research.ResearchData.model_validate(fake_market)) as retrieve_mock,
        patch.object(research, "retrieve_news", return_value=fake_news),
        patch.object(research, "create_investment_agent") as factory,
    ):
        factory.return_value.invoke.return_value = _fake_agent_result()
        result = research.run_research("Review Reliance Industries")

    assert result["ok"] is True
    assert result["ticker"] == "RELIANCE.NS"
    assert result["analysis"] == "Test analysis from stub agent."
    # Structured news was pre-retrieved, so the news subagent must be off.
    assert factory.call_args.kwargs.get("include_news_subagent") is False
    assert retrieve_mock.called

    report = ResearchReport.model_validate(result["report"])
    assert report.ticker == "RELIANCE.NS"
    assert len(report.uncertainty) >= 1
    assert len(report.risks) >= 1
    assert any(item.evidence_type == "news" for item in report.evidence)


def test_run_research_without_news_enables_news_subagent(monkeypatch):
    _run_research_starts_with_universe(monkeypatch)

    fake_market = _fake_market_data()
    fake_news = {"ok": False, "error": "RSS failed.", "articles": []}

    with (
        patch.object(research, "_retrieve_market_research", return_value=research.ResearchData.model_validate(fake_market)),
        patch.object(research, "retrieve_news", return_value=fake_news),
        patch.object(research, "create_investment_agent") as factory,
    ):
        factory.return_value.invoke.return_value = _fake_agent_result()
        result = research.run_research("Review Reliance Industries")

    assert factory.call_args.kwargs.get("include_news_subagent") is True
    assert result["ok"] is True


def test_run_research_agent_error_still_returns_report(monkeypatch):
    _run_research_starts_with_universe(monkeypatch)

    fake_market = _fake_market_data()
    fake_news = {"ok": False, "articles": []}

    with (
        patch.object(research, "_retrieve_market_research", return_value=research.ResearchData.model_validate(fake_market)),
        patch.object(research, "retrieve_news", return_value=fake_news),
        patch.object(research, "create_investment_agent") as factory,
    ):
        factory.return_value.invoke.side_effect = RuntimeError("Provider boom")
        result = research.run_research("Review Reliance Industries")

    assert result["ok"] is False
    assert "agent_error" in result
    # The deterministic report must still be present when the LLM fails.
    assert result["report"] is not None
    report = ResearchReport.model_validate(result["report"])
    assert report.ticker == "RELIANCE.NS"


def test_run_research_with_structured_news_includes_evidence_in_prompt(monkeypatch):
    _run_research_starts_with_universe(monkeypatch)

    fake_market = _fake_market_data()
    fake_news = _fake_news_result(
        [
            {
                "title": "Unique headline XYZ",
                "publisher": "Example",
                "url": "https://example.com/unique",
                "published": "2026-10-22T10:00:00Z",
                "summary": "Unique summary.",
            }
        ]
    )

    with (
        patch.object(research, "_retrieve_market_research", return_value=research.ResearchData.model_validate(fake_market)),
        patch.object(research, "retrieve_news", return_value=fake_news),
        patch.object(research, "create_investment_agent") as factory,
    ):
        factory.return_value.invoke.return_value = _fake_agent_result()
        research.run_research("Review Reliance Industries")

    prompt = factory.return_value.invoke.call_args.args[0]["messages"][0]["content"]
    assert "STRUCTURED NEWS EVIDENCE" in prompt
    assert "Unique headline XYZ" in prompt
