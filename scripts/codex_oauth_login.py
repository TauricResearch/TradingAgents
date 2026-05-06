#!/usr/bin/env python3
"""Login to ChatGPT/Codex OAuth for TradingAgents."""

import argparse

from tradingagents.llm_clients.codex_oauth import (
    CodexOAuthStore,
    run_device_login_flow,
    run_login_flow,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", action="store_true", help="Use the headless device-code login flow")
    parser.add_argument("--no-browser", action="store_true", help="Print the login URL without opening a browser")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for the OAuth callback")
    args = parser.parse_args()

    store = CodexOAuthStore()
    if args.device:
        tokens = run_device_login_flow(store, timeout_seconds=args.timeout)
    else:
        tokens = run_login_flow(
            store,
            open_browser=not args.no_browser,
            timeout_seconds=args.timeout,
        )
    account = tokens.account_id or "unknown account"
    print(f"Codex OAuth login saved for {account}.")


if __name__ == "__main__":
    main()
