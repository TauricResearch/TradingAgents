"""Run Binance crypto train mode with Gemini key rotation.

Example:
    python3 scripts/crypto_train.py --once BTC/USDT ETH/USDT
    python3 scripts/crypto_train.py --once --profile full BTC/USDT
    python3 scripts/crypto_train.py --forever --interval 15 BTC/USDT
"""

from __future__ import annotations

# Load .env BEFORE importing any tradingagents modules so that os.getenv()
# calls evaluated at import time (default_config.py) pick up the correct values.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
import logging

from tradingagents.crypto import CryptoTrainRunner
from tradingagents.llm_clients.google_key_rotator import GoogleApiKeyRotator, parse_google_api_keys


def _print_quota_summary(config: dict) -> None:
    """In tóm tắt lượng quota đã dùng theo từng key."""
    keys = parse_google_api_keys(config.get("google_api_keys", ""))
    if not keys:
        return
    state_path = config.get("google_key_rotation_state_path")
    if not state_path:
        return
    try:
        rotator = GoogleApiKeyRotator(keys, state_path=state_path)
        usage = rotator.state.get("usage", {})
        total = sum(v.get("requests", 0) for v in usage.values())
        print("\n--- Quota usage today (cumulative) ---")
        for kid, v in usage.items():
            print(f"  Key ...{kid[-6:]}: {v.get('requests', 0)} requests "
                  f"(quick={v.get('roles', {}).get('quick', 0)}, deep={v.get('roles', {}).get('deep', 0)})")
        print(f"  TOTAL: {total} requests across {len(usage)} key(s)")
        print("  Free-tier limit: ~20/day/project for flash-lite, ~10/day/project for flash")
        print("--------------------------------------")
    except Exception:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TradingAgents crypto train mode")
    parser.add_argument("symbols", nargs="*", default=["BTC/USDT", "ETH/USDT"], help="Binance symbols, e.g. BTC/USDT")
    parser.add_argument("--once", action="store_true", help="Run one pass and exit")
    parser.add_argument("--forever", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=15, help="Trigger interval in minutes")
    parser.add_argument(
        "--profile",
        choices=["compact", "full"],
        default="compact",
        help="compact uses ~1 LLM call per symbol; full runs the multi-agent graph and needs much more quota",
    )
    parser.add_argument("--debug", action="store_true", help="Print LangGraph debug messages")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    runner = CryptoTrainRunner(args.symbols, debug=args.debug, profile=args.profile)
    if args.forever:
        runner.run_forever(interval_minutes=args.interval)
        return
    results = runner.run_once()
    for symbol, decision in results.items():
        print("\n" + "=" * 80)
        print(f"{symbol} decision")
        print("=" * 80)
        print(decision)
    _print_quota_summary(runner.config)


if __name__ == "__main__":
    main()
