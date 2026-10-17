"""Inspect the size and structure of the real news tool output."""

from langchain_core.messages import AIMessage

from nifty50_investment_advisor.model_provider import create_chat_model
from nifty50_investment_advisor.tools.news_data import search_market_news


def main() -> int:
    print("Creating the configured chat model...")
    model = create_chat_model()

    print("Requesting a compact news-tool call...")
    model_with_tools = model.bind_tools([search_market_news])

    response = model_with_tools.invoke(
        [
            (
                "system",
                "Call search_market_news exactly once. Request three recent "
                "NIFTY 50 Indian stock-market news results. Do not summarize "
                "or reproduce the returned results in your response.",
            ),
            (
                "human",
                "Search for recent NIFTY 50 and Indian stock-market news.",
            ),
        ]
    )

    if not isinstance(response, AIMessage):
        print("Unexpected response type:", type(response).__name__)
        return 1

    if not response.tool_calls:
        print("No tool call was returned.")
        print("Model response:", str(response.content)[:1000])
        return 1

    call = response.tool_calls[0]
    print("\nTool name:", call["name"])
    print("Tool arguments:", call["args"])

    if call["name"] != "search_market_news":
        print("Unexpected tool selected.")
        return 1

    print("\nExecuting the real news tool...")
    result = search_market_news.invoke(call["args"])

    if isinstance(result, str):
        print("Result type: str")
        print("Result character count:", len(result))
        print("Result preview:")
        print(result[:6000])
    else:
        print("Result type:", type(result).__name__)
        print("Result representation length:", len(repr(result)))
        print("Result representation preview:")
        print(repr(result)[:6000])

    print("\nPASS: The real news tool was executed and inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
