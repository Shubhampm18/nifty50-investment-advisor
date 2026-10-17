"""Verify that the Deep Agent can call the real market-data tool."""

from nifty50_investment_advisor.agent import create_investment_agent


def main() -> int:
    try:
        print("Creating the NIFTY 50 Deep Agent...")
        agent = create_investment_agent()

        question = (
            "Retrieve the latest available NIFTY 50 daily closing observation "
            "using your market-data tool. Report its observation date, closing "
            "value, previous observation's close, percentage change, and source. "
            "Mention any limitations in the data. Do not make a trade recommendation."
        )

        print("\nSending a real request to the agent...")
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})

        messages = result.get("messages", [])

        tool_messages = [
            message for message in messages if getattr(message, "type", None) == "tool"
        ]

        if not tool_messages:
            print("\nFAIL: No tool result was found in the agent's messages.")
            print("The model may not have called the market-data tool.")
            for message in messages:
                print(
                    getattr(message, "type", "unknown"),
                    str(getattr(message, "content", ""))[:500],
                )
            return 1

        print(f"\nMarket-data tool executions found: {len(tool_messages)}")

        for message in tool_messages:
            content = getattr(message, "content", "")
            print("\nTool result:")
            print(str(content)[:2000])

        for message in reversed(messages):
            if getattr(message, "type", None) != "ai":
                continue

            content = getattr(message, "content", "")

            if isinstance(content, str) and content.strip():
                print("\nAgent's final answer:")
                print(content)
                print("\nPASS: The Deep Agent completed a tool-backed response.")
                return 0

            if isinstance(content, list):
                text_parts = [
                    item["text"]
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ]
                answer = "\n".join(text_parts).strip()

                if answer:
                    print("\nAgent's final answer:")
                    print(answer)
                    print("\nPASS: The Deep Agent completed a tool-backed response.")
                    return 0

        print("\nFAIL: The agent returned no final text answer.")
        return 1

    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
