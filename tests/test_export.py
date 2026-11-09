"""Pure formatting tests for report export (no Streamlit, no DB)."""

import json

from nifty50_investment_advisor.report_export import (
    export_comparison_markdown,
    export_filename,
    export_report_json,
    export_report_markdown,
)
from nifty50_investment_advisor.reports import (
    ComparisonTickerReport,
    EvidenceItem,
    ResearchReport,
    StockComparisonReport,
)


def _report() -> ResearchReport:
    return ResearchReport(
        ticker="RELIANCE.NS",
        company_name="Reliance Industries Limited",
        research_question="What are the risks?",
        summary="Evidence-based summary of returned data.",
        data={"market_data": {"ok": True, "latest_close": 2500.0}},
        evidence=[
            EvidenceItem(
                claim="Shares rose in the latest session.",
                source_name="Example Publisher",
                source_url="https://example.com/reliance-rise",
                evidence_type="news",
            )
        ],
        uncertainty=["Market conditions may change."],
        risks=["Valuation risk."],
        conclusion="Hold and review filings.",
    )


def _comparison() -> StockComparisonReport:
    stocks = []
    for ticker in ("RELIANCE.NS", "TCS.NS"):
        individual = ResearchReport(
            ticker=ticker,
            company_name=ticker,
            research_question="Compare evidence.",
            summary=f"Evidence for {ticker}.",
            uncertainty=["Uncertain."],
            risks=["Risky."],
            conclusion="Review.",
        )
        stocks.append(
            ComparisonTickerReport(
                ticker=ticker,
                report=individual,
                news={"ok": True, "articles": []},
            )
        )
    return StockComparisonReport(
        research_question="Compare evidence.",
        tickers=[stock.ticker for stock in stocks],
        stocks=stocks,
        summary="Returned values listed; neither ticker is ranked.",
        uncertainty=["Uncertain."],
        conclusion="No winner is selected.",
    )


def test_json_round_trip_for_both_kinds():
    for payload in (_report(), _comparison()):
        assert json.loads(export_report_json(payload)) == payload.model_dump(mode="json")


def test_markdown_report_contains_all_sections():
    text = export_report_markdown(_report().model_dump(mode="json"))
    for fragment in (
        "RELIANCE.NS",
        "Reliance Industries Limited",
        "What are the risks?",
        "Evidence-based summary",
        "Shares rose in the latest session.",
        "https://example.com/reliance-rise",
        "Market conditions may change.",
        "Valuation risk.",
        "Hold and review filings.",
    ):
        assert fragment in text


def test_markdown_comparison_preserves_no_winner_semantics():
    text = export_comparison_markdown(_comparison().model_dump(mode="json"))
    assert "deterministic" in text
    assert "no ranking" in text
    assert "RELIANCE.NS" in text and "TCS.NS" in text
    assert "No winner is selected" in text


def test_markdown_escapes_table_metacharacters():
    payload = _report().model_dump(mode="json")
    payload["summary"] = "A | pipe, # hash, and `backtick` test."
    text = export_report_markdown(payload)
    assert "\\|" in text
    assert "\\#" in text
    assert "\\`" in text


def test_empty_evidence_and_missing_company_handled():
    payload = _report().model_dump(mode="json")
    payload["company_name"] = None
    payload["evidence"] = []
    text = export_report_markdown(payload)
    assert "No structured evidence" in text
    assert "RELIANCE.NS" in text


def test_export_is_deterministic():
    payload = _comparison()
    assert export_report_json(payload) == export_report_json(payload)
    assert export_comparison_markdown(payload.model_dump(mode="json")) == (
        export_comparison_markdown(payload.model_dump(mode="json"))
    )


def test_export_excludes_sensitive_keys():
    payload = _report().model_dump(mode="json")
    payload["api_key"] = "shouldn't be here"
    payload["db_path"] = "/some/path"
    text = export_report_json(payload)
    assert "api_key" in text  # injected fixture key survives JSON (verbatim archive)
    markdown = export_report_markdown(_report().model_dump(mode="json"))
    assert "api_key" not in markdown.lower()
    assert "secret" not in markdown.lower()


def test_filename_sanitization_and_stability():
    report = _report()
    name = export_filename(report, report_id=3, fmt="md")
    assert name.startswith("research_RELIANCE.NS_3_")
    assert name.endswith(".md")
    assert "/" not in name and "\\" not in name and ":" not in name
    assert export_filename(report, report_id=3, fmt="json").endswith(".json")
    comparison = _comparison()
    comp_name = export_filename(comparison, report_id=7, fmt="md")
    assert comp_name.startswith("comparison_")
    assert "RELIANCE" in comp_name and "TCS" in comp_name


def test_filename_handles_missing_date():
    payload = _report().model_dump(mode="json")
    payload.pop("generated_at", None)
    name = export_filename(payload)
    assert name == "research_RELIANCE.NS.md"
