"""Verify structured news is retrieved once without calling a real LLM."""

from unittest.mock import patch

from nifty50_investment_advisor import research


def main() -> int:
    fake_news = {
        "ok": True,
        "query": "NIFTY 50 India stock market",
        "source": "Google News RSS",
        "articles_returned": 1,
        "articles": [
            {
                "title": "Example NIFTY 50 headline",
                "publisher": "Example Publisher",
                "published": "2026-10-16T10:00:00Z",
                "summary": "Example summary for testing.",
                "url": "https://example.com/news",
            }
        ],
        "disclaimer": "Test fixture; not real news.",
    }

    fake_agent_result = {
        "messages": [
            type(
                "FakeAIMessage",
                (),
                {
                    "type": "ai",
                    "content": (
                        "Example NIFTY 50 headline was supplied as evidence. "
                        "This is a test response, not investment analysis."
                    ),
                },
            )()
        ]
    }

    with (
        patch.object(
            research,
            "retrieve_news",
            return_value=fake_news,
        ) as retrieve_mock,
        patch.object(
            research,
            "create_investment_agent",
        ) as agent_factory_mock,
    ):
        agent_factory_mock.return_value.invoke.return_value = fake_agent_result

        result = research.run_research(
            "Summarize the latest NIFTY 50 news.",
            include_news=True,
        )

    if retrieve_mock.call_count != 1:
        print(f"FAIL: Expected one structured news retrieval; got {retrieve_mock.call_count}.")
        return 1

    if not result.get("ok"):
        print("FAIL: Research workflow did not return analysis.")
        return 1

    if result.get("news", {}).get("articles_returned") != 1:
        print("FAIL: Structured news was not preserved in the result.")
        return 1

    agent_messages = agent_factory_mock.return_value.invoke.call_args.args[0]["messages"]
    supplied_prompt = agent_messages[0].content

    if "STRUCTURED NEWS EVIDENCE" not in supplied_prompt:
        print("FAIL: Structured news was not passed to the agent.")
        return 1

    if "Example NIFTY 50 headline" not in supplied_prompt:
        print("FAIL: The supplied article was missing from agent context.")
        return 1

    print("PASS: Structured news retrieval was called exactly once.")
    print("PASS: The same structured article was included in agent context.")
    print("NOTE: The LLM and live RSS service were not called by this test.")
    print(
        "NOTE: This does not independently prove the real LLM avoids calling its news specialist."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
