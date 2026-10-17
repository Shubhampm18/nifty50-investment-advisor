"""Verify that the Deep Agent can make a real LLM call."""

from nifty50_investment_advisor.agent import create_investment_agent


def main() -> int:
    try:
        print("Creating the NIFTY 50 Deep Agent...")
        agent = create_investment_agent()

        question = (
            "Explain in three concise bullet points what the NIFTY 50 "
            "represents. Do not provide current market prices."
        )

        print("Sending a real question to the agent...\n")

        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": question,
                    }
                ]
            }
        )

        messages = result.get("messages", [])

        for message in reversed(messages):
            if getattr(message, "type", None) != "ai":
                continue

            content = getattr(message, "content", "")

            if isinstance(content, str):
                answer = content.strip()
            elif isinstance(content, list):
                answer = "\n".join(
                    item["text"]
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ).strip()
            else:
                answer = ""

            if answer:
                print("PASS: Deep Agent returned a real response.\n")
                print(answer)
                return 0

        print("FAIL: The agent did not return a non-empty text response.")
        return 1

    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
