"""Trade history component — every executed trade with full agent reasoning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from tradingbot.dashboard.components.signals_view import (
    _extract_signal,
    _normalize_state,
    _render_agent_tabs,
    _render_signal_header,
)


def render(portfolio_manager, config: dict):
    st.subheader("Trade History")

    results_dir = Path(
        config.get("results_dir",
                   Path.home() / ".tradingagents" / "logs")
    )

    trades = portfolio_manager.get_trade_history(limit=500)

    if not trades:
        st.info(
            "No trades recorded yet. Run `python run_bot.py --once` to execute your first trade."
        )
        return

    # ── Filter controls ────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    tickers = sorted({t.ticker for t in trades})
    selected_ticker = col1.selectbox("Filter by ticker", ["All"] + tickers)
    selected_side = col2.selectbox("Filter by side", ["All", "buy", "sell"])

    filtered = trades
    if selected_ticker != "All":
        filtered = [t for t in filtered if t.ticker == selected_ticker]
    if selected_side != "All":
        filtered = [t for t in filtered if t.side == selected_side]

    # ── Summary table ──────────────────────────────────────────────────
    rows = []
    for t in filtered:
        log_path = _log_path(results_dir, t.ticker, t.trade_date)
        rows.append({
            "Date": t.trade_date,
            "Ticker": t.ticker,
            "Side": t.side.upper(),
            "Shares": round(t.qty, 4),
            "Price": f"${t.price:.2f}",
            "Value": f"${t.total_value:,.2f}",
            "Signal": t.signal,
            "Logs": "✅" if log_path.exists() else "—",
            "_trade": t,
        })

    df = pd.DataFrame(rows)

    def colour_side(val: str):
        return "color: green; font-weight: bold" if val == "BUY" else "color: red; font-weight: bold"

    display_df = df.drop(columns=["_trade"])
    styled = display_df.style.applymap(colour_side, subset=["Side"])
    st.dataframe(styled, use_container_width=True)
    st.caption(
        "**Logs ✅** means the full 12-agent reasoning log exists for that trade "
        "and is viewable below. Logs are saved automatically every time `run_bot.py` runs."
    )

    # ── Per-trade agent reasoning ──────────────────────────────────────
    st.markdown("---")
    st.subheader("Agent Reasoning per Trade")
    st.caption(
        "Expand any trade to see the full reasoning of all 12 agents — "
        "analysts, researchers, risk debaters, and the portfolio manager — "
        "exactly as they ran when the bot made that decision."
    )

    for row in rows[:50]:  # cap for render performance
        trade = row["_trade"]
        log_path = _log_path(results_dir, trade.ticker, trade.trade_date)
        has_log = log_path.exists()

        side_icon = "🟢" if trade.is_buy else "🔴"
        log_icon = "📋" if has_log else "📄"
        label = (
            f"{log_icon} {trade.trade_date}  |  "
            f"{side_icon} {trade.side.upper()} {trade.ticker}  |  "
            f"Signal: {trade.signal}  |  "
            f"${trade.total_value:,.2f}"
        )

        with st.expander(label, expanded=False):
            if has_log:
                _render_full_log(trade.ticker, trade.trade_date, log_path)
            else:
                # Fallback: show only the stored final decision
                st.info(
                    "Full agent log not found. Showing the stored portfolio manager "
                    "decision only. Logs are written to "
                    f"`{results_dir / trade.ticker / 'TradingAgentsStrategy_logs'}`"
                    " when the bot runs."
                )
                st.markdown("**Portfolio Manager Decision**")
                st.markdown(trade.agent_reasoning or "_No reasoning stored._")

    # ── Closed positions P&L table ─────────────────────────────────────
    st.markdown("---")
    st.subheader("Closed Positions")
    closed = portfolio_manager._db.get_closed_positions(limit=200)
    if not closed:
        st.info("No closed positions yet.")
        return

    closed_rows = []
    for c in closed:
        pnl = c["realized_pnl"]
        pnl_pct = c["realized_pnl_pct"] * 100
        closed_rows.append({
            "Ticker": c["ticker"],
            "Entry Date": c["entry_date"],
            "Exit Date": c["exit_date"],
            "Days Held": c["holding_days"],
            "Entry $": f"${c['entry_price']:.2f}",
            "Exit $": f"${c['exit_price']:.2f}",
            "Shares": round(c["qty"], 4),
            "Realised P&L": f"${pnl:+,.2f}",
            "P&L %": f"{pnl_pct:+.2f}%",
            "Entry Signal": c.get("entry_signal", ""),
            "Exit Signal": c.get("exit_signal", ""),
        })

    cdf = pd.DataFrame(closed_rows)

    def colour_pnl(val: str):
        v = val.replace("$", "").replace(",", "").replace("%", "").replace("+", "")
        try:
            return "color: green" if float(v) >= 0 else "color: red"
        except ValueError:
            return ""

    st.dataframe(
        cdf.style.applymap(colour_pnl, subset=["Realised P&L", "P&L %"]),
        use_container_width=True,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _log_path(results_dir: Path, ticker: str, trade_date: str) -> Path:
    """Construct the deterministic path to a trade's full agent JSON log."""
    return (
        results_dir
        / ticker.upper()
        / "TradingAgentsStrategy_logs"
        / f"full_states_log_{trade_date}.json"
    )


def _render_full_log(ticker: str, trade_date: str, log_path: Path) -> None:
    """Load a JSON log and render the 3-card header + 12-agent tabs."""
    try:
        with open(log_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        st.error(f"Could not read log file: {exc}")
        return

    state = _normalize_state(raw)
    signal = _extract_signal(state.get("final_trade_decision", ""))
    _render_signal_header(ticker, trade_date, signal, state)
    _render_agent_tabs(state)
