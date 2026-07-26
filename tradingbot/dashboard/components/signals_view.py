"""
Agent Reasoning — inspect every agent's analysis with per-agent tabs.

Two modes:
  Live Analysis  — trigger a fresh TradingAgentsGraph.propagate() from the UI
  Historical Logs — browse past analyses from the JSON logs the bot saves to
                    ~/.tradingagents/logs/{ticker}/TradingAgentsStrategy_logs/

Tab layout (one tab per agent, in pipeline order):
  🎯 Portfolio Mgr → 📊 Market → 📰 News → 💬 Sentiment → 📈 Fundamentals
  → 🐂 Bull → 🐻 Bear → ⚖️ Research Mgr → 💼 Trader
  → ⚡ Aggressive → 😐 Neutral → 🛡️ Conservative
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

import streamlit as st


# ── Public entry point ────────────────────────────────────────────────────────

def render(trading_graph, config: dict):
    st.subheader("Agent Reasoning")
    st.caption(
        "Inspect the full reasoning of every agent — analysts, researchers, "
        "risk debaters, and the portfolio manager. Run a live analysis or load "
        "a past one from the bot's logs."
    )

    mode = st.radio(
        "Mode",
        ["🔴 Live Analysis", "📁 Historical Logs"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("---")

    if mode == "🔴 Live Analysis":
        _render_live(trading_graph)
    else:
        _render_historical(config)


# ── Live analysis mode ─────────────────────────────────────────────────────────

def _render_live(trading_graph):
    col1, col2, col3 = st.columns([2, 2, 1])
    ticker = col1.text_input("Ticker", value="AAPL", key="live_ticker").upper().strip()
    analysis_date = col2.date_input("Analysis Date", value=date.today(), key="live_date")
    run_btn = col3.button("Run Analysis", type="primary", use_container_width=True)

    if not run_btn:
        st.info(
            "Enter a ticker and date, then click **Run Analysis**. "
            "The full multi-agent pipeline will run and results will appear below — "
            "no trade is executed."
        )
        return

    if not ticker:
        st.warning("Please enter a ticker symbol.")
        return

    with st.spinner(f"Running multi-agent analysis for **{ticker}** on {analysis_date}…"):
        try:
            final_state, signal = trading_graph.propagate(ticker, analysis_date.isoformat())
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            return

    state = _normalize_state(final_state)
    _render_signal_header(ticker, analysis_date.isoformat(), signal, state)
    _render_agent_tabs(state)


# ── Historical logs mode ───────────────────────────────────────────────────────

def _render_historical(config: dict):
    results_dir = Path(
        config.get("results_dir",
                   os.path.join(os.path.expanduser("~"), ".tradingagents", "logs"))
    )

    available = _scan_logs(results_dir)

    if not available:
        st.info(
            f"No historical analysis logs found in `{results_dir}`. "
            "Every time `run_bot.py` runs an analysis, a full agent log is saved there automatically. "
            "Those same logs are also linked directly in the **Trade History** page per trade."
        )
        return

    tickers = sorted(available.keys())
    col1, col2, col3 = st.columns([2, 2, 1])
    selected_ticker = col1.selectbox("Ticker", tickers, key="hist_ticker")
    dates = sorted(available[selected_ticker], reverse=True)
    selected_date = col2.selectbox("Analysis Date", dates, key="hist_date")
    load_btn = col3.button("Load", type="primary", use_container_width=True)

    if not load_btn:
        st.info("Select a ticker and date, then click **Load** to view the agents' reasoning.")
        return

    log_path = (
        results_dir
        / selected_ticker
        / "TradingAgentsStrategy_logs"
        / f"full_states_log_{selected_date}.json"
    )
    try:
        with open(log_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        st.error(f"Could not load log file: {exc}")
        return

    state = _normalize_state(raw)
    signal = _extract_signal(state.get("final_trade_decision", ""))
    _render_signal_header(selected_ticker, selected_date, signal, state)
    _render_agent_tabs(state)


def _scan_logs(results_dir: Path) -> dict:
    """Return {ticker: [date_str, ...]} for every available log file."""
    available: dict = {}
    if not results_dir.exists():
        return available
    for ticker_dir in results_dir.iterdir():
        if not ticker_dir.is_dir():
            continue
        log_dir = ticker_dir / "TradingAgentsStrategy_logs"
        if not log_dir.exists():
            continue
        dates = []
        for f in log_dir.glob("full_states_log_*.json"):
            # filename: full_states_log_2024-05-10.json
            date_str = f.stem.replace("full_states_log_", "")
            dates.append(date_str)
        if dates:
            available[ticker_dir.name] = dates
    return available


# ── Signal header ──────────────────────────────────────────────────────────────

_SIGNAL_COLOURS = {
    "BUY":         "#1B5E20",   # dark green
    "OVERWEIGHT":  "#33691E",   # light green
    "HOLD":        "#37474F",   # dark grey-blue
    "UNDERWEIGHT": "#E65100",   # orange
    "SELL":        "#B71C1C",   # dark red
}
_SIGNAL_BG = {
    "BUY":         "#E8F5E9",
    "OVERWEIGHT":  "#F1F8E9",
    "HOLD":        "#ECEFF1",
    "UNDERWEIGHT": "#FFF3E0",
    "SELL":        "#FFEBEE",
}


def _render_signal_header(ticker: str, analysis_date: str, signal: str, state: dict):
    sig = signal.strip().upper()
    fg = _SIGNAL_COLOURS.get(sig, "#37474F")
    bg = _SIGNAL_BG.get(sig, "#ECEFF1")

    col1, col2, col3 = st.columns([1, 1, 1])
    col1.markdown(
        f'<div style="background:{bg};border-left:6px solid {fg};padding:14px 18px;'
        f'border-radius:6px">'
        f'<div style="font-size:0.85em;color:#555">SIGNAL — {ticker} | {analysis_date}</div>'
        f'<div style="font-size:2em;font-weight:700;color:{fg}">{sig}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    invest_state = state.get("investment_debate_state") or {}
    risk_state = state.get("risk_debate_state") or {}
    col2.markdown(
        f'<div style="background:#F3E5F5;border-left:6px solid #7B1FA2;'
        f'padding:14px 18px;border-radius:6px">'
        f'<div style="font-size:0.85em;color:#555">RESEARCH JUDGE</div>'
        f'<div style="font-size:1em;color:#4A148C">'
        f'{(invest_state.get("judge_decision") or "—")[:120]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    col3.markdown(
        f'<div style="background:#E3F2FD;border-left:6px solid #0D47A1;'
        f'padding:14px 18px;border-radius:6px">'
        f'<div style="font-size:0.85em;color:#555">RISK JUDGE</div>'
        f'<div style="font-size:1em;color:#0D47A1">'
        f'{(risk_state.get("judge_decision") or "—")[:120]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")  # spacer


# ── Agent tabs ─────────────────────────────────────────────────────────────────

_TAB_LABELS = [
    "🎯 Portfolio Mgr",
    "📊 Market",
    "📰 News",
    "💬 Sentiment",
    "📈 Fundamentals",
    "🐂 Bull",
    "🐻 Bear",
    "⚖️ Research Mgr",
    "💼 Trader",
    "⚡ Aggressive",
    "😐 Neutral",
    "🛡️ Conservative",
]


def _render_agent_tabs(state: dict):
    invest = state.get("investment_debate_state") or {}
    risk = state.get("risk_debate_state") or {}

    tabs = st.tabs(_TAB_LABELS)

    # ── 0. Portfolio Manager ──────────────────────────────────────────
    with tabs[0]:
        _section_header(
            "Portfolio Manager",
            "Final decision-maker. Synthesises all agent inputs and risk debates "
            "into the definitive trading rating.",
        )
        decision = state.get("final_trade_decision") or ""
        sig = _extract_signal(decision)
        if sig != "UNKNOWN":
            fg = _SIGNAL_COLOURS.get(sig, "#37474F")
            bg = _SIGNAL_BG.get(sig, "#ECEFF1")
            st.markdown(
                f'<div style="background:{bg};border:2px solid {fg};padding:10px 16px;'
                f'border-radius:6px;margin-bottom:12px">'
                f'<b style="color:{fg};font-size:1.4em">{sig}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )
        _content_block("Final Trade Decision", decision)
        _content_block("Risk Debate Judge Decision", risk.get("judge_decision") or "")
        _content_block("Full Risk Debate History", risk.get("history") or "")

    # ── 1. Market Analyst ─────────────────────────────────────────────
    with tabs[1]:
        _section_header(
            "Market Analyst",
            "Analyses technical indicators (MACD, RSI, Bollinger Bands, moving averages, "
            "ATR, VWMA) to identify trading patterns and forecast price movements.",
        )
        _content_block("Market Analysis Report", state.get("market_report") or "")

    # ── 2. News Analyst ───────────────────────────────────────────────
    with tabs[2]:
        _section_header(
            "News Analyst",
            "Monitors global news, earnings events, and macroeconomic indicators, "
            "interpreting how current events may affect the stock.",
        )
        _content_block("News Analysis Report", state.get("news_report") or "")

    # ── 3. Sentiment Analyst ──────────────────────────────────────────
    with tabs[3]:
        _section_header(
            "Sentiment Analyst",
            "Assesses public sentiment and social media signals to gauge "
            "short-term market mood and retail investor positioning.",
        )
        _content_block("Sentiment Analysis Report", state.get("sentiment_report") or "")

    # ── 4. Fundamentals Analyst ───────────────────────────────────────
    with tabs[4]:
        _section_header(
            "Fundamentals Analyst",
            "Evaluates company financials: balance sheet, income statement, "
            "cash flow, and key ratios to assess intrinsic value.",
        )
        _content_block("Fundamentals Analysis Report", state.get("fundamentals_report") or "")

    # ── 5. Bull Researcher ────────────────────────────────────────────
    with tabs[5]:
        _section_header(
            "Bull Researcher",
            "Builds the strongest possible evidence-based case for buying. "
            "Argues growth catalysts, undervaluation, and upside potential.",
        )
        _content_block("Bull Argument", invest.get("bull_history") or "")

    # ── 6. Bear Researcher ────────────────────────────────────────────
    with tabs[6]:
        _section_header(
            "Bear Researcher",
            "Counters with risks, downside scenarios, and reasons for caution or selling. "
            "Stress-tests the bull case with worst-case analysis.",
        )
        _content_block("Bear Argument", invest.get("bear_history") or "")

    # ── 7. Research Manager ───────────────────────────────────────────
    with tabs[7]:
        _section_header(
            "Research Manager",
            "Judges the bull vs bear debate and synthesises the full analyst team's "
            "reports into a final investment plan for the Trader.",
        )
        _content_block("Investment Plan", state.get("investment_plan") or "")
        _content_block("Judge Decision (Invest Debate)", invest.get("judge_decision") or "")
        _content_block("Full Investment Debate History", invest.get("history") or "")

    # ── 8. Trader ─────────────────────────────────────────────────────
    with tabs[8]:
        _section_header(
            "Trader",
            "Takes the Research Manager's investment plan and produces a specific "
            "BUY / HOLD / SELL proposal with entry strategy, sizing, and time horizon.",
        )
        _content_block(
            "Trader's Investment Plan",
            state.get("trader_investment_plan") or "",
        )

    # ── 9. Aggressive Risk Debater ────────────────────────────────────
    with tabs[9]:
        _section_header(
            "Aggressive Risk Debater",
            "Advocates for taking the trade at full size, emphasising upside potential "
            "and arguing against excessive caution.",
        )
        _content_block("Aggressive Risk Argument", risk.get("aggressive_history") or "")

    # ── 10. Neutral Risk Debater ──────────────────────────────────────
    with tabs[10]:
        _section_header(
            "Neutral Risk Debater",
            "Provides a balanced assessment, weighing both the aggressive and conservative "
            "positions to find an optimal risk-adjusted approach.",
        )
        _content_block("Neutral Risk Argument", risk.get("neutral_history") or "")

    # ── 11. Conservative Risk Debater ─────────────────────────────────
    with tabs[11]:
        _section_header(
            "Conservative Risk Debater",
            "Emphasises downside protection, position sizing discipline, and scenarios "
            "where doing nothing or reducing size is the right call.",
        )
        _content_block("Conservative Risk Argument", risk.get("conservative_history") or "")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _section_header(title: str, description: str):
    st.markdown(f"#### {title}")
    st.caption(description)
    st.markdown("---")


def _content_block(label: str, text: str):
    """Render a labelled text block; show a placeholder if empty."""
    if not text or text.strip() == "":
        st.markdown(f"**{label}**")
        st.info("No output recorded for this agent. It may not have been included in this run.")
        return

    # Show a character count badge for long reports
    char_count = len(text)
    badge = f" `{char_count:,} chars`" if char_count > 500 else ""
    st.markdown(f"**{label}**{badge}")
    st.markdown(text)
    st.markdown("")


def _normalize_state(state: dict) -> dict:
    """
    Normalise key differences between the live-run state and the JSON log format.

    JSON logs save the trader output under 'trader_investment_decision';
    the live LangGraph state uses 'trader_investment_plan'.
    """
    normalized = dict(state)
    if (
        "trader_investment_decision" in normalized
        and "trader_investment_plan" not in normalized
    ):
        normalized["trader_investment_plan"] = normalized["trader_investment_decision"]
    return normalized


def _extract_signal(text: str) -> str:
    """
    Best-effort extraction of the 5-tier signal word from a decision text.
    Looks for the signal word standing alone (word boundary) to avoid false
    matches like "OVERWEIGHT" inside "NOT OVERWEIGHT".
    """
    if not text:
        return "UNKNOWN"
    # Ordered by specificity — check longer tokens first
    for signal in ("OVERWEIGHT", "UNDERWEIGHT", "BUY", "SELL", "HOLD"):
        if re.search(rf"\b{signal}\b", text.upper()):
            return signal
    return "UNKNOWN"
