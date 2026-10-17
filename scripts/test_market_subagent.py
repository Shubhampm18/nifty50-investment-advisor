"""Verify that the main Deep Agent delegates market research."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from nifty50_investment_advisor.agent import create_investment_agent


def main() -> int:
    try:
        print("Creating the main Deep Agent and market specialist...")
        agent = create_investment_agent()

        print("Sending a market-data question...")
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "Research the latest available daily NIFTY 50 "
                            "observation. Report its date, closing value, "
                            "previous close, daily percentage change, and source. "
                            "Use the market-research specialist."
                        )
                    )
                ]
            }
        )

        messages = result.get("messages", [])

        delegation_calls = []
        delegation_results = []

        for message in messages:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    if call.get("name") == "task":
                        delegation_calls.append(call)
                        print("\nDelegation requested:")
                        print(call.get("args", {}))

            if isinstance(message, ToolMessage) and message.name == "task":
                delegation_results.append(message)
                print("\nSpecialist result received:")
                print(str(message.content)[:4000])

        final_answer = ""

        for message in reversed(messages):
            if isinstance(message, AIMessage) and not message.tool_calls:
                if isinstance(message.content, str):
                    final_answer = message.content
                elif message.content:
                    final_answer = str(message.content)
                if final_answer:
                    break

        print("\nMain agent's final answer:")
        print(final_answer or "(No final text answer found.)")

        if not delegation_calls:
            print("\nFAIL: The main agent did not call the task tool.")
            return 1

        if not delegation_results:
            print("\nFAIL: No completed specialist result was found.")
            return 1

        if not final_answer:
            print("\nFAIL: The main agent did not produce a final answer.")
            return 1

        print("\nPASS: The main agent delegated and received a specialist result.")
        return 0

    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
