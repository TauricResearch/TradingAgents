"""Performance view — equity curve, drawdown chart, and key metrics."""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from tradingbot.dashboard.i18n import t


def render(portfolio_manager):
    st.subheader(t("perf.subheader"))

    metrics = portfolio_manager.get_performance_metrics()
    snapshots = portfolio_manager.get_equity_curve()

    # ── KPI cards ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        t("perf.kpi.total_return"),
        f"{metrics.total_return_pct * 100:+.2f}%",
        delta=t("perf.kpi.realised_delta", pnl=f"{metrics.total_realized_pnl:+,.2f}"),
    )
    c2.metric(t("perf.kpi.sharpe"), f"{metrics.sharpe_ratio:.2f}")
    c3.metric(t("perf.kpi.max_dd"), f"{metrics.max_drawdown * 100:.2f}%")
    c4.metric(
        t("perf.kpi.win_rate"),
        f"{metrics.win_rate * 100:.1f}%",
        delta=t("perf.kpi.wl_delta", w=metrics.winning_trades, l=metrics.losing_trades),
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(t("perf.kpi.total_trades"), metrics.total_trades)
    c6.metric(t("perf.kpi.avg_win"), f"${metrics.avg_win:,.2f}")
    c7.metric(t("perf.kpi.avg_loss"), f"${metrics.avg_loss:,.2f}")
    pf = metrics.profit_factor
    c8.metric(t("perf.kpi.profit_factor"), f"{pf:.2f}" if pf != float('inf') else "∞")

    if not snapshots:
        st.info(t("perf.empty"))
        return

    col_date = t("perf.axis.date")
    col_equity = t("perf.equity.total")
    col_cash = t("perf.equity.cash")
    col_daily_pnl = t("perf.daily.name")

    df = pd.DataFrame([
        {
            col_date: s.snapshot_date,
            col_equity: s.total_value,
            col_cash: s.cash,
            "Invested": s.invested_value,
            col_daily_pnl: s.daily_pnl,
            "Daily P&L %": s.daily_pnl_pct * 100,
        }
        for s in snapshots
    ])
    df[col_date] = pd.to_datetime(df[col_date])

    # ── Equity curve ───────────────────────────────────────────────────
    st.subheader(t("perf.equity.subheader"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[col_date], y=df[col_equity],
        mode="lines", name=col_equity,
        line=dict(color="#2196F3", width=2),
        fill="tozeroy", fillcolor="rgba(33,150,243,0.08)",
    ))
    fig.add_trace(go.Scatter(
        x=df[col_date], y=df[col_cash],
        mode="lines", name=col_cash,
        line=dict(color="#4CAF50", width=1, dash="dot"),
    ))
    fig.update_layout(
        xaxis_title=t("perf.axis.date"),
        yaxis_title=t("perf.axis.value"),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Drawdown chart ─────────────────────────────────────────────────
    st.subheader(t("perf.dd.subheader"))
    peak = df[col_equity].cummax()
    drawdown = (df[col_equity] - peak) / peak * 100
    fig2 = go.Figure(go.Scatter(
        x=df[col_date], y=drawdown,
        fill="tozeroy",
        fillcolor="rgba(244,67,54,0.2)",
        line=dict(color="#F44336"),
        name=t("perf.dd.name"),
    ))
    fig2.update_layout(yaxis_title=t("perf.dd.axis"), xaxis_title=t("perf.axis.date"))
    st.plotly_chart(fig2, use_container_width=True)

    # ── Daily P&L bar chart ────────────────────────────────────────────
    st.subheader(t("perf.daily.subheader"))
    colours = ["#4CAF50" if v >= 0 else "#F44336" for v in df[col_daily_pnl]]
    fig3 = go.Figure(go.Bar(
        x=df[col_date], y=df[col_daily_pnl],
        marker_color=colours,
        name=t("perf.daily.name"),
    ))
    fig3.update_layout(yaxis_title=t("perf.daily.axis"), xaxis_title=t("perf.axis.date"))
    st.plotly_chart(fig3, use_container_width=True)
