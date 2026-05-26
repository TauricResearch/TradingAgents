"""MCP server exposing TradingAgents REST API endpoints as tools."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP


def _api_base_url() -> str:
    return (os.getenv("TRADINGAGENTS_API_BASE_URL", "http://localhost:9000") or "http://localhost:9000").rstrip("/")


def _request_json(method: str, path: str, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    url = f"{_api_base_url()}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code} from {url}: {payload}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach {url}: {exc}") from exc


mcp = FastMCP("tradingagents-api")


@mcp.tool()
def health_check() -> str:
    """Check if the TradingAgents API is reachable and healthy."""
    url = f"{_api_base_url()}/healthz"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")


@mcp.tool()
def submit_analysis(ticker: str, date: Optional[str] = None, llm_provider: str = "ollama") -> dict[str, Any]:
    """Submit a new stock analysis request."""
    payload: dict[str, Any] = {"ticker": ticker, "llm_provider": llm_provider}
    if date:
        payload["date"] = date
    return _request_json("POST", "/analyze", payload)


@mcp.tool()
def get_request_status(request_id: str) -> dict[str, Any]:
    """Get current status for an analysis request."""
    safe_id = urllib.parse.quote(request_id, safe="")
    return _request_json("GET", f"/status/{safe_id}")


@mcp.tool()
def get_latest_recommendation(ticker: str, provider: Optional[str] = None) -> dict[str, Any]:
    """Fetch the latest final recommendation for a stock ticker."""
    safe_ticker = urllib.parse.quote(ticker, safe="")
    query = ""
    if provider:
        query = f"?provider={urllib.parse.quote(provider, safe='')}"
    return _request_json("GET", f"/recommendations/latest/{safe_ticker}{query}")


@mcp.tool()
def force_vault_refresh() -> dict[str, Any]:
    """Force immediate key refresh from HashiCorp Vault."""
    return _request_json("POST", "/vault/refresh", {})


@mcp.tool()
def get_runtime_env_value(var_name: str) -> dict[str, Any]:
    """Get a runtime env value currently visible to the API service."""
    safe_name = urllib.parse.quote(var_name, safe="")
    return _request_json("GET", f"/env/{safe_name}")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
