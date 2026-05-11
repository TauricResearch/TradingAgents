"""Alpha Vantage ETF profile and holdings.

Alpha Vantage's ``ETF_PROFILE`` endpoint returns the ETF's net assets,
expense ratio, dividend yield, inception date, leveraged flag, sector
allocation, and top holdings in a single JSON payload — convenient to
split into the same two-function shape we expose for yfinance.
"""

from __future__ import annotations

import json
from datetime import datetime

from .alpha_vantage_common import _make_api_request


def _fetch_etf_profile_raw(ticker: str) -> dict:
    """Fetch and parse the raw ``ETF_PROFILE`` payload.

    ``_make_api_request`` returns the response body verbatim — JSON for
    this endpoint. Returns an empty dict when Alpha Vantage responds with
    a non-JSON body (e.g. rate-limit notes that slipped past detection).
    """
    raw = _make_api_request("ETF_PROFILE", {"symbol": ticker})
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def get_etf_profile(ticker: str) -> str:
    """Profile snapshot for an ETF via Alpha Vantage ``ETF_PROFILE``.

    Renders the core fields (AUM / expense ratio / dividend yield / sectors)
    in the same markdown shape as the yfinance variant so the downstream
    analyst prompt doesn't have to branch on vendor.
    """
    data = _fetch_etf_profile_raw(ticker)
    if not data:
        return f"No ETF profile available for {ticker} (Alpha Vantage returned no data)"

    fields = [
        ("Name", data.get("name")),
        ("Net Assets (AUM)", data.get("net_assets")),
        ("Net Expense Ratio", data.get("net_expense_ratio")),
        ("Portfolio Turnover", data.get("portfolio_turnover")),
        ("Dividend Yield", data.get("dividend_yield")),
        ("Inception Date", data.get("inception_date")),
        ("Leveraged", data.get("leveraged")),
        ("Asset Class", data.get("asset_class")),
    ]

    lines = [
        f"# ETF Profile for {ticker.upper()}",
        "# Source: Alpha Vantage ETF_PROFILE",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for label, value in fields:
        if value not in (None, "", "None"):
            lines.append(f"- **{label}**: {value}")

    sectors = data.get("sectors") or []
    if sectors:
        lines.append("")
        lines.append("## Sector Weightings")
        for entry in sectors:
            sector = entry.get("sector")
            weight = entry.get("weight")
            if sector and weight is not None:
                lines.append(f"- {sector}: {weight}")

    return "\n".join(lines)


def get_etf_holdings(ticker: str, top_n: int = 10) -> str:
    """Top-N ETF holdings via Alpha Vantage ``ETF_PROFILE``.

    Alpha Vantage bundles the holdings inside the same payload as the
    profile. We slice to ``top_n`` and render as CSV — matching the
    yfinance variant's output shape so analyst prompts stay vendor-agnostic.
    """
    data = _fetch_etf_profile_raw(ticker)
    holdings = data.get("holdings") or [] if data else []
    if not holdings:
        return f"No holdings disclosed for {ticker.upper()}"

    rows = holdings[:top_n]
    header = (
        f"# ETF Holdings for {ticker.upper()}\n"
        "# Source: Alpha Vantage ETF_PROFILE.holdings\n"
        f"# Top {len(rows)} positions\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "\nsymbol,description,weight\n"
    )
    body = "\n".join(
        f"{row.get('symbol', '')},{row.get('description', '')},{row.get('weight', '')}"
        for row in rows
    )
    return header + body + "\n"


def get_top_holding_tickers(
    etf_ticker: str, top_n: int = 3
) -> list[tuple[str, str, float]]:
    """Structured top-N holdings: ``[(ticker, name, weight_pct), ...]``.

    Alpha Vantage emits weight as a decimal string (``"0.092"`` = 9.2%).
    Returns ``[]`` when the endpoint returns no payload so the
    orchestrator can degrade gracefully.
    """
    data = _fetch_etf_profile_raw(etf_ticker)
    holdings = (data or {}).get("holdings") or []
    if not holdings:
        return []

    out: list[tuple[str, str, float]] = []
    for row in holdings[:top_n]:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        name = str(row.get("description") or symbol)
        try:
            weight_pct = float(row.get("weight") or 0.0) * 100
        except (TypeError, ValueError):
            weight_pct = 0.0
        out.append((symbol, name, weight_pct))
    return out
