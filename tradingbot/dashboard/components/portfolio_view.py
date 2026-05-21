"""Portfolio positions component — current holdings table + allocation pie."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tradingbot.dashboard.i18n import t


def render(broker, portfolio_manager):
    st.subheader(t("pv.subheader"))

    positions = broker.get_positions()
    account = broker.get_account()

    # ── KPI cards ──────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t("pv.kpi.value"), f"${account.equity:,.2f}")
    col2.metric(t("pv.kpi.cash"), f"${account.cash:,.2f}")
    invested = sum(p.market_value for p in positions)
    col3.metric(t("pv.kpi.invested"), f"${invested:,.2f}")
    total_unrealised = sum(p.unrealized_pnl for p in positions)
    col4.metric(
        t("pv.kpi.unrealised"),
        f"${total_unrealised:,.2f}",
        delta=f"{total_unrealised / account.equity * 100:.2f}%" if account.equity else None,
    )

    if not positions:
        st.info(t("pv.empty"))
        return

    # ── Positions table ────────────────────────────────────────────────
    col_ticker = t("pv.col.ticker")
    col_shares = t("pv.col.shares")
    col_avg = t("pv.col.avg_entry")
    col_cur = t("pv.col.current")
    col_mv = t("pv.col.market_value")
    col_un = t("pv.col.unrealised")
    col_pct = t("pv.col.pnl_pct")

    rows = []
    for p in positions:
        rows.append({
            col_ticker: p.ticker,
            col_shares: round(p.qty, 4),
            col_avg: f"${p.avg_entry_price:.2f}",
            col_cur: f"${p.current_price:.2f}",
            col_mv: f"${p.market_value:,.2f}",
            col_un: f"${p.unrealized_pnl:+,.2f}",
            col_pct: f"{p.unrealized_pnl_pct * 100:+.2f}%",
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

    styled = df.style.applymap(colour_pnl, subset=[col_un, col_pct])
    st.dataframe(styled, use_container_width=True)

    # ── Allocation pie chart ────────────────────────────────────────────
    st.subheader(t("pv.alloc.subheader"))
    labels = [p.ticker for p in positions] + [t("pv.alloc.cash")]
    values = [p.market_value for p in positions] + [account.cash]
    fig = px.pie(
        names=labels,
        values=values,
        title=t("pv.alloc.title"),
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)
