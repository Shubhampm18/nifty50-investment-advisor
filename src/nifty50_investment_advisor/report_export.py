"""Pure formatting helpers for exporting saved research reports.

No Streamlit, database, network, or LLM involvement here — the UI and CLI
hand these functions the already-JSON-safe dicts returned by
``database.get_research_report`` / ``database.get_stock_comparison``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from nifty50_investment_advisor.reports import (
    ResearchReport,
    StockComparisonReport,
)


def _as_json_dict(
    report: ResearchReport | StockComparisonReport | dict[str, Any],
) -> dict[str, Any]:
    """Return a JSON-safe dict for either report kind."""
    if isinstance(report, dict):
        return report
    return report.model_dump(mode="json")


def export_report_json(
    report: ResearchReport | StockComparisonReport | dict[str, Any],
) -> str:
    """Serialize a report faithfully for archiving and round-tripping."""
    return json.dumps(
        _as_json_dict(report),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _esc(text: Any) -> str:
    """Escape Markdown structural characters in untrusted text."""
    value = str(text or "")
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("#", "\\#")
    )


def _bullet(lines: list[str], items: list[str] | None, empty: str) -> None:
    if not items:
        lines.append(f"- {empty}")
        return
    for item in items:
        lines.append(f"- {_esc(item)}")


def export_report_markdown(report: dict[str, Any]) -> str:
    """Render a single-stock report as human-readable Markdown."""
    lines: list[str] = [
        f"# Research report: {_esc(report.get('ticker', 'Unknown'))}",
        "",
    ]
    if report.get("company_name"):
        lines.append(f"**Company:** {_esc(report['company_name'])}")
    if report.get("generated_at"):
        lines.append(f"**Generated:** {_esc(report['generated_at'])}")
    if report.get("stored_at"):
        lines.append(f"**Stored:** {_esc(report['stored_at'])}")
    lines += [
        "",
        "## Research question",
        _esc(report.get("research_question", "")),
        "",
        "## Summary",
        _esc(report.get("summary", "")),
        "",
        "## Evidence",
    ]

    evidence = report.get("evidence") or []
    if not evidence:
        lines.append("- No structured evidence items were available.")
    for index, item in enumerate(evidence, start=1):
        source = _esc(item.get("source_name", "Source"))
        evidence_type = _esc(item.get("evidence_type", "evidence"))
        claim = _esc(item.get("claim", "No claim provided."))
        url = item.get("source_url")
        lines.append(f"{index}. **{source}** ({evidence_type}): {claim}")
        if url:
            lines.append(f"   - URL: {_esc(url)}")
        if item.get("published_at"):
            lines.append(f"   - Published: {_esc(item['published_at'])}")
        if item.get("limitations"):
            lines.append(f"   - Limitations: {_esc(item['limitations'])}")

    lines += ["", "## Uncertainty"]
    _bullet(lines, report.get("uncertainty"), "No uncertainty recorded.")
    lines += ["", "## Risks"]
    _bullet(lines, report.get("risks"), "No risks recorded.")
    lines += ["", "## Missing information"]
    _bullet(
        lines,
        report.get("missing_information"),
        "No missing information recorded.",
    )
    lines += [
        "",
        "## Conclusion",
        _esc(report.get("conclusion", "")),
        "",
        f"_{_esc(report.get('disclaimer', ''))}_",
        "",
    ]
    return "\n".join(lines)


def export_comparison_markdown(report: dict[str, Any]) -> str:
    """Render a stock comparison as Markdown, preserving no-winner semantics."""
    lines: list[str] = [
        "# Stock comparison",
        "",
    ]
    tickers = report.get("tickers") or []
    lines.append(f"**Tickers:** {', '.join(_esc(t) for t in tickers)}")
    if report.get("generated_at"):
        lines.append(f"**Generated:** {_esc(report['generated_at'])}")
    if report.get("stored_at"):
        lines.append(f"**Stored:** {_esc(report['stored_at'])}")
    if report.get("universe_stale"):
        lines.append("**Universe:** stale (refresh failed; cached member list used)")
    lines += [
        "",
        "## Research question",
        _esc(report.get("research_question", "")),
        "",
        "## Summary (deterministic — no ranking, no winner selected)",
        _esc(report.get("summary", "")),
        "",
        "## Differences (values returned for multiple tickers)",
    ]

    differences = report.get("differences") or []
    if not differences:
        lines.append("- No comparable differences were returned.")
    else:
        lines.append("| Category | Metric | Ticker | Value | As of | Source |")
        lines.append("|---|---|---|---|---|---|")
        for difference in differences:
            for observation in difference.get("observations", []):
                lines.append(
                    "| {} | {} | {} | {} | {} | {} |".format(
                        _esc(difference.get("category", "")),
                        _esc(difference.get("metric", "")),
                        _esc(observation.get("ticker", "")),
                        _esc(observation.get("value", "")),
                        _esc(observation.get("as_of") or ""),
                        _esc(observation.get("source_name", "")),
                    )
                )

    lines += ["", "## Per-stock notes"]
    for stock in report.get("stocks") or []:
        lines.append(f"### {_esc(stock.get('ticker', 'Unknown'))}")
        nested = stock.get("report") or {}
        lines.append(_esc(nested.get("summary", "")))
        lines.append("")

    lines += ["## Uncertainty"]
    _bullet(lines, report.get("uncertainty"), "No uncertainty recorded.")
    lines += ["", "## Missing information"]
    _bullet(
        lines,
        report.get("missing_information"),
        "No missing information recorded.",
    )
    lines += [
        "",
        "## Conclusion",
        _esc(report.get("conclusion", "")),
        "",
        f"_{_esc(report.get('disclaimer', ''))}_",
        "",
    ]
    return "\n".join(lines)


def export_filename(
    report: dict[str, Any] | ResearchReport | StockComparisonReport,
    report_id: int | None = None,
    fmt: str = "md",
) -> str:
    """Build a sanitized, stable export filename for a report."""
    data = _as_json_dict(report)
    if "tickers" in data and "stocks" in data:
        base = "comparison_" + "_".join(data.get("tickers") or [])
    else:
        base = f"research_{data.get('ticker', 'unknown')}"
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "research"
    parts = [clean]
    if report_id is not None:
        parts.append(str(report_id))
    generated = str(data.get("generated_at") or "")[:10]
    if generated and re.fullmatch(r"\d{4}-\d{2}-\d{2}", generated):
        parts.append(generated)
    extension = "md" if fmt == "md" else "json"
    return "_".join(parts) + f".{extension}"
