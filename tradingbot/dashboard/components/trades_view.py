"""Trade history component — every executed trade with full agent reasoning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from tradingbot.dashboard.i18n import t
from tradingbot.dashboard.components.signals_view import (
    _extract_signal,
    _normalize_state,
    _render_agent_tabs,
    _render_signal_header,
)


def render(portfolio_manager, config: dict):
    st.subheader(t("tv.subheader"))

    results_dir = Path(
        config.get("results_dir",
                   Path.home() / ".tradingagents" / "logs")
    )

    trades = portfolio_manager.get_trade_history(limit=500)

    if not trades:
        st.info(t("tv.empty"))
        return

    # ── Filter controls ────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    tickers = sorted({t_.ticker for t_ in trades})
    all_label = t("tv.filter.all")
    selected_ticker = col1.selectbox(t("tv.filter.ticker"), [all_label] + tickers)
    side_options = [all_label, "buy", "sell"]
    selected_side = col2.selectbox(
        t("tv.filter.side"),
        side_options,
        format_func=lambda s: all_label if s == all_label
        else (t("tv.filter.buy") if s == "buy" else t("tv.filter.sell")),
    )

    filtered = trades
    if selected_ticker != all_label:
        filtered = [x for x in filtered if x.ticker == selected_ticker]
    if selected_side != all_label:
        filtered = [x for x in filtered if x.side == selected_side]

    # ── Summary table ──────────────────────────────────────────────────
    col_date = t("tv.col.date")
    col_ticker = t("tv.col.ticker")
    col_side = t("tv.col.side")
    col_shares = t("tv.col.shares")
    col_price = t("tv.col.price")
    col_value = t("tv.col.value")
    col_signal = t("tv.col.signal")
    col_logs = t("tv.col.logs")

    buy_label = t("tv.side.buy")
    sell_label = t("tv.side.sell")

    rows = []
    for tr in filtered:
        log_path = _log_path(results_dir, tr.ticker, tr.trade_date)
        rows.append({
            col_date: tr.trade_date,
            col_ticker: tr.ticker,
            col_side: buy_label if tr.side.lower() == "buy" else sell_label,
            col_shares: round(tr.qty, 4),
            col_price: f"${tr.price:.2f}",
            col_value: f"${tr.total_value:,.2f}",
            col_signal: tr.signal,
            col_logs: "✅" if log_path.exists() else "—",
            "_trade": tr,
        })

    df = pd.DataFrame(rows)

    def colour_side(val: str):
        return ("color: green; font-weight: bold" if val == buy_label
                else "color: red; font-weight: bold")

    display_df = df.drop(columns=["_trade"])
    styled = display_df.style.applymap(colour_side, subset=[col_side])
    st.dataframe(styled, use_container_width=True)
    st.caption(t("tv.caption_logs"))

    # ── Per-trade agent reasoning ──────────────────────────────────────
    st.markdown("---")
    st.subheader(t("tv.per_trade.subheader"))
    st.caption(t("tv.per_trade.caption"))

    for row in rows[:50]:
        trade = row["_trade"]
        log_path = _log_path(results_dir, trade.ticker, trade.trade_date)
        has_log = log_path.exists()

        side_icon = "🟢" if trade.is_buy else "🔴"
        log_icon = "📋" if has_log else "📄"
        side_text = buy_label if trade.side.lower() == "buy" else sell_label
        label = t(
            "tv.expander.label",
            log_icon=log_icon,
            date=trade.trade_date,
            side_icon=side_icon,
            side=side_text,
            ticker=trade.ticker,
            signal=trade.signal,
            value=f"{trade.total_value:,.2f}",
        )

        with st.expander(label, expanded=False):
            if has_log:
                _render_full_log(trade.ticker, trade.trade_date, log_path)
            else:
                st.info(
                    t("tv.no_log",
                      path=str(results_dir / trade.ticker / 'TradingAgentsStrategy_logs'))
                )
                st.markdown(t("tv.pm_decision"))
                st.markdown(trade.agent_reasoning or t("tv.no_reasoning"))

    # ── Closed positions P&L table ─────────────────────────────────────
    st.markdown("---")
    st.subheader(t("tv.closed.subheader"))
    closed = portfolio_manager._db.get_closed_positions(limit=200)
    if not closed:
        st.info(t("tv.closed.empty"))
        return

    c_ticker = t("tv.closed.col.ticker")
    c_entry_date = t("tv.closed.col.entry_date")
    c_exit_date = t("tv.closed.col.exit_date")
    c_days = t("tv.closed.col.days")
    c_entry = t("tv.closed.col.entry")
    c_exit = t("tv.closed.col.exit")
    c_shares = t("tv.closed.col.shares")
    c_realised = t("tv.closed.col.realised")
    c_pnl_pct = t("tv.closed.col.pnl_pct")
    c_entry_sig = t("tv.closed.col.entry_sig")
    c_exit_sig = t("tv.closed.col.exit_sig")

    closed_rows = []
    for c in closed:
        pnl = c["realized_pnl"]
        pnl_pct = c["realized_pnl_pct"] * 100
        closed_rows.append({
            c_ticker: c["ticker"],
            c_entry_date: c["entry_date"],
            c_exit_date: c["exit_date"],
            c_days: c["holding_days"],
            c_entry: f"${c['entry_price']:.2f}",
            c_exit: f"${c['exit_price']:.2f}",
            c_shares: round(c["qty"], 4),
            c_realised: f"${pnl:+,.2f}",
            c_pnl_pct: f"{pnl_pct:+.2f}%",
            c_entry_sig: c.get("entry_signal", ""),
            c_exit_sig: c.get("exit_signal", ""),
        })

    cdf = pd.DataFrame(closed_rows)

    def colour_pnl(val: str):
        v = val.replace("$", "").replace(",", "").replace("%", "").replace("+", "")
        try:
            return "color: green" if float(v) >= 0 else "color: red"
        except ValueError:
            return ""

    st.dataframe(
        cdf.style.applymap(colour_pnl, subset=[c_realised, c_pnl_pct]),
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
        st.error(t("tv.log_read_failed", err=str(exc)))
        return

    state = _normalize_state(raw)
    signal = _extract_signal(state.get("final_trade_decision", ""))
    _render_signal_header(ticker, trade_date, signal, state)
    _render_agent_tabs(state)
