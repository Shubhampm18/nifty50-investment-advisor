"""Test real Indian stock-market news retrieval."""

from nifty50_investment_advisor.tools.news_data import search_market_news


def main() -> int:
    print("Searching Google News RSS for Indian market news...")

    result = search_market_news.invoke(
        {
            "query": "NIFTY 50 Indian stock market",
            "max_results": 5,
        }
    )

    if not result.get("ok"):
        print("\nFAIL: News retrieval did not succeed.")
        print(result)
        return 1

    articles = result.get("articles", [])

    print("\nSource:", result.get("source"))
    print("Query:", result.get("query"))
    print("Articles returned:", len(articles))

    for index, article in enumerate(articles, start=1):
        print(f"\n--- Article {index} ---")
        print("Headline:", article["title"])
        print("Publisher:", article["publisher"] or "Not provided")
        print("Published:", article["published"] or "Not provided")
        print("Summary:", article["summary"] or "Not provided")
        print("URL:", article["url"])

    print("\nDisclaimer:", result.get("disclaimer"))

    if not articles:
        print(
            "\nFAIL: The request succeeded, but no usable articles "
            "were returned. Check connectivity or try another query."
        )
        return 1

    print("\nPASS: Real news articles were retrieved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
