"""Write and optionally email a read-only Alpaca paper-trading report."""

import argparse
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORT_PATH = Path.home() / ".tradingagents" / "automation" / "daily-paper-report.md"
STATE_PATH = Path.home() / ".tradingagents" / "automation" / "state.db"


def _text(value) -> str:
    return "-" if value is None else str(value)


def _intent_rows(state_path: Path, since: datetime):
    if not state_path.exists():
        return []
    with sqlite3.connect(state_path, timeout=10) as connection:
        return connection.execute(
            """
            SELECT created_at, symbol, side, notional, target_notional, status
            FROM order_intents WHERE created_at >= ?
            ORDER BY created_at DESC, symbol
            """,
            (since.isoformat(),),
        ).fetchall()


def _option_intent_rows(state_path: Path, since: datetime):
    if not state_path.exists():
        return []
    with sqlite3.connect(state_path, timeout=10) as connection:
        return connection.execute(
            """
            SELECT created_at, contract_symbol, underlying, position_intent,
                   quantity, limit_price, status
            FROM option_order_intents WHERE created_at >= ?
            ORDER BY created_at DESC, contract_symbol
            """,
            (since.isoformat(),),
        ).fetchall()


def _value(item, name, default="-"):
    return getattr(item, name, default)


def _is_option_position(position) -> bool:
    return "option" in str(_value(position, "asset_class", "")).casefold()


def _risk_value(risk_summary, name, default="Unavailable"):
    value = risk_summary.get(name)
    return default if value is None else value


def _mapping_summary(values, *, currency: bool = False) -> str:
    if not values:
        return "None"
    return ", ".join(
        f"{symbol} {'$' if currency else ''}{value}"
        for symbol, value in sorted(values.items())
    )


def format_report(
    account,
    positions,
    broker_orders,
    equity_intents,
    option_intents,
    risk_summary,
    now: datetime,
) -> str:
    """Format broker and strategy state without reading or rendering credentials."""
    since = now - timedelta(days=1)
    equity_positions = [position for position in positions if not _is_option_position(position)]
    option_positions = [position for position in positions if _is_option_position(position)]
    lines = [
        "# Alpaca Paper Trading Daily Report",
        "",
        f"Generated: {now.isoformat()}",
        f"Period: {since.isoformat()} to {now.isoformat()}",
        f"Account status: {_value(account, 'status')}",
        f"Cash: ${_value(account, 'cash')}",
        f"Portfolio value: ${_value(account, 'portfolio_value')}",
        "",
        "## Equity positions",
    ]
    if equity_positions:
        lines.extend(
            f"- {_value(position, 'symbol')}: {_value(position, 'side')} "
            f"{_value(position, 'qty')} shares, market value "
            f"${_value(position, 'market_value')}"
            for position in equity_positions
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Option positions"])
    if option_positions:
        lines.extend(
            f"- {_value(position, 'symbol')}: {_value(position, 'side')} "
            f"{_value(position, 'qty')} contract(s), market value "
            f"${_value(position, 'market_value')}"
            for position in option_positions
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Alpaca orders in the last 24 hours"])
    if broker_orders:
        lines.extend(
            f"- {_value(order, 'symbol')}: {_value(order, 'side')} "
            f"{_value(order, 'qty')} units, filled {_value(order, 'filled_qty')}, "
            f"status {_value(order, 'status')}"
            for order in broker_orders
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Equity order intents in the last 24 hours"])
    if equity_intents:
        lines.extend(
            f"- {symbol}: {side} ${notional} toward ${target}, status {status} ({created_at})"
            for created_at, symbol, side, notional, target, status in equity_intents
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Option order intents in the last 24 hours"])
    if option_intents:
        lines.extend(
            f"- {contract}: {position_intent} {quantity} contract(s) on {underlying} "
            f"at limit ${limit_price}, status {status} ({created_at})"
            for (
                created_at,
                contract,
                underlying,
                position_intent,
                quantity,
                limit_price,
                status,
            ) in option_intents
        )
    else:
        lines.append("- None")

    option_delta = _risk_value(risk_summary, "option_delta_exposure")
    if isinstance(option_delta, dict):
        option_delta = _mapping_summary(option_delta, currency=True)
    covered_shares = _risk_value(risk_summary, "covered_shares", {})
    if isinstance(covered_shares, dict):
        covered_shares = _mapping_summary(covered_shares)
    forecast = _risk_value(risk_summary, "combined_forecast_volatility")
    if isinstance(forecast, Decimal):
        forecast = f"{forecast * Decimal('100'):.2f}%"
    gross = _risk_value(risk_summary, "gross_leverage")
    if isinstance(gross, Decimal):
        gross = f"{gross}x"
    suppression = risk_summary.get("suppression_reasons")
    if suppression is None:
        suppression = risk_summary.get("suppressed_reason")
    if isinstance(suppression, (list, tuple)):
        suppression = "; ".join(str(reason) for reason in suppression)
    suppression = suppression or "None"
    lines.extend(
        [
            "",
            "## Coordinated wheel risk",
            f"- Reserved collateral: ${_risk_value(risk_summary, 'wheel_collateral')}",
            f"- Covered shares: {covered_shares}",
            f"- Option delta exposure: {option_delta}",
            f"- Combined forecast volatility: {forecast}",
            f"- Gross leverage: {gross}",
            f"- Suppression reasons: {suppression}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_report(now: datetime) -> str:
    if os.getenv("TRADINGAGENTS_ALPACA_MODE") != "paper":
        raise RuntimeError("daily report only supports Alpaca paper mode")

    client = TradingClient(
        os.environ["ALPACA_API_KEY"],
        os.environ["ALPACA_SECRET_KEY"],
        paper=True,
    )
    account = client.get_account()
    positions = client.get_all_positions()
    since = now - timedelta(days=1)
    broker_orders = client.get_orders(
        filter=GetOrdersRequest(status=QueryOrderStatus.ALL, after=since, limit=500)
    )
    state_path = Path(os.getenv("TRADINGAGENTS_AUTOMATION_STATE_PATH", STATE_PATH))
    equity_intents = _intent_rows(state_path, since)
    option_intents = _option_intent_rows(state_path, since)
    return format_report(
        account,
        positions,
        broker_orders,
        equity_intents,
        option_intents,
        {},
        now,
    )


def send_mail(report_path: Path, recipient: str) -> None:
    script = """
on run argv
    set reportText to read (POSIX file (item 1 of argv)) as «class utf8»
    tell application \"Mail\"
        set outgoingMessage to make new outgoing message with properties {subject:\"Alpaca Paper Trading Daily Report\", content:reportText, visible:false}
        tell outgoingMessage
            make new to recipient at end of to recipients with properties {address:item 2 of argv}
            send
        end tell
    end tell
end run
"""
    subprocess.run(["/usr/bin/osascript", "-e", script, str(report_path), recipient], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_DIR / ".env")
    now = datetime.now(timezone.utc).astimezone()
    report = build_report(now)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    if args.send:
        recipient = os.getenv("TRADINGAGENTS_REPORT_RECIPIENT", "").strip()
        if not recipient:
            raise RuntimeError("TRADINGAGENTS_REPORT_RECIPIENT is required when sending")
        send_mail(REPORT_PATH, recipient)
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
