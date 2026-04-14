"""Smoke test for the claude_agent provider (Shape A).

Exercises the three call patterns used in TradingAgents:
  1. Plain string prompt (trader, researchers)
  2. List of role/content dicts (trader)
  3. List of LangChain messages via ChatPromptTemplate (simulated manager path)

Prints the response text and timing for each. Any exception = failure.
Requires the user to be logged into Claude Code.
"""

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.llm_clients.factory import create_llm_client


def run(label, invocation):
    start = time.monotonic()
    result = invocation()
    elapsed = time.monotonic() - start
    content = result.content if hasattr(result, "content") else result
    preview = (content[:300] + "…") if len(content) > 300 else content
    print(f"\n--- {label} ({elapsed:.1f}s) ---")
    print(preview)


def main():
    client = create_llm_client(
        provider="claude_agent",
        model="sonnet",
    )
    llm = client.get_llm()

    run("1. string prompt",
        lambda: llm.invoke("In one sentence, what is a P/E ratio?"))

    run("2. role/content dicts",
        lambda: llm.invoke([
            {"role": "system", "content": "You are a concise financial analyst."},
            {"role": "user", "content": "In one sentence, define moving average."},
        ]))

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a concise financial analyst."),
        MessagesPlaceholder(variable_name="messages"),
    ])
    run("3. ChatPromptTemplate pipe",
        lambda: (prompt | llm).invoke({
            "messages": [HumanMessage(content="In one sentence, define RSI.")]
        }))

    try:
        llm.bind_tools([])
    except NotImplementedError as e:
        print(f"\n--- 4. bind_tools guard ---\nRaised as expected: {e}")
    else:
        raise AssertionError("bind_tools should have raised NotImplementedError")

    print("\nSmoke test OK.")


if __name__ == "__main__":
    main()
