"""Test NVIDIA tool calling with the real market-data tool, without Deep Agents."""

from langchain_core.messages import HumanMessage

from nifty50_investment_advisor.model_provider import create_chat_model
from nifty50_investment_advisor.tools.market_data import get_market_data


def main() -> int:
    try:
        print("Creating the configured NVIDIA model...")
        model = create_chat_model()
        model_with_tools = model.bind_tools([get_market_data])

        print("Requesting one real NIFTY 50 market-data tool call...")
        response = model_with_tools.invoke(
            [
                HumanMessage(
                    content=(
                        "Call get_market_data exactly once with "
                        "symbol='^NSEI', period='5d', interval='1d'. "
                        "Do not answer until you have requested the tool."
                    )
                )
            ]
        )

        if not response.tool_calls:
            print("FAIL: The model did not request a tool call.")
            print("Response:", response.content)
            return 1

        call = response.tool_calls[0]
        print("Requested tool:", call["name"])
        print("Arguments:", call["args"])

        if call["name"] != "get_market_data":
            print("FAIL: The model requested an unexpected tool.")
            return 1

        print("\nExecuting the actual market-data tool...")
        result = get_market_data.invoke(call["args"])
        print("Tool result:")
        print(result)

        if not result.get("ok"):
            print("\nFAIL: The market-data tool returned an error.")
            return 1

        print("\nPASS: NVIDIA requested and executed the real market-data tool.")
        return 0

    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
