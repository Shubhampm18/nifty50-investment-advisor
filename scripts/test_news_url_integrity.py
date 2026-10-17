"""Verify that real news article URLs survive JSON serialization."""

import json

from nifty50_investment_advisor.tools.news_data import search_market_news


def main() -> None:
    print("Fetching real news results from Google News RSS...")

    result = search_market_news.invoke(
        {
            "query": "NIFTY 50 India stock market",
            "max_results": 3,
        }
    )

    if not result.get("ok"):
        print("FAIL: News retrieval failed.")
        print(result)
        raise SystemExit(1)

    # Simulate passing the complete tool result through a JSON boundary.
    serialized = json.dumps(result, ensure_ascii=False)
    restored = json.loads(serialized)

    articles = restored.get("articles", [])
    print(f"\nArticles returned: {len(articles)}")

    for index, article in enumerate(articles, start=1):
        url = article.get("url", "")
        print(f"\nArticle {index}: {article.get('title', '(no title)')}")
        print(f"Publisher: {article.get('publisher')}")
        print(f"URL length: {len(url)}")
        print(f"URL complete: {url.startswith(('https://', 'http://'))}")
        print(f"URL: {url}")

        assert url.startswith(("https://", "http://")), f"Article {index} has no valid URL"

    assert len(articles) > 0, "No articles were returned."

    print("\nPASS: Original URLs survived JSON serialization.")


if __name__ == "__main__":
    main()
