"""Retrieve structured news records without relying on LLM-generated URLs."""

from typing import Any

from nifty50_investment_advisor.tools.news_data import search_market_news


def retrieve_news(
    query: str = "NIFTY 50 India stock market",
    max_results: int = 3,
) -> dict[str, Any]:
    """Return original news metadata and URLs from the real RSS tool."""
    result = search_market_news.invoke(
        {
            "query": query,
            "max_results": max_results,
        }
    )

    if not isinstance(result, dict):
        return {
            "ok": False,
            "query": query,
            "error": "The news tool returned an unexpected response.",
            "articles": [],
        }

    if not result.get("ok"):
        return {
            **result,
            "articles": [],
        }

    articles = []

    for article in result.get("articles", []):
        if not isinstance(article, dict):
            continue

        url = article.get("url")
        title = article.get("title")

        # Retain the original URL; never reconstruct it from model output.
        if (
            isinstance(title, str)
            and title.strip()
            and isinstance(url, str)
            and url.startswith(("https://", "http://"))
        ):
            articles.append(dict(article))

    return {
        "ok": True,
        "query": result.get("query", query),
        "source": result.get("source", "Google News RSS"),
        "articles_returned": len(articles),
        "articles": articles,
        "disclaimer": result.get("disclaimer"),
    }
