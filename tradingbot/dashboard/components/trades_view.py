"""Trade history component — every executed trade with agent reasoning."""

import pandas as pd
import streamlit as st


def render(portfolio_manager):
    st.subheader("Trade History")

    trades = portfolio_manager.get_trade_history(limit=500)

    if not trades:
        st.info("No trades recorded yet.")
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
        rows.append({
            "Date": t.trade_date,
            "Ticker": t.ticker,
            "Side": t.side.upper(),
            "Shares": round(t.qty, 4),
            "Price": f"${t.price:.2f}",
            "Value": f"${t.total_value:,.2f}",
            "Signal": t.signal,
            "Time": t.timestamp.strftime("%H:%M:%S"),
            "_reasoning": t.agent_reasoning,
        })
    df = pd.DataFrame(rows)

    def colour_side(val):
        return "color: green; font-weight: bold" if val == "BUY" else "color: red; font-weight: bold"

    display_df = df.drop(columns=["_reasoning"])
    styled = display_df.style.applymap(colour_side, subset=["Side"])
    st.dataframe(styled, use_container_width=True)

    # ── Agent reasoning expander ───────────────────────────────────────
    st.subheader("Agent Reasoning")
    st.caption("Select a trade row above, then expand the entry below to see the full agent analysis.")
    for i, row in enumerate(rows[:50]):  # limit for performance
        label = f"{row['Date']} | {row['Side']} {row['Ticker']} | Signal: {row['Signal']}"
        with st.expander(label, expanded=False):
            st.markdown(row["_reasoning"])

    # ── Closed positions P&L table ─────────────────────────────────────
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
            colour = "color: green" if float(v) >= 0 else "color: red"
        except ValueError:
            colour = ""
        return colour

    styled_closed = cdf.style.applymap(colour_pnl, subset=["Realised P&L", "P&L %"])
    st.dataframe(styled_closed, use_container_width=True)
