"""Portfolio positions component — current holdings table + allocation pie."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render(broker, portfolio_manager):
    st.subheader("Open Positions")

    positions = broker.get_positions()
    account = broker.get_account()

    # ── KPI cards ──────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio Value", f"${account.equity:,.2f}")
    col2.metric("Cash", f"${account.cash:,.2f}")
    invested = sum(p.market_value for p in positions)
    col3.metric("Invested", f"${invested:,.2f}")
    total_unrealised = sum(p.unrealized_pnl for p in positions)
    col4.metric(
        "Unrealised P&L",
        f"${total_unrealised:,.2f}",
        delta=f"{total_unrealised / account.equity * 100:.2f}%" if account.equity else None,
    )

    if not positions:
        st.info("No open positions.")
        return

    # ── Positions table ────────────────────────────────────────────────
    rows = []
    for p in positions:
        rows.append({
            "Ticker": p.ticker,
            "Shares": round(p.qty, 4),
            "Avg Entry": f"${p.avg_entry_price:.2f}",
            "Current": f"${p.current_price:.2f}",
            "Market Value": f"${p.market_value:,.2f}",
            "Unrealised P&L": f"${p.unrealized_pnl:+,.2f}",
            "P&L %": f"{p.unrealized_pnl_pct * 100:+.2f}%",
        })
    df = pd.DataFrame(rows)

    def colour_pnl(val: str):
        v = val.replace("$", "").replace(",", "").replace("%", "").replace("+", "")
        try:
            num = float(v)
            colour = "color: green" if num >= 0 else "color: red"
        except ValueError:
            colour = ""
        return colour

    styled = df.style.applymap(colour_pnl, subset=["Unrealised P&L", "P&L %"])
    st.dataframe(styled, use_container_width=True)

    # ── Allocation pie chart ────────────────────────────────────────────
    st.subheader("Portfolio Allocation")
    labels = [p.ticker for p in positions] + ["Cash"]
    values = [p.market_value for p in positions] + [account.cash]
    fig = px.pie(
        names=labels,
        values=values,
        title="Allocation by Market Value",
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)
