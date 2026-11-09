"""Unit tests for structured news retrieval (``retrieve_news``).

The real RSS tool is mocked, so no network or LLM is involved. These tests
verify the filtering contract: articles must keep their original URLs, and
entries without a title or an http(s) URL are dropped rather than fixed up.
"""

from unittest.mock import patch

from nifty50_investment_advisor.news_research import retrieve_news


def _invoke_with_tool_result(tool_result):
    with patch(
        "nifty50_investment_advisor.news_research.search_market_news"
    ) as tool_mock:
        tool_mock.invoke.return_value = tool_result
        return retrieve_news(query="NIFTY 50 India stock market", max_results=3)


def test_valid_articles_keep_original_urls():
    result = _invoke_with_tool_result(
        {
            "ok": True,
            "query": "NIFTY 50 India stock market",
            "source": "Google News RSS",
            "articles": [
                {
                    "title": "Sensex closes higher",
                    "publisher": "Example Publisher",
                    "url": "https://example.com/sensex-close",
                },
                {
                    "title": "Nifty opens flat",
                    "publisher": "Example Publisher",
                    "url": "http://example.com/nifty-open",
                },
            ],
            "disclaimer": None,
        }
    )

    assert result["ok"] is True
    assert result["articles_returned"] == 2
    assert [a["url"] for a in result["articles"]] == [
        "https://example.com/sensex-close",
        "http://example.com/nifty-open",
    ]


def test_articles_without_title_or_url_are_dropped():
    result = _invoke_with_tool_result(
        {
            "ok": True,
            "query": "NIFTY 50 India stock market",
            "source": "Google News RSS",
            "articles": [
                {"title": "", "url": "https://example.com/empty-title"},
                {"title": "   ", "url": "https://example.com/blank-title"},
                {"title": "No URL at all"},
                {"title": "None URL", "url": None},
                {"title": "Relative URL", "url": "/news/no-scheme"},
                {"title": "Unrelated scheme", "url": "ftp://example.com/x"},
                {"title": "Kept", "url": "https://example.com/kept"},
                "not-a-dict article",
            ],
            "disclaimer": None,
        }
    )

    assert result["ok"] is True
    assert result["articles_returned"] == 1
    assert result["articles"][0]["url"] == "https://example.com/kept"


def test_tool_failure_is_preserved_with_empty_articles():
    result = _invoke_with_tool_result(
        {"ok": False, "error": "RSS request failed.", "articles": []}
    )

    assert result["ok"] is False
    assert result["articles"] == []
    assert result["error"] == "RSS request failed."


def test_unexpected_tool_response_returns_failure_dict():
    result = _invoke_with_tool_result(None)

    assert result["ok"] is False
    assert result["articles"] == []
    assert "unexpected response" in result["error"]


def test_response_fields_come_from_tool_output():
    result = _invoke_with_tool_result(
        {
            "ok": True,
            "query": "Reliance Industries news",
            "source": "Google News RSS",
            "disclaimer": "Headlines and snippets only.",
            "articles": [
                {
                    "title": "Reliance reports quarterly results",
                    "url": "https://example.com/reliance-results",
                }
            ],
        }
    )

    assert result["query"] == "Reliance Industries news"
    assert result["source"] == "Google News RSS"
    assert result["disclaimer"] == "Headlines and snippets only."
    assert result["articles_returned"] == 1
