"""Append-only execution journal for preserving workflow context."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def append_execution_journal(
    *,
    path: str,
    ticker: str,
    account_scope: str | None,
    trade_date: str | None,
    portfolio_manager_text: str,
    execution_report: dict[str, Any],
) -> None:
    """Append one human-readable execution record to a markdown journal."""
    journal_path = Path(path).expanduser()
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    decision = execution_report.get("decision", {}) or {}
    account = execution_report.get("account_snapshot", {}) or {}
    positions = execution_report.get("positions_snapshot", []) or []
    estimated_notional = _estimated_notional(execution_report)

    lines = [
        "",
        "---",
        "",
        (
            f"## {ticker.upper()} | Account: {account_scope or 'default'} | "
            f"Trade date: {trade_date or 'unknown'} | Logged: {_now_iso()}"
        ),
        "",
        "### Portfolio Manager",
        f"- Rating: {decision.get('rating')}",
        f"- Parsed action: {decision.get('action')}",
        f"- Entry price: {_fmt(decision.get('entry_price'))}",
        f"- Stop loss: {_fmt(decision.get('stop_loss'))}",
        f"- Time horizon: {_fmt(decision.get('time_horizon'))}",
        f"- Quick why: {_extract_quick_why(portfolio_manager_text)}",
        "",
        "### Execution Agent",
        f"- Recommended action: {execution_report.get('order_action')}",
        f"- Cash allocation %: {_fmt(execution_report.get('cash_allocation_pct'))}",
        f"- Order submitted: {execution_report.get('order_submitted')}",
        f"- Order type: {execution_report.get('order_type')}",
        f"- Quantity: {_fmt(execution_report.get('quantity'))}",
        f"- Limit price: {_fmt(execution_report.get('limit_price'))}",
        f"- Estimated notional: {_fmt_money(estimated_notional)}",
        f"- Stop loss attached: {execution_report.get('stop_loss_attached')}",
        f"- Alpaca order id: {execution_report.get('alpaca_order_id') or ''}",
        f"- Alpaca status: {execution_report.get('alpaca_status') or ''}",
        f"- Message: {execution_report.get('message') or ''}",
        "",
        "### Account Snapshot",
        f"- Cash (usable): {_fmt_money(account.get('cash'))}",
        f"- Equity: {_fmt_money(account.get('equity') or account.get('portfolio_value'))}",
        "",
        "### Positions Snapshot",
    ]

    if positions:
        for position in positions:
            lines.append(
                "- "
                f"{position.get('symbol')}: qty={_fmt(position.get('qty'))}, "
                f"market_value={_fmt_money(position.get('market_value'))}, "
                f"avg_entry={_fmt_money(position.get('avg_entry_price'))}, "
                f"current={_fmt_money(position.get('current_price'))}"
            )
    else:
        lines.append("- No open positions reported.")

    with journal_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def load_execution_context(
    *,
    path: str,
    ticker: str,
    account_scope: str | None = None,
    max_entries: int = 5,
    max_chars: int = 4000,
) -> str:
    """Return recent same-ticker execution journal entries for later runs."""
    journal_path = Path(path).expanduser()
    if not journal_path.exists():
        return ""

    text = journal_path.read_text(encoding="utf-8")
    blocks = [block.strip() for block in text.split("\n---\n") if block.strip()]
    needle = f"## {ticker.upper()} |"
    matching = [block for block in blocks if needle in block]
    if account_scope:
        scope_marker = f"| Account: {account_scope} |"
        matching = [block for block in matching if scope_marker in block]
    if not matching:
        return ""

    context = "\n\n---\n\n".join(matching[-max_entries:])
    if len(context) <= max_chars:
        return context
    return context[-max_chars:]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _estimated_notional(report: dict[str, Any]) -> Optional[float]:
    quantity = _to_float(report.get("quantity"))
    price = _to_float(report.get("limit_price"))
    if quantity is None or price is None:
        return None
    return quantity * price


def _extract_quick_why(text: str) -> str:
    for label in ("Executive Summary", "Investment Thesis"):
        extracted = _extract_section(text, label)
        if extracted:
            return _squash(extracted, 500)
    return _squash(text, 500)


def _extract_section(text: str, label: str) -> str:
    marker_options = [f"**{label}**:", f"{label}:"]
    start = -1
    marker = ""
    for option in marker_options:
        start = text.find(option)
        if start >= 0:
            marker = option
            break
    if start < 0:
        return ""

    body = text[start + len(marker) :]
    next_section = body.find("\n\n**")
    if next_section >= 0:
        body = body[:next_section]
    return body.strip()


def _squash(text: str, limit: int) -> str:
    squashed = " ".join((text or "").split())
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 3].rstrip() + "..."


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _fmt_money(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    return f"${number:,.2f}"


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
