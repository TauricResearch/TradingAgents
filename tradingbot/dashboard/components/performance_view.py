"""Performance view — equity curve, drawdown chart, and key metrics."""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st


def render(portfolio_manager):
    st.subheader("Performance")

    metrics = portfolio_manager.get_performance_metrics()
    snapshots = portfolio_manager.get_equity_curve()

    # ── KPI cards ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Total Return",
        f"{metrics.total_return_pct * 100:+.2f}%",
        delta=f"${metrics.total_realized_pnl:+,.2f} realised",
    )
    c2.metric("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}")
    c3.metric("Max Drawdown", f"{metrics.max_drawdown * 100:.2f}%")
    c4.metric("Win Rate", f"{metrics.win_rate * 100:.1f}%",
              delta=f"{metrics.winning_trades}W / {metrics.losing_trades}L")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Total Trades", metrics.total_trades)
    c6.metric("Avg Win", f"${metrics.avg_win:,.2f}")
    c7.metric("Avg Loss", f"${metrics.avg_loss:,.2f}")
    pf = metrics.profit_factor
    c8.metric("Profit Factor", f"{pf:.2f}" if pf != float('inf') else "∞")

    if not snapshots:
        st.info("No historical snapshots yet. Snapshots are taken post-market each trading day.")
        return

    df = pd.DataFrame([
        {
            "Date": s.snapshot_date,
            "Equity": s.total_value,
            "Cash": s.cash,
            "Invested": s.invested_value,
            "Daily P&L": s.daily_pnl,
            "Daily P&L %": s.daily_pnl_pct * 100,
        }
        for s in snapshots
    ])
    df["Date"] = pd.to_datetime(df["Date"])

    # ── Equity curve ───────────────────────────────────────────────────
    st.subheader("Equity Curve")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Equity"],
        mode="lines", name="Total Equity",
        line=dict(color="#2196F3", width=2),
        fill="tozeroy", fillcolor="rgba(33,150,243,0.08)",
    ))
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Cash"],
        mode="lines", name="Cash",
        line=dict(color="#4CAF50", width=1, dash="dot"),
    ))
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Value ($)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Drawdown chart ─────────────────────────────────────────────────
    st.subheader("Drawdown")
    peak = df["Equity"].cummax()
    drawdown = (df["Equity"] - peak) / peak * 100
    fig2 = go.Figure(go.Scatter(
        x=df["Date"], y=drawdown,
        fill="tozeroy",
        fillcolor="rgba(244,67,54,0.2)",
        line=dict(color="#F44336"),
        name="Drawdown %",
    ))
    fig2.update_layout(yaxis_title="Drawdown (%)", xaxis_title="Date")
    st.plotly_chart(fig2, use_container_width=True)

    # ── Daily P&L bar chart ────────────────────────────────────────────
    st.subheader("Daily P&L")
    colours = ["#4CAF50" if v >= 0 else "#F44336" for v in df["Daily P&L"]]
    fig3 = go.Figure(go.Bar(
        x=df["Date"], y=df["Daily P&L"],
        marker_color=colours,
        name="Daily P&L ($)",
    ))
    fig3.update_layout(yaxis_title="P&L ($)", xaxis_title="Date")
    st.plotly_chart(fig3, use_container_width=True)
