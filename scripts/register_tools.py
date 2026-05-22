#!/usr/bin/env python3
"""
Register Hermes tool wrappers with the Hermes tool registry.
Run once via: python /opt/scripts/register_tools.py

Use --dry-run to preview registrations without making API calls.
409 Conflict (already registered) is treated as success — safe to re-run.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


HERMES_API_URL = os.environ.get("HERMES_API_URL", "http://localhost:8080")
REGISTER_ENDPOINT = f"{HERMES_API_URL}/api/tools/register"

TOOLS = [
    {
        "name": "tradingagents_analyze",
        "description": (
            "Run full TradingAgents multi-agent analysis on a ticker. "
            "Returns entry, stop, signal, scenario, confidence."
        ),
        "module": "/opt/hermes_tools/tradingagents_tool.py",
        "function": "tradingagents_analyze",
        "parameters": {
            "ticker": {"type": "string", "required": True},
            "date": {"type": "string", "required": False, "default": "latest"},
        },
    },
    {
        "name": "ib_place_bracket",
        "description": (
            "Place a bracket order on IB Gateway (LMT entry + STP stop). "
            "Returns order_id. Paper trading on port 4002."
        ),
        "module": "/opt/hermes_tools/ib_executor_tool.py",
        "function": "ib_place_bracket",
        "parameters": {
            "ticker": {"type": "string", "required": True},
            "shares": {"type": "integer", "required": True},
            "entry": {"type": "number", "required": True},
            "stop": {"type": "number", "required": True},
        },
    },
    {
        "name": "ib_cancel_order",
        "description": "Cancel an open IB Gateway order by order_id.",
        "module": "/opt/hermes_tools/ib_executor_tool.py",
        "function": "ib_cancel_order",
        "parameters": {
            "order_id": {"type": "integer", "required": True},
        },
    },
    {
        "name": "ib_get_positions",
        "description": (
            "Return all open IB positions as a list of dicts "
            "(ticker, shares, avg_cost, unrealized_pnl)."
        ),
        "module": "/opt/hermes_tools/ib_executor_tool.py",
        "function": "ib_get_positions",
        "parameters": {},
    },
    {
        "name": "ib_get_account_value",
        "description": (
            "Return current IB account equity as a float. "
            "Used for position sizing calculations."
        ),
        "module": "/opt/hermes_tools/ib_executor_tool.py",
        "function": "ib_get_account_value",
        "parameters": {},
    },
    {
        "name": "send_approval_card",
        "description": (
            "Send a trade approval card to the operator via Telegram with "
            "Approve / Reject / More Info inline buttons. "
            "Blocks until the operator responds or the 30-minute timeout expires."
        ),
        "module": "/opt/hermes_tools/telegram_tool.py",
        "function": "send_approval_card",
        "parameters": {
            "trade_card": {"type": "object", "required": True},
        },
    },
    {
        "name": "send_notification",
        "description": (
            "Send an informational or alert message to the operator via Telegram. "
            "level: info | warning | alert."
        ),
        "module": "/opt/hermes_tools/telegram_tool.py",
        "function": "send_notification",
        "parameters": {
            "message": {"type": "string", "required": True},
            "level": {
                "type": "string",
                "required": False,
                "default": "info",
                "enum": ["info", "warning", "alert"],
            },
        },
    },
]


def register_tool(tool: dict, dry_run: bool) -> bool:
    """
    POST tool definition to Hermes registry.
    Returns True on success or already-registered (409).
    Returns False on any other error.
    """
    name = tool["name"]

    if dry_run:
        print(f"  [dry-run] Would register: {name}")
        print(f"    module:   {tool['module']}")
        print(f"    function: {tool['function']}")
        return True

    payload = json.dumps(tool).encode("utf-8")
    req = urllib.request.Request(
        REGISTER_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            print(f"  Already registered: {name}")
            return True
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(
            f"  ERROR registering '{name}': HTTP {exc.code} — {body or exc.reason}",
            file=sys.stderr,
        )
        return False
    except urllib.error.URLError as exc:
        print(
            f"  ERROR registering '{name}': Cannot reach Hermes API at "
            f"{HERMES_API_URL} — {exc.reason}",
            file=sys.stderr,
        )
        return False
    except TimeoutError:
        print(
            f"  ERROR registering '{name}': Request timed out after 10 s",
            file=sys.stderr,
        )
        return False

    print(f"  Registered: {name} (HTTP {status})")
    return True


def main(dry_run: bool) -> None:
    if dry_run:
        print(f"Dry-run mode — no API calls will be made.")
        print(f"Target: {REGISTER_ENDPOINT}\n")
    else:
        print(f"Registering tools with Hermes at {REGISTER_ENDPOINT}\n")

    registered = 0
    failed = 0

    for tool in TOOLS:
        ok = register_tool(tool, dry_run)
        if ok:
            registered += 1
        else:
            failed += 1

    qualifier = "would be " if dry_run else ""
    print(
        f"\nDone. {registered} tools {qualifier}registered"
        + (f", {failed} failed." if failed else ".")
    )

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register Hermes tool wrappers with the Hermes tool registry."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be registered without making API calls.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
