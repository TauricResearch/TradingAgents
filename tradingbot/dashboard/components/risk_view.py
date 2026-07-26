"""Risk monitor view — current exposure vs limits, circuit breaker status."""

import plotly.graph_objects as go
import streamlit as st


def render(broker, db, config):
    st.subheader("Risk Monitor")

    account = broker.get_account()
    positions = broker.get_positions()
    snap = db.get_latest_snapshot()

    portfolio_value = account.equity
    invested = sum(p.market_value for p in positions)
    cash_pct = account.cash / portfolio_value * 100 if portfolio_value else 0
    invested_pct = invested / portfolio_value * 100 if portfolio_value else 0

    max_exposure = config.get("max_total_exposure_pct", 0.80) * 100
    max_single = config.get("max_single_position_pct", 0.10) * 100
    daily_limit = config.get("daily_loss_limit_pct", -0.02) * 100
    min_cash = config.get("min_cash_reserve", 1_000.0)

    # ── Circuit breaker status ─────────────────────────────────────────
    st.markdown("#### Circuit Breaker")
    if snap:
        daily_pnl_pct = snap.daily_pnl_pct * 100
        breached = daily_pnl_pct < daily_limit
        if breached:
            st.error(
                f"CIRCUIT BREAKER ACTIVE — Daily P&L: {daily_pnl_pct:.2f}% "
                f"(limit: {daily_limit:.2f}%). No new buys today."
            )
        else:
            st.success(
                f"Circuit breaker OK — Daily P&L: {daily_pnl_pct:+.2f}% "
                f"(limit: {daily_limit:.2f}%)"
            )
    else:
        st.info("No intraday snapshot yet — circuit breaker inactive.")

    # ── Exposure gauge ─────────────────────────────────────────────────
    st.markdown("#### Total Exposure")
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=invested_pct,
            delta={"reference": max_exposure, "suffix": "%"},
            title={"text": "Portfolio Invested (%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2196F3"},
                "steps": [
                    {"range": [0, max_exposure * 0.7], "color": "#E8F5E9"},
                    {"range": [max_exposure * 0.7, max_exposure], "color": "#FFF9C4"},
                    {"range": [max_exposure, 100], "color": "#FFEBEE"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "thickness": 0.85,
                    "value": max_exposure,
                },
            },
            number={"suffix": "%"},
        ))
        fig.update_layout(height=280)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Cash reserve check
        cash_ok = account.cash >= min_cash
        st.metric(
            "Available Cash",
            f"${account.cash:,.2f}",
            delta=f"Reserve: ${min_cash:,.2f}",
            delta_color="normal" if cash_ok else "inverse",
        )
        st.metric("Invested Value", f"${invested:,.2f}")
        st.metric("Exposure", f"{invested_pct:.1f}% / {max_exposure:.0f}% cap")
        if not cash_ok:
            st.warning(f"Cash ${account.cash:,.2f} is below minimum reserve ${min_cash:,.2f}.")

    # ── Per-position concentration ─────────────────────────────────────
    if positions:
        st.markdown("#### Position Concentration")
        data = {
            "Ticker": [p.ticker for p in positions],
            "Value ($)": [p.market_value for p in positions],
            "% of Portfolio": [p.market_value / portfolio_value * 100 if portfolio_value else 0
                               for p in positions],
            "Cap (%)": [max_single] * len(positions),
        }

        import plotly.express as px
        fig2 = px.bar(
            x=data["Ticker"],
            y=data["% of Portfolio"],
            text=[f"{v:.1f}%" for v in data["% of Portfolio"]],
            labels={"x": "Ticker", "y": "% of Portfolio"},
            title=f"Position Sizes vs {max_single:.0f}% Single-Position Cap",
            color=[
                "Over limit" if v > max_single else "Within limit"
                for v in data["% of Portfolio"]
            ],
            color_discrete_map={"Within limit": "#4CAF50", "Over limit": "#F44336"},
        )
        fig2.add_hline(
            y=max_single,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Cap {max_single:.0f}%",
        )
        fig2.update_traces(textposition="outside")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No open positions — nothing to monitor.")
