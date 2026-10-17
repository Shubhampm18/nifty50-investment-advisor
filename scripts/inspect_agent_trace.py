"""Inspect real agent messages and specialist calls."""

from langchain_core.messages import HumanMessage

from nifty50_investment_advisor.agent import create_investment_agent


def main() -> int:
    agent = create_investment_agent()

    question = """
Summarize the following supplied news evidence. Do not search for more news.

STRUCTURED NEWS EVIDENCE:
[
  {
    "title": "Example NIFTY 50 headline supplied for trace inspection",
    "publisher": "Example Publisher",
    "published": "2026-10-16T10:00:00Z",
    "summary": "Example summary.",
    "url": "https://example.com/news"
  }
]

Use only this supplied evidence for the news portion. If market data is
not necessary, do not call the market-research specialist. Do not execute
trades.
"""

    result = agent.invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"recursion_limit": 12},
    )

    print("\n========== AGENT EXECUTION TRACE ==========\n")

    specialist_calls = []
    news_tool_calls = []

    for message in result.get("messages", []):
        message_type = getattr(message, "type", type(message).__name__)
        name = getattr(message, "name", None)
        content = getattr(message, "content", "")

        print(f"Message type: {message_type}")
        if name:
            print(f"Name: {name}")

        for call in getattr(message, "tool_calls", []) or []:
            tool_name = call.get("name", "")
            print(f"Tool call: {tool_name}")

            if tool_name in {"task", "delegate_task"}:
                specialist_calls.append(call)

                arguments = call.get("args", {})
                serialized_args = str(arguments).lower()

                if "news-research" in serialized_args:
                    news_tool_calls.append(call)

        if message_type == "tool":
            print(f"Tool result name: {name}")

        if isinstance(content, str) and content.strip():
            print("Content preview:", content[:500].replace("\n", " "))
        print("-" * 50)

    print("\n========== TRACE SUMMARY ==========")
    print("Specialist/task tool calls:", len(specialist_calls))
    print("News-specialist calls identified:", len(news_tool_calls))

    print(
        "\nNote: this inspects the top-level returned messages. "
        "If the subagent execution is nested or summarized, we may need "
        "to inspect streaming events for a definitive count."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
