"""agentRobin brokerage bridge client for TradingAgents (ROBIN-1689).

Resolves portfolio / accounts / optional equity orders via:
  1. HTTP  — TRADINGAGENTS_AGENTROBIN_URL (or AGENTROBIN_TRADINGAGENTS_BRIDGE_URL)
  2. CLI   — `ruby scripts/tradingagents_bridge.rb` under AGENTROBIN_ROOT
             (default /home/marckoby/dev/agentRobin when present)

Live order placement requires allow_live=True and
AGENTROBIN_TRADINGAGENTS_ALLOW_LIVE=1 on the agentRobin side.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from tradingagents.portfolio import PortfolioContext

DEFAULT_AGENTROBIN_ROOTS = (
    os.environ.get("AGENTROBIN_ROOT"),
    "/home/marckoby/dev/agentRobin",
    str(Path.home() / "dev" / "agentRobin"),
)


class AgentRobinBridgeError(RuntimeError):
    """Bridge CLI/HTTP failed or returned unusable data."""


def _agentrobin_root() -> Path | None:
    for candidate in DEFAULT_AGENTROBIN_ROOTS:
        if not candidate:
            continue
        root = Path(candidate)
        cli = root / "scripts" / "tradingagents_bridge.rb"
        if cli.is_file():
            return root
    return None


def _bridge_url() -> str | None:
    for key in (
        "TRADINGAGENTS_AGENTROBIN_URL",
        "AGENTROBIN_TRADINGAGENTS_BRIDGE_URL",
    ):
        value = os.environ.get(key, "").strip().rstrip("/")
        if value:
            return value
    return None


def _bridge_token() -> str:
    return (
        os.environ.get("TRADINGAGENTS_AGENTROBIN_TOKEN")
        or os.environ.get("AGENTROBIN_TRADINGAGENTS_BRIDGE_TOKEN")
        or os.environ.get("AGENTROBIN_PROXY_AUTH_TOKEN")
        or ""
    )


def _http_json(method: str, path: str, body: dict | None = None) -> Any:
    base = _bridge_url()
    if not base:
        raise AgentRobinBridgeError("no TRADINGAGENTS_AGENTROBIN_URL configured")
    url = f"{base}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    token = _bridge_token()
    if token:
        req.add_header("X-TradingAgents-Bridge-Token", token)
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AgentRobinBridgeError(f"HTTP {exc.code} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AgentRobinBridgeError(f"HTTP unreachable {url}: {exc}") from exc


def _cli_json(args: list[str]) -> Any:
    root = _agentrobin_root()
    if root is None:
        raise AgentRobinBridgeError(
            "agentRobin bridge CLI not found; set AGENTROBIN_ROOT or TRADINGAGENTS_AGENTROBIN_URL"
        )
    cmd = ["ruby", str(root / "scripts" / "tradingagents_bridge.rb"), *args]
    env = os.environ.copy()
    env.setdefault("AGENTROBIN_ROOT", str(root))
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgentRobinBridgeError(f"bridge CLI failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise AgentRobinBridgeError(
            f"bridge CLI exit {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AgentRobinBridgeError(f"bridge CLI returned non-JSON: {proc.stdout[:200]}") from exc


def list_accounts(*, sandbox_only: bool = False) -> list[dict[str, Any]]:
    """Paper + live accounts known to agentRobin."""
    if _bridge_url():
        qs = "?sandbox_only=1" if sandbox_only else ""
        payload = _http_json("GET", f"/api/tradingagents/accounts{qs}")
        return list(payload.get("accounts") or [])
    args = ["accounts"]
    if sandbox_only:
        args.append("--sandbox-only")
    return list(_cli_json(args))


def fetch_portfolio(
    account: str,
    *,
    include_options: bool = False,
    include_forex: bool = False,
    refresh: bool = False,
) -> PortfolioContext:
    """Load a TradingAgents PortfolioContext for an agentRobin account id."""
    if not account or not str(account).strip():
        raise AgentRobinBridgeError("account is required")

    if _bridge_url():
        params = {
            "account": account,
            "strict": "1",
        }
        if include_options:
            params["include_options"] = "1"
        if include_forex:
            params["include_forex"] = "1"
        if refresh:
            params["refresh"] = "1"
        qs = urllib.parse.urlencode(params)
        raw = _http_json("GET", f"/api/tradingagents/portfolio?{qs}")
    else:
        args = ["portfolio", "--account", account, "--strict"]
        if include_options:
            args.append("--include-options")
        if include_forex:
            args.append("--include-forex")
        if refresh:
            args.append("--refresh")
        raw = _cli_json(args)

    try:
        return PortfolioContext.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        raise AgentRobinBridgeError(f"portfolio for {account} is not usable: {exc}") from exc


def place_equity_order(
    account: str,
    *,
    symbol: str,
    side: str,
    quantity: float | int | str,
    order_type: str = "market",
    limit_price: float | None = None,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Place an equity order through agentRobin (paper by default)."""
    order = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "type": order_type,
        "account": account,
    }
    if limit_price is not None:
        order["limit_price"] = limit_price
    if allow_live:
        order["allow_live"] = True

    if _bridge_url():
        return _http_json("POST", "/api/tradingagents/orders", order)

    args = [
        "place",
        "--account",
        account,
        "--symbol",
        symbol,
        "--side",
        side,
        "--qty",
        str(quantity),
        "--type",
        order_type,
    ]
    if limit_price is not None:
        args.extend(["--limit-price", str(limit_price)])
    if allow_live:
        args.append("--allow-live")
    return _cli_json(args)


def write_portfolio_file(account: str, path: str | Path, **kwargs: Any) -> Path:
    """Fetch portfolio and write strict JSON for --portfolio consumers."""
    book = fetch_portfolio(account, **kwargs)
    out = Path(path)
    out.write_text(book.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return out
