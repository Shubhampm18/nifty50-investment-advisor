"""Trace main-agent delegation without allowing an unbounded run."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from nifty50_investment_advisor.agent import create_investment_agent


def main() -> int:
    agent = create_investment_agent()

    question = (
        "Use the news-research specialist to retrieve three recent "
        "NIFTY 50 or Indian stock-market news results. Return the real "
        "headlines, publishers, timestamps, and URLs. Do not execute trades."
    )

    delegated_to_news = False
    task_result_found = False
    step_count = 0

    print("Starting bounded delegation diagnostic...")
    print("Recursion limit: 8\n")

    try:
        for update in agent.stream(
            {"messages": [HumanMessage(content=question)]},
            config={"recursion_limit": 8},
            stream_mode="updates",
        ):
            step_count += 1

            for node_name, node_update in update.items():
                print(f"\n--- Graph step {step_count}: {node_name} ---")

                if not isinstance(node_update, dict):
                    print("Update type:", type(node_update).__name__)
                    continue

                for message in node_update.get("messages", []):
                    if isinstance(message, AIMessage):
                        for call in message.tool_calls:
                            tool_name = call.get("name")
                            args = call.get("args", {})

                            print(f"Model requested tool: {tool_name}")
                            if tool_name == "task":
                                specialist = args.get("subagent_type")
                                print(f"Requested specialist: {specialist}")

                                if specialist == "news-research":
                                    delegated_to_news = True

                                if specialist == "general-purpose":
                                    print(
                                        "DIAGNOSTIC: The model selected "
                                        "the general-purpose subagent."
                                    )

                        if message.content:
                            content = message.content
                            text_content = str(content)
                            print("Model response length:", len(text_content), "characters")
                            print("Model response:\n", text_content)

                    elif isinstance(message, ToolMessage):
                        print("Tool result:", message.name)
                        content = str(message.content)
                        print("Result length:", len(content), "characters")
                        print("Result beginning:\n", content[:1200])
                        print("\nResult ending:\n", content[-500:])

                        if message.name == "task":
                            task_result_found = True

    except GraphRecursionError:
        print(
            "\nSTOPPED: The graph reached its recursion limit. "
            "The trace above should show which node or tool was repeating."
        )

    print("\n--- Diagnostic summary ---")
    print("Graph updates observed:", step_count)
    print("Delegated to news-research:", delegated_to_news)
    print("Received a task-tool result:", task_result_found)

    if delegated_to_news and task_result_found:
        print("\nPASS: News-specialist delegation completed.")
        return 0

    print(
        "\nINCOMPLETE: Review the trace above before changing the agent "
        "configuration. The run was bounded to prevent another unbounded loop."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
