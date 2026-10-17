"""Test native NVIDIA tool calling with a real LLM request."""

from langchain_core.tools import tool

from nifty50_investment_advisor.model_provider import create_chat_model


@tool
def confirm_tool_call(code: str) -> str:
    """Execute a diagnostic tool to confirm the model can call tools."""
    return f"TOOL_EXECUTED:{code}"


def main() -> int:
    print("Creating the configured NVIDIA model...")
    model = create_chat_model()

    print("Binding a real diagnostic tool...")
    model_with_tools = model.bind_tools([confirm_tool_call])

    print("Sending a real tool-calling request...")
    response = model_with_tools.invoke(
        "You must call confirm_tool_call exactly once with "
        "code='TOOL_CALL_OK'. Do not answer directly."
    )

    calls = response.tool_calls

    if not calls:
        print("FAIL: The model returned no tool calls.")
        print("Response:", response.content)
        return 1

    for call in calls:
        print("Tool requested:", call["name"])
        print("Tool arguments:", call["args"])

        if call["name"] != "confirm_tool_call":
            print("FAIL: The model requested an unexpected tool.")
            return 1

        result = confirm_tool_call.invoke(call["args"])
        print("Actual tool result:", result)

        if result != "TOOL_EXECUTED:TOOL_CALL_OK":
            print("FAIL: The diagnostic tool returned an unexpected result.")
            return 1

    print("\nPASS: The model requested and successfully executed the tool.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
