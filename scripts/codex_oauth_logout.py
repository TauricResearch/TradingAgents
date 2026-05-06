#!/usr/bin/env python3
"""Remove the saved ChatGPT/Codex OAuth token for TradingAgents."""

import argparse

from tradingagents.llm_clients.codex_oauth import CodexOAuthStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the token path without removing it")
    args = parser.parse_args()

    path = CodexOAuthStore().path
    if args.dry_run:
        print(f"Codex OAuth token file path: {path}")
        return

    if path.exists():
        path.unlink()
        print(f"Removed Codex OAuth token file: {path}")
    else:
        print(f"No Codex OAuth token file found at: {path}")


if __name__ == "__main__":
    main()
