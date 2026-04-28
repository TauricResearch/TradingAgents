"""
Signals view — run live analysis from the dashboard and display results.

This page lets you trigger a TradingAgentsGraph.propagate() call
directly from the UI for any ticker on any date, without executing a trade.
Useful for reviewing what the agents are recommending before enabling
fully automated mode.
"""

from datetime import date

import streamlit as st


def render(trading_graph):
    st.subheader("Agent Signal Analysis")
    st.caption(
        "Run the multi-agent analysis pipeline for any ticker and date. "
        "The result shows the full agent reasoning — no trade is executed."
    )

    col1, col2, col3 = st.columns([2, 2, 1])
    ticker = col1.text_input("Ticker", value="AAPL").upper().strip()
    analysis_date = col2.date_input("Analysis Date", value=date.today())
    run_btn = col3.button("Run Analysis", type="primary", use_container_width=True)

    if run_btn and ticker:
        with st.spinner(f"Running multi-agent analysis for {ticker} on {analysis_date}…"):
            try:
                final_state, signal = trading_graph.propagate(
                    ticker, analysis_date.isoformat()
                )
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
                return

        _display_signal_result(ticker, analysis_date.isoformat(), signal, final_state)


def _display_signal_result(ticker: str, analysis_date: str, signal: str, state: dict):
    # ── Signal badge ───────────────────────────────────────────────────
    colour_map = {
        "BUY": "green",
        "OVERWEIGHT": "#8BC34A",
        "HOLD": "gray",
        "UNDERWEIGHT": "orange",
        "SELL": "red",
    }
    badge_colour = colour_map.get(signal.upper(), "gray")
    st.markdown(
        f"### Signal for **{ticker}** on {analysis_date}: "
        f'<span style="color:{badge_colour}; font-weight:bold; font-size:1.3em">{signal}</span>',
        unsafe_allow_html=True,
    )

    # ── Final decision ─────────────────────────────────────────────────
    with st.expander("Portfolio Manager Final Decision", expanded=True):
        st.markdown(state.get("final_trade_decision", "_No decision text_"))

    # ── Analyst reports ────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        with st.expander("Market Analysis"):
            st.markdown(state.get("market_report", "_Not run_"))
        with st.expander("News Analysis"):
            st.markdown(state.get("news_report", "_Not run_"))
    with col2:
        with st.expander("Sentiment Analysis"):
            st.markdown(state.get("sentiment_report", "_Not run_"))
        with st.expander("Fundamentals Analysis"):
            st.markdown(state.get("fundamentals_report", "_Not run_"))

    # ── Investment plan ────────────────────────────────────────────────
    with st.expander("Investment Plan (Research Manager)"):
        st.markdown(state.get("investment_plan", "_Not available_"))

    with st.expander("Trader's Plan"):
        st.markdown(state.get("trader_investment_plan", "_Not available_"))

    # ── Debate summaries ───────────────────────────────────────────────
    invest_state = state.get("investment_debate_state", {})
    risk_state = state.get("risk_debate_state", {})

    with st.expander("Bull vs Bear Debate"):
        c1, c2 = st.columns(2)
        c1.markdown("**Bull Researcher**")
        c1.markdown(invest_state.get("bull_history", "_No history_")[:2000])
        c2.markdown("**Bear Researcher**")
        c2.markdown(invest_state.get("bear_history", "_No history_")[:2000])

    with st.expander("Risk Debate"):
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Aggressive**")
        c1.markdown(risk_state.get("aggressive_history", "_No history_")[:1500])
        c2.markdown("**Neutral**")
        c2.markdown(risk_state.get("neutral_history", "_No history_")[:1500])
        c3.markdown("**Conservative**")
        c3.markdown(risk_state.get("conservative_history", "_No history_")[:1500])
