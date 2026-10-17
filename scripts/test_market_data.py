"""Test real NIFTY 50 market-data retrieval."""

from nifty50_investment_advisor.tools.market_data import get_market_data


def main() -> int:
    print("Requesting historical NIFTY 50 data from Yahoo Finance...")

    result = get_market_data.invoke(
        {
            "symbol": "^NSEI",
            "period": "5d",
            "interval": "1d",
        }
    )

    if not result.get("ok"):
        print("\nFAIL: Market-data retrieval was unsuccessful.")
        print("Details:", result)
        return 1

    print("\nPASS: Market data was retrieved successfully.")
    print("Symbol:", result["symbol"])
    print("Latest date:", result["latest_date"])
    print("Latest close:", result["latest_close"])
    print("Previous close:", result["previous_close"])
    print("Change (%):", result["change_percent"])
    print("Observations returned:", result["observations_returned"])
    print("Source:", result["source"])

    print("\nRecent observations:")

    for observation in result["recent_observations"]:
        print(observation)

    print("\nNote:", result["disclaimer"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
