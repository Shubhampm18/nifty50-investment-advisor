"""Retrieve real Indian-market news from Google News RSS."""

import re
from html import unescape
from typing import Any
from urllib.parse import urlencode

import feedparser
import httpx
from langchain_core.tools import tool

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


def _clean_html(value: str) -> str:
    """Remove markup and normalize whitespace in RSS text."""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


@tool
def search_market_news(
    query: str = "NIFTY 50 India stock market",
    max_results: int = 5,
) -> dict[str, Any]:
    """Search real news articles relevant to the Indian stock market.

    Uses Google News RSS to retrieve article metadata. It does not
    generate or invent headlines.

    Args:
        query: Search terms, such as NIFTY 50, Reliance Industries,
            TCS results, RBI policy, or Indian inflation.
        max_results: Maximum number of articles to return, from 1 to 10.

    Returns:
        Article headlines, publication dates when available, publishers,
        links, available summaries, and source information.
    """
    query = query.strip()

    if not query:
        return {
            "ok": False,
            "query": query,
            "error": "Search query cannot be empty.",
        }

    if len(query) > 200:
        return {
            "ok": False,
            "query": query[:200],
            "error": "Search query must be 200 characters or fewer.",
        }

    if not 1 <= max_results <= 10:
        return {
            "ok": False,
            "query": query,
            "error": "max_results must be between 1 and 10.",
        }

    params = {
        "q": query,
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
    }
    url = f"{GOOGLE_NEWS_RSS_URL}?{urlencode(params)}"

    try:
        response = httpx.get(
            url,
            timeout=25.0,
            follow_redirects=True,
            headers={"User-Agent": ("Nifty50InvestmentResearch/0.1 (educational research tool)")},
        )
        response.raise_for_status()

        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            return {
                "ok": False,
                "query": query,
                "error": "The news feed could not be parsed.",
                "source": "Google News RSS",
            }

        articles = []

        for entry in feed.entries[:max_results]:
            title = _clean_html(str(entry.get("title", "")))
            link = str(entry.get("link", "")).strip()

            # Do not return incomplete entries as valid articles.
            if not title or not link.startswith(("https://", "http://")):
                continue

            source_info = entry.get("source", {})
            publisher = _clean_html(str(source_info.get("title", ""))) if source_info else ""

            summary = _clean_html(str(entry.get("summary", "")))

            articles.append(
                {
                    "title": title,
                    "publisher": publisher or None,
                    "published": entry.get("published"),
                    "summary": summary or None,
                    "url": link,
                }
            )

        return {
            "ok": True,
            "query": query,
            "source": "Google News RSS",
            "feed_url": url,
            "articles_returned": len(articles),
            "articles": articles,
            "disclaimer": (
                "These are search results, not independently verified "
                "claims. Publication dates and summaries depend on the "
                "feed. Open the original article to verify its contents. "
                "An empty result does not prove that no relevant news exists."
            ),
        }

    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "query": query,
            "error": (f"The news provider returned HTTP {exc.response.status_code}."),
            "source": "Google News RSS",
        }
    except httpx.RequestError as exc:
        return {
            "ok": False,
            "query": query,
            "error": (f"The news request failed: {type(exc).__name__}."),
            "source": "Google News RSS",
        }
    except Exception as exc:
        return {
            "ok": False,
            "query": query,
            "error": f"News retrieval failed: {type(exc).__name__}.",
            "source": "Google News RSS",
        }
