
"""Research orchestration for the NIFTY 50 Investment Advisor."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

from nifty50_investment_advisor.agent import create_investment_agent
from nifty50_investment_advisor.news_research import retrieve_news
from nifty50_investment_advisor.reports import (
    EvidenceItem,
    ResearchData,
    ResearchReport,
)
from nifty50_investment_advisor.tools.fundamentals import (
    get_company_fundamentals,
)
from nifty50_investment_advisor.tools.market_data import get_market_data
from nifty50_investment_advisor.tools.technical_indicators import (
    get_technical_indicators,
)


DISCLAIMER = (
    "This report is for educational and informational purposes only. "
    "It is not personalized financial advice. Market data may be delayed, "
    "incomplete, or revised. Historical performance and technical indicators "
    "do not guarantee future returns. No trades are executed."
)

INDEX_TICKERS = {"^NSEI", "^NSEBANK", "^BSESN"}

TICKER_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("bank nifty", "nifty bank"), "^NSEBANK"),
    (("sensex", "bse sensex"), "^BSESN"),
    (("nifty 50", "nifty50", "nifty"), "^NSEI"),
    (("reliance industries", "reliance"), "RELIANCE.NS"),
    (("tata consultancy services", "tcs"), "TCS.NS"),
    (("infosys",), "INFY.NS"),
    (("hdfc bank",), "HDFCBANK.NS"),
    (("icici bank",), "ICICIBANK.NS"),
    (("bharti airtel", "airtel"), "BHARTIARTL.NS"),
]


def _report_ticker(question: str) -> str:
    """Infer a supported index or company ticker from the question."""
    normalized = question.casefold()

    # Prefer an explicitly named company over a general market reference.
    company_patterns = TICKER_PATTERNS[3:]
    index_patterns = TICKER_PATTERNS[:3]

    for patterns, ticker in company_patterns:
        if any(
            re.search(rf"\b{re.escape(pattern)}\b", normalized)
            for pattern in patterns
        ):
            return ticker

    # Recognize common Yahoo Finance ticker symbols when explicitly supplied.
    ticker_match = re.search(
        r"\b(RELIANCE\.NS|TCS\.NS|INFY\.NS|HDFCBANK\.NS|"
        r"ICICIBANK\.NS|BHARTIARTL\.NS)\b",
        question,
        re.IGNORECASE,
    )
    if ticker_match:
        return ticker_match.group(1).upper()

    for patterns, ticker in index_patterns:
        if any(pattern in normalized for pattern in patterns):
            return ticker

    # Broad Indian-market questions default to the NIFTY 50 index.
    general_market_terms = (
        "indian stock market",
        "india stock market",
        "indian equity market",
        "market today",
        "market outlook",
        "market analysis",
        "stock market",
        "nifty market",
    )
    if any(term in normalized for term in general_market_terms):
        return "^NSEI"

    return "INDIA-MARKET"


def _news_query(question: str) -> str:
    """Create a focused news query for common Indian market entities."""
    normalized = question.casefold()

    entity_queries = [
        (("bank nifty", "nifty bank"), "Bank Nifty Indian financial market"),
        (("sensex",), "BSE Sensex Indian stock market"),
        (("reliance",), "Reliance Industries stock India"),
        (("tata consultancy", "tcs"), "Tata Consultancy Services TCS stock India"),
        (("infosys",), "Infosys stock India"),
        (("hdfc bank",), "HDFC Bank stock India"),
        (("icici bank",), "ICICI Bank stock India"),
        (("bharti airtel", "airtel"), "Bharti Airtel stock India"),
        (("rbi", "reserve bank"), "Reserve Bank of India monetary policy"),
        (("inflation",), "India inflation economic news"),
        (("nifty",), "NIFTY 50 Indian stock market"),
    ]

    for terms, query in entity_queries:
        if any(term in normalized for term in terms):
            return f"{query} latest news"

    return "Indian stock market latest financial and economic news"


def _parse_published_date(value: Any) -> datetime | None:
    """Parse common RSS and ISO publication-date formats."""
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed


def _extract_articles(news: Any) -> list[dict[str, Any]]:
    """Normalize common news-result shapes without inventing articles."""
    if isinstance(news, list):
        return [item for item in news if isinstance(item, dict)]

    if not isinstance(news, dict):
        return []

    for key in ("articles", "results", "items", "news"):
        value = news.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def _quote_url(symbol: str) -> str:
    """Return the Yahoo Finance quote URL for a ticker."""
    return f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/"


def _result_succeeded(result: Any) -> bool:
    return isinstance(result, dict) and result.get("ok") is True


def _retrieve_tool(
    tool: Any,
    arguments: dict[str, Any],
    symbol: str,
    tool_name: str,
) -> dict[str, Any]:
    """Call one tool independently and retain its error if it fails."""
    try:
        result = tool.invoke(arguments)
        if isinstance(result, dict):
            return result

        return {
            "ok": False,
            "symbol": symbol,
            "error": (
                f"{tool_name} returned an unexpected result type: "
                f"{type(result).__name__}"
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "symbol": symbol,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _retrieve_market_research(ticker: str) -> ResearchData:
    """Retrieve market, technical, and applicable fundamental data."""
    data = ResearchData()

    if ticker == "INDIA-MARKET":
        message = (
            "Could not infer a supported company or index ticker from the "
            "question. Specify a supported stock or index to retrieve "
            "market data."
        )
        data.retrieval_status = {
            "market_data": "not_run",
            "technical_indicators": "not_run",
            "fundamentals": "not_run",
        }
        data.retrieval_errors = {
            "ticker_resolution": message,
        }
        return data

    data.market_data = _retrieve_tool(
        get_market_data,
        {
            "symbol": ticker,
            "period": "1mo",
            "interval": "1d",
        },
        ticker,
        "Market data",
    )
    data.retrieval_status["market_data"] = (
        "success" if _result_succeeded(data.market_data) else "failed"
    )

    data.technical_indicators = _retrieve_tool(
        get_technical_indicators,
        {
            "symbol": ticker,
            "period": "6mo",
        },
        ticker,
        "Technical indicators",
    )
    data.retrieval_status["technical_indicators"] = (
        "success"
        if _result_succeeded(data.technical_indicators)
        else "failed"
    )

    if ticker in INDEX_TICKERS:
        data.fundamentals = None
        data.retrieval_status["fundamentals"] = "not_applicable"
    else:
        data.fundamentals = _retrieve_tool(
            get_company_fundamentals,
            {"symbol": ticker},
            ticker,
            "Company fundamentals",
        )
        data.retrieval_status["fundamentals"] = (
            "success" if _result_succeeded(data.fundamentals) else "failed"
        )

    for name in ("market_data", "technical_indicators", "fundamentals"):
        result = getattr(data, name)
        if isinstance(result, dict) and result.get("ok") is not True:
            error = result.get("error", "Tool did not return a successful result")
            data.retrieval_errors[name] = str(error)

    return data


def _build_market_context(data: ResearchData) -> str:
    """Serialize retrieved results for the agent without losing fields."""
    return (
        "STRUCTURED MARKET DATA:\n"
        "The following results were retrieved by the application. "
        "Use these results directly; do not repeat their tool calls. "
        "Preserve missing values as missing, and report retrieval errors.\n"
        f"{json.dumps(data.model_dump(mode='json'), indent=2, default=str)}"
    )


def _build_news_context(news: Any) -> str:
    """Serialize available news results for direct analysis by the agent."""
    return (
        "STRUCTURED NEWS EVIDENCE:\n"
        "The following news retrieval results are supplied by the application. "
        "Analyze them directly; do not repeat news retrieval calls. "
        "A headline or snippet is not proof of causation or of the full "
        "article's contents.\n"
        f"{json.dumps(news, indent=2, default=str)}"
    )


def _build_research_report(
    question: str,
    analysis: str,
    news: Any,
    data: ResearchData,
    ticker: str,
) -> ResearchReport:
    """Build a validated report while retaining raw retrieval results."""
    evidence: list[EvidenceItem] = []
    missing_information: list[str] = []
    uncertainties: list[str] = [
        "Historical market data and technical indicators do not reliably "
        "predict future returns.",
        "Market data and third-party company information may be delayed, "
        "incomplete, or revised.",
    ]
    risks: list[str] = [
        "Market prices can move against an investment thesis, including "
        "because of unexpected events.",
        "This analysis does not account for an individual's financial "
        "position, investment horizon, or risk tolerance.",
    ]

    market = data.market_data
    if _result_succeeded(market):
        latest_close = market.get("latest_close")
        latest_date = market.get("latest_date")
        previous_close = market.get("previous_close")
        change_percent = market.get("change_percent")

        claim = (
            f"Latest close for {ticker}: {latest_close} on {latest_date}; "
            f"previous close: {previous_close}; "
            f"reported percentage change: {change_percent}."
        )
        evidence.append(
            EvidenceItem(
                claim=claim[:1000],
                source_name=str(market.get("source") or "Yahoo Finance"),
                source_url=_quote_url(ticker),
                evidence_type="market_data",
                limitations=str(
                    market.get("disclaimer")
                    or "Third-party market data may be delayed or revised."
                )[:1000],
            )
        )
    else:
        missing_information.append(
            "Market data retrieval failed or was not run. "
            + str((market or {}).get("error", "No successful result returned."))
        )

    technical = data.technical_indicators
    if _result_succeeded(technical):
        indicators = technical.get("indicators") or {}
        indicator_summary = ", ".join(
            f"{key}={value}"
            for key, value in indicators.items()
        )
        claim = (
            f"Technical indicators for {ticker} as of "
            f"{technical.get('latest_date')}: {indicator_summary or 'no indicator values returned'}."
        )
        evidence.append(
            EvidenceItem(
                claim=claim[:1000],
                source_name=str(technical.get("source") or "Yahoo Finance"),
                source_url=_quote_url(ticker),
                evidence_type="technical",
                limitations=str(
                    technical.get("disclaimer")
                    or "Indicators describe historical observations only."
                )[:1000],
            )
        )
    else:
        missing_information.append(
            "Technical-indicator retrieval failed or was not run. "
            + str(
                (technical or {}).get(
                    "error", "No successful result returned."
                )
            )
        )

    fundamentals = data.fundamentals
    company_name: str | None = None

    if _result_succeeded(fundamentals):
        company_name = fundamentals.get("company")
        metrics = fundamentals.get("metrics") or {}
        metric_summary = ", ".join(
            f"{key}={value}" for key, value in metrics.items()
        )
        claim = (
            f"Company profile and fundamentals retrieved for "
            f"{company_name or ticker}. "
            f"Reported metrics: {metric_summary or 'none returned'}."
        )
        evidence.append(
            EvidenceItem(
                claim=claim[:1000],
                source_name=str(
                    fundamentals.get("source") or "Yahoo Finance"
                ),
                source_url=_quote_url(ticker),
                evidence_type="fundamentals",
                limitations=str(
                    fundamentals.get("disclaimer")
                    or "Third-party fundamentals may be incomplete or revised."
                )[:1000],
            )
        )
    elif data.retrieval_status.get("fundamentals") == "failed":
        missing_information.append(
            "Company-fundamentals retrieval failed. "
            + str(
                (fundamentals or {}).get(
                    "error", "No successful result returned."
                )
            )
        )

    for article in _extract_articles(news):
        title = article.get("title") or article.get("headline")
        url = article.get("url") or article.get("link")
        if not title or not isinstance(url, str):
            continue
        if not url.startswith(("https://", "http://")):
            continue

        published = (
            article.get("published_at")
            or article.get("published")
            or article.get("pubDate")
            or article.get("date")
        )

        try:
            evidence.append(
                EvidenceItem(
                    claim=str(title)[:1000],
                    source_name=str(
                        article.get("source")
                        or article.get("publisher")
                        or "News source"
                    )[:200],
                    source_url=url,
                    published_at=_parse_published_date(published),
                    evidence_type="news",
                    limitations=(
                        "This evidence may be based on headline or snippet "
                        "metadata; the full article may not have been reviewed."
                    ),
                )
            )
        except Exception:
            # Ignore malformed evidence records rather than fabricate citations.
            continue

    if data.retrieval_errors.get("ticker_resolution"):
        missing_information.append(data.retrieval_errors["ticker_resolution"])

    if not _extract_articles(news):
        missing_information.append(
            "No structured news articles were available for this report."
        )
        uncertainties.append(
            "News coverage may be incomplete; no structured article records "
            "were available to corroborate current events."
        )

    if data.retrieval_status.get("fundamentals") == "not_applicable":
        uncertainties.append(
            "Company-level fundamentals do not apply to an index."
        )

    summary = analysis.strip() or (
        "The research agent did not return a usable analysis. "
        "Review the retrieval status and errors before drawing conclusions."
    )

    conclusion = (
        "This report summarizes retrieved evidence and the research agent's "
        "interpretation. Review the data retrieval status, source limitations, "
        "uncertainties, and risks before drawing conclusions. It is not a "
        "personalized investment recommendation."
    )

    return ResearchReport(
        ticker=ticker,
        company_name=company_name,
        generated_at=datetime.now(UTC),
        research_question=question,
        summary=summary[:5000],
        data=data,
        evidence=evidence,
        uncertainty=uncertainties,
        risks=risks,
        missing_information=missing_information,
        conclusion=conclusion,
        disclaimer=DISCLAIMER,
    )


def run_research(question: str) -> dict[str, Any]:
    """Run data retrieval, news retrieval, agent analysis, and report validation."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Research question must not be empty.")

    question = question.strip()
    ticker = _report_ticker(question)

    # Retrieve each data source independently so one failure does not discard
    # successful results from the other sources.
    data = _retrieve_market_research(ticker)

    news_query = _news_query(question)
    try:
        news = retrieve_news(news_query)
    except Exception as exc:
        news = {
            "ok": False,
            "query": news_query,
            "articles": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    articles = _extract_articles(news)
    has_structured_news = bool(articles)

    # The main agent receives retrieved data as structured context and is
    # instructed not to call the same tools again.
    context_parts = [
        question,
        _build_market_context(data),
    ]
    if has_structured_news:
        context_parts.append(_build_news_context(news))

    agent_input = "\n\n".join(context_parts)
    agent = create_investment_agent(
        include_news_subagent=not has_structured_news
    )

    analysis = ""
    agent_error: str | None = None

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": agent_input}]})

        if isinstance(result, dict):
            messages = result.get("messages", [])
            if messages:
                for message in reversed(messages):
                    content = (
                        message.get("content")
                        if isinstance(message, dict)
                        else getattr(message, "content", None)
                    )
                    if isinstance(content, str) and content.strip():
                        analysis = content.strip()
                        break

            if not analysis:
                output = result.get("output")
                if isinstance(output, str):
                    analysis = output.strip()
                elif output is not None:
                    analysis = str(output).strip()
        elif isinstance(result, str):
            analysis = result.strip()
        else:
            analysis = str(result).strip()

    except Exception as exc:
        agent_error = f"{type(exc).__name__}: {exc}"
        analysis = (
            "The research agent could not complete its analysis. "
            "See the agent error in the returned result and review the "
            "retrieved structured data."
        )

    if agent_error:
        data.retrieval_errors["agent"] = agent_error

    report = _build_research_report(
        question=question,
        analysis=analysis,
        news=news,
        data=data,
        ticker=ticker,
    )

    return {
        "ok": bool(analysis.strip()) and agent_error is None,
        "question": question,
        "ticker": ticker,
        "analysis": analysis,
        "news": news,
        "agent_error": agent_error,
        "report": report.model_dump(mode="json"),
    }
