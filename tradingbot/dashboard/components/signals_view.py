"""
Agent Reasoning — inspect every agent's analysis with per-agent tabs.

Two modes:
  Live Analysis  — trigger a fresh TradingAgentsGraph.propagate() from the UI
  Historical Logs — browse past analyses from the JSON logs the bot saves to
                    ~/.tradingagents/logs/{ticker}/TradingAgentsStrategy_logs/
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

import streamlit as st

from tradingbot.dashboard.i18n import t


# ── Public entry point ────────────────────────────────────────────────────────

def render(trading_graph, config: dict):
    st.subheader(t("sig.subheader"))
    st.caption(t("sig.caption"))

    mode_live = t("sig.mode.live")
    mode_hist = t("sig.mode.historical")
    mode = st.radio(
        t("sig.mode.label"),
        [mode_live, mode_hist],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("---")

    if mode == mode_live:
        _render_live(trading_graph)
    else:
        _render_historical(config)


# ── Live analysis mode ─────────────────────────────────────────────────────────

def _render_live(trading_graph):
    col1, col2, col3 = st.columns([2, 2, 1])
    ticker = col1.text_input(t("sig.live.ticker"), value="AAPL", key="live_ticker").upper().strip()
    analysis_date = col2.date_input(t("sig.live.date"), value=date.today(), key="live_date")
    run_btn = col3.button(t("sig.live.run"), type="primary", use_container_width=True)

    if not run_btn:
        st.info(t("sig.live.hint"))
        return

    if not ticker:
        st.warning(t("sig.live.no_ticker"))
        return

    with st.spinner(t("sig.live.spinner", ticker=ticker, date=analysis_date)):
        try:
            final_state, signal = trading_graph.propagate(ticker, analysis_date.isoformat())
        except Exception as exc:
            st.error(t("sig.live.failed", err=str(exc)))
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
        st.info(t("sig.hist.empty", dir=str(results_dir)))
        return

    tickers = sorted(available.keys())
    col1, col2, col3 = st.columns([2, 2, 1])
    selected_ticker = col1.selectbox(t("sig.hist.ticker"), tickers, key="hist_ticker")
    dates = sorted(available[selected_ticker], reverse=True)
    selected_date = col2.selectbox(t("sig.hist.date"), dates, key="hist_date")
    load_btn = col3.button(t("sig.hist.load"), type="primary", use_container_width=True)

    if not load_btn:
        st.info(t("sig.hist.hint"))
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
        st.error(t("sig.hist.load_failed", err=str(exc)))
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
            date_str = f.stem.replace("full_states_log_", "")
            dates.append(date_str)
        if dates:
            available[ticker_dir.name] = dates
    return available


# ── Signal header ──────────────────────────────────────────────────────────────

_SIGNAL_COLOURS = {
    "BUY":         "#1B5E20",
    "OVERWEIGHT":  "#33691E",
    "HOLD":        "#37474F",
    "UNDERWEIGHT": "#E65100",
    "SELL":        "#B71C1C",
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
        f'<div style="font-size:0.85em;color:#555">{t("sig.header.signal", ticker=ticker, date=analysis_date)}</div>'
        f'<div style="font-size:2em;font-weight:700;color:{fg}">{sig}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    invest_state = state.get("investment_debate_state") or {}
    risk_state = state.get("risk_debate_state") or {}
    col2.markdown(
        f'<div style="background:#F3E5F5;border-left:6px solid #7B1FA2;'
        f'padding:14px 18px;border-radius:6px">'
        f'<div style="font-size:0.85em;color:#555">{t("sig.header.research")}</div>'
        f'<div style="font-size:1em;color:#4A148C">'
        f'{(invest_state.get("judge_decision") or "—")[:120]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    col3.markdown(
        f'<div style="background:#E3F2FD;border-left:6px solid #0D47A1;'
        f'padding:14px 18px;border-radius:6px">'
        f'<div style="font-size:0.85em;color:#555">{t("sig.header.risk")}</div>'
        f'<div style="font-size:1em;color:#0D47A1">'
        f'{(risk_state.get("judge_decision") or "—")[:120]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")


# ── Agent tabs ─────────────────────────────────────────────────────────────────

_TAB_KEYS = [
    "sig.tab.portfolio_mgr",
    "sig.tab.market",
    "sig.tab.news",
    "sig.tab.sentiment",
    "sig.tab.fundamentals",
    "sig.tab.bull",
    "sig.tab.bear",
    "sig.tab.research_mgr",
    "sig.tab.trader",
    "sig.tab.aggressive",
    "sig.tab.neutral",
    "sig.tab.conservative",
]


def _render_agent_tabs(state: dict):
    invest = state.get("investment_debate_state") or {}
    risk = state.get("risk_debate_state") or {}

    tabs = st.tabs([t(k) for k in _TAB_KEYS])

    # ── 0. Portfolio Manager ──────────────────────────────────────────
    with tabs[0]:
        _section_header(t("sig.sec.pm.title"), t("sig.sec.pm.desc"))
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
        _content_block(t("sig.block.final_decision"), decision)
        _content_block(t("sig.block.risk_judge"), risk.get("judge_decision") or "")
        _content_block(t("sig.block.risk_history"), risk.get("history") or "")

    # ── 1. Market Analyst ─────────────────────────────────────────────
    with tabs[1]:
        _section_header(t("sig.sec.market.title"), t("sig.sec.market.desc"))
        _content_block(t("sig.block.market_report"), state.get("market_report") or "")

    # ── 2. News Analyst ───────────────────────────────────────────────
    with tabs[2]:
        _section_header(t("sig.sec.news.title"), t("sig.sec.news.desc"))
        _content_block(t("sig.block.news_report"), state.get("news_report") or "")

    # ── 3. Sentiment Analyst ──────────────────────────────────────────
    with tabs[3]:
        _section_header(t("sig.sec.sent.title"), t("sig.sec.sent.desc"))
        _content_block(t("sig.block.sent_report"), state.get("sentiment_report") or "")

    # ── 4. Fundamentals Analyst ───────────────────────────────────────
    with tabs[4]:
        _section_header(t("sig.sec.fund.title"), t("sig.sec.fund.desc"))
        _content_block(t("sig.block.fund_report"), state.get("fundamentals_report") or "")

    # ── 5. Bull Researcher ────────────────────────────────────────────
    with tabs[5]:
        _section_header(t("sig.sec.bull.title"), t("sig.sec.bull.desc"))
        _content_block(t("sig.block.bull_arg"), invest.get("bull_history") or "")

    # ── 6. Bear Researcher ────────────────────────────────────────────
    with tabs[6]:
        _section_header(t("sig.sec.bear.title"), t("sig.sec.bear.desc"))
        _content_block(t("sig.block.bear_arg"), invest.get("bear_history") or "")

    # ── 7. Research Manager ───────────────────────────────────────────
    with tabs[7]:
        _section_header(t("sig.sec.rm.title"), t("sig.sec.rm.desc"))
        _content_block(t("sig.block.investment_plan"), state.get("investment_plan") or "")
        _content_block(t("sig.block.judge_invest"), invest.get("judge_decision") or "")
        _content_block(t("sig.block.invest_history"), invest.get("history") or "")

    # ── 8. Trader ─────────────────────────────────────────────────────
    with tabs[8]:
        _section_header(t("sig.sec.trader.title"), t("sig.sec.trader.desc"))
        _content_block(t("sig.block.trader_plan"), state.get("trader_investment_plan") or "")

    # ── 9. Aggressive Risk Debater ────────────────────────────────────
    with tabs[9]:
        _section_header(t("sig.sec.agg.title"), t("sig.sec.agg.desc"))
        _content_block(t("sig.block.agg_arg"), risk.get("aggressive_history") or "")

    # ── 10. Neutral Risk Debater ──────────────────────────────────────
    with tabs[10]:
        _section_header(t("sig.sec.neu.title"), t("sig.sec.neu.desc"))
        _content_block(t("sig.block.neu_arg"), risk.get("neutral_history") or "")

    # ── 11. Conservative Risk Debater ─────────────────────────────────
    with tabs[11]:
        _section_header(t("sig.sec.con.title"), t("sig.sec.con.desc"))
        _content_block(t("sig.block.con_arg"), risk.get("conservative_history") or "")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _section_header(title: str, description: str):
    st.markdown(f"#### {title}")
    st.caption(description)
    st.markdown("---")


def _content_block(label: str, text: str):
    """Render a labelled text block; show a placeholder if empty."""
    if not text or text.strip() == "":
        st.markdown(f"**{label}**")
        st.info(t("sig.block.empty"))
        return

    char_count = len(text)
    badge = f" `{t('sig.block.chars', n=f'{char_count:,}')}`" if char_count > 500 else ""
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
    for signal in ("OVERWEIGHT", "UNDERWEIGHT", "BUY", "SELL", "HOLD"):
        if re.search(rf"\b{signal}\b", text.upper()):
            return signal
    return "UNKNOWN"
