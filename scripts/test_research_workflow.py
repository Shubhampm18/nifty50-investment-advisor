from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow running this script directly from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nifty50_investment_advisor.research import run_research
from nifty50_investment_advisor.reports import ResearchReport


def main() -> int:
    question = (
        "Summarize the latest available NIFTY 50 market news. "
        "Identify the reported market direction, important developments, "
        "possible risks, and uncertainties. Use verifiable sources and "
        "do not invent facts. This is educational research only, not "
        "a recommendation to buy or sell securities."
    )

    print("=" * 72)
    print("NIFTY 50 RESEARCH WORKFLOW TEST")
    print("=" * 72)
    print("Question:", question)
    print("\nRunning research workflow...\n")

    try:
        result: dict[str, Any] = run_research(question)
    except Exception as exc:
        print("Research workflow raised an exception:")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    if not isinstance(result, dict):
        print("ERROR: run_research() did not return a dictionary.")
        print("Actual result:", repr(result))
        return 1

    print("\n" + "=" * 72)
    print("RESEARCH ANALYSIS")
    print("=" * 72)

    analysis = result.get("analysis")

    if not isinstance(analysis, str) or not analysis.strip():
        print("ERROR: No research analysis was returned.")
        print("Result keys:", list(result.keys()))
        return 1

    print(analysis)

    # Validate the structured news retrieval result.
    news = result.get("news")

    print("\n" + "=" * 72)
    print("STRUCTURED NEWS EVIDENCE")
    print("=" * 72)

    if not isinstance(news, dict):
        print("ERROR: The news result is missing or is not a dictionary.")
        print("News result:", repr(news))
        return 1

    articles = news.get("articles", [])
    if not isinstance(articles, list):
        print("ERROR: The news articles field is not a list.")
        print("Articles value:", repr(articles))
        return 1

    print("Source:", news.get("source", "Unknown"))
    print("Query:", news.get("query", question))
    print("Retrieval status:", news.get("ok"))
    print("Articles:", len(articles))

    if news.get("error"):
        print("Retrieval error:", news["error"])

    for index, article in enumerate(articles, start=1):
        if not isinstance(article, dict):
            print(f"\n{index}. Invalid article record: {article!r}")
            continue

        print(f"\n{index}. {article.get('title', 'Untitled')}")
        print("   Publisher:", article.get("publisher") or "Unknown")
        print("   Published:", article.get("published") or "Unknown")
        print("   URL:", article.get("url") or "Missing")
        if article.get("summary"):
            print("   Summary:", article["summary"])

    if news.get("ok") is not True:
        print("\nWARNING: Structured news retrieval did not succeed.")

    if not articles:
        print("WARNING: No structured news articles were returned.")
        print(
            "The analysis may have used another retrieval path. "
            "Do not treat the analysis itself as proof that structured "
            "news retrieval succeeded."
        )

    # Validate the structured research report.
    print("\n" + "=" * 72)
    print("STRUCTURED RESEARCH REPORT")
    print("=" * 72)

    report_data = result.get("report")

    if not isinstance(report_data, dict):
        print("ERROR: The report is missing or is not a dictionary.")
        print("Report value:", repr(report_data))
        return 1

    try:
        report = ResearchReport.model_validate(report_data)
    except Exception as exc:
        print("ERROR: The structured report failed validation.")
        print(f"{type(exc).__name__}: {exc}")
        print("\nRaw report:")
        print(json.dumps(report_data, indent=2, ensure_ascii=False, default=str))
        return 1

    print("Report validation: PASSED")
    print("Ticker:", report.ticker)
    print("Summary:", report.summary)
    print("Conclusion:", report.conclusion)

    print("\nUncertainties:")
    for item in report.uncertainty:
        print(f"- {item}")

    print("\nRisks:")
    for item in report.risks:
        print(f"- {item}")

    print("\nEvidence items:", len(report.evidence))
    for index, item in enumerate(report.evidence, start=1):
        print(f"\n{index}. {item.source_name}")
        print("   Claim:", item.claim)
        print("   URL:", item.source_url)
        print("   Published:", item.published_at or "Unknown")

    # A missing structured-news result is reported clearly, but does not
    # automatically fail the entire test if analysis and report are valid.
    print("\n" + "=" * 72)
    print("WORKFLOW TEST SUMMARY")
    print("=" * 72)
    print("Analysis returned: YES")
    print("Report validated: YES")
    print("Structured news retrieval:", news.get("ok"))
    print("Structured articles returned:", len(articles))
    print("Structured report evidence:", len(report.evidence))

    if news.get("ok") is not True or not articles:
        print(
            "\nRESULT: PARTIAL SUCCESS — analysis and report are available, "
            "but structured news retrieval needs investigation."
        )
    else:
        print("\nRESULT: SUCCESS — analysis, structured news, and report validated.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
