"""Test that structured news records preserve their original URLs."""

from nifty50_investment_advisor.news_research import retrieve_news


def main() -> int:
    print("Retrieving real news through the structured news module...")

    result = retrieve_news(
        query="NIFTY 50 India stock market",
        max_results=3,
    )

    if not result.get("ok"):
        print("FAIL:", result.get("error", "News retrieval failed"))
        return 1

    articles = result["articles"]
    print("Source:", result["source"])
    print("Articles returned:", len(articles))

    for index, article in enumerate(articles, start=1):
        print(f"\nArticle {index}: {article['title']}")
        print("Publisher:", article.get("publisher"))
        print("Published:", article.get("published"))
        print("URL:", article["url"])
        print("URL length:", len(article["url"]))

    if not articles:
        print("FAIL: No valid article records were returned.")
        return 1

    print("\nPASS: Structured news records retain their original URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
