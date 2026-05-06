#!/usr/bin/env python3
"""Smoke-test the TradingAgents Codex OAuth provider after login."""

from langchain_core.messages import HumanMessage

from tradingagents.llm_clients.codex_oauth_client import CodexOAuthChatModel


def main() -> None:
    try:
        response = CodexOAuthChatModel(
            model_name="gpt-5.4-mini",
            reasoning_effort="low",
            text_verbosity="low",
            timeout=60,
        ).invoke([HumanMessage(content="Reply with exactly: codex-oauth-ok")])
    except RuntimeError as exc:
        print(f"Codex OAuth smoke failed: {exc}")
        raise SystemExit(1) from exc
    print(response.content.strip())


if __name__ == "__main__":
    main()
