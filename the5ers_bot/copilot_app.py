"""
copilot_app.py
==============
**AI Co-Pilot & Sentinel Council Dashboard** - a live co-pilot for *manual*
day/swing trading on a The5ers *Bootcamp* evaluation account, fed by the native,
100% free **MetaTrader 5** Python library.

The app **never executes a trade**. It reads the local MT5 terminal, proposes a
fully-specified setup on the "Sentinel Signal Card" and has the Sentinel Council
audit it against the account's hard risk rules. *You* review the card and place the
order by hand in MetaTrader 5.

Design
------
* **Data** - :mod:`data_fetcher` attaches to the **local** MT5 terminal via
  ``mt5.initialize()``. No token, no cloud, no API key. Live ticks + historical
  OHLCV for EURUSD / GBPUSD / USDJPY / XAUUSD. If the package is unavailable
  (non-Windows) or the terminal is closed, it flips to a clearly-labelled offline
  simulator so the dashboard never crashes.
* **Sentinel Council** - :class:`sentinel_council.RiskEngine` is the deterministic,
  authoritative gate; the optional Groq *Scout* + Gemini *Risk Auditor* LLMs add a
  plain-English opinion and fail **open**.
* **Risk model (The5ers Bootcamp, $5,000 demo scaling to $20,000)** - 1R = $10, RRR
  floor 1:1.5, max 3 trades/day, circuit breaker at -$20 (2R) with a hard kill-switch
  at -$30 (3R), a +$20 daily profit target, and a London / London-NY session filter.

Run it:
    streamlit run the5ers_bot/copilot_app.py     # dashboard
    python the5ers_bot/copilot_app.py --once     # single headless pass (smoke test)

Streamlit Community Cloud starts the process from the repository root, so this
module's own directory is prepended to ``sys.path`` to resolve its sibling modules.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st  # noqa: E402

from data_fetcher import TIMEFRAMES, MT5Client, SymbolSpec  # noqa: E402
from sentinel_council import (  # noqa: E402
    ACCOUNT_SIZE_MAX_USD,
    ACCOUNT_SIZE_USD,
    DAILY_LOSS_KILL_USD,
    DAILY_LOSS_LOCK_USD,
    DAILY_PROFIT_TARGET_USD,
    MAX_TRADES_PER_DAY,
    MIN_RRR,
    RISK_PER_TRADE_USD,
    RiskAssessment,
    RiskEngine,
    SentinelCouncil,
)

LOGGER = logging.getLogger("copilot.app")

# --------------------------------------------------------------------------- #
# Dashboard defaults
# --------------------------------------------------------------------------- #
PAIRS: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
DEFAULT_SYMBOL = "EURUSD"
DEFAULT_TIMEFRAME = "15m"
CANDLES = 300
EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
DEFAULT_STOP_ATR = 1.5
DEFAULT_TARGET_RRR = 2.0
REFRESH_SECONDS = 10

CIRCUIT_STYLE = {
    "SAFE": {"color": "#26a69a", "icon": "🟢", "label": "SAFE", "blurb": "All guardrails clear - you may take a qualified setup."},
    "WATCH": {"color": "#ffa726", "icon": "🟡", "label": "WATCH", "blurb": "You are down ~1R today. Slow down and let the A+ setup come to you."},
    "LOCKED": {"color": "#ef5350", "icon": "🔴", "label": "LOCKED", "blurb": "Kill switch / circuit breaker active - NO new signals today."},
}
VERDICT_COLORS = {"long": "#26a69a", "short": "#ef5350", "neutral": "#787b86"}

RISK_ENGINE = RiskEngine()


# --------------------------------------------------------------------------- #
# Pure helpers (importable without a live terminal)
# --------------------------------------------------------------------------- #
def build_setup(
    df: pd.DataFrame,
    spec: SymbolSpec,
    tick: Dict[str, Any],
    *,
    symbol: str,
    daily_pnl: float,
    trades_today: int,
    now: Optional[datetime] = None,
    stop_atr_mult: float = DEFAULT_STOP_ATR,
    target_rrr: float = DEFAULT_TARGET_RRR,
    ema_fast: int = EMA_FAST,
    ema_slow: int = EMA_SLOW,
    rsi_period: int = RSI_PERIOD,
) -> Optional[Dict[str, Any]]:
    """Turn the latest candle + tick into a fully-specified, ATF-sized setup dict."""
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    close = float(last["close"])
    ema_f = float(last.get(f"ema{ema_fast}", close))
    ema_s = float(last.get(f"ema{ema_slow}", close))
    rsi = float(last.get(f"rsi{rsi_period}", 50.0))
    atr = float(last.get("atr14", 0.0))
    bid = float(tick.get("bid") or close)
    ask = float(tick.get("ask") or close)

    if ema_f > ema_s and rsi >= 50.0:
        direction = "long"
    elif ema_f < ema_s and rsi <= 50.0:
        direction = "short"
    else:
        direction = "neutral"

    stop_distance = max(atr * float(stop_atr_mult), spec.point * 10)
    rrr = max(MIN_RRR, float(target_rrr))
    tp_distance = stop_distance * rrr

    if direction == "long":
        entry, stop, tp = ask, ask - stop_distance, ask + tp_distance
    elif direction == "short":
        entry, stop, tp = bid, bid + stop_distance, bid - tp_distance
    else:
        entry, stop, tp = close, close - stop_distance, close + tp_distance

    return {
        "symbol": symbol,
        "direction": direction,
        "entry": round(entry, spec.digits),
        "stop": round(stop, spec.digits),
        "take_profit": round(tp, spec.digits),
        "value_per_unit": spec.value_per_price_unit_per_lot,
        "min_lot": spec.min_lot,
        "max_lot": spec.max_lot,
        "lot_step": spec.lot_step,
        "daily_pnl": round(float(daily_pnl), 2),
        "trades_today": int(trades_today),
        "now": now,
    }


def indicator_snapshot(df: pd.DataFrame) -> Dict[str, float]:
    """Latest EMA / RSI / ATR values for the market-intelligence panel."""
    if df is None or df.empty:
        return {}
    last = df.iloc[-1]
    return {
        "close": float(last["close"]),
        f"ema{EMA_FAST}": float(last.get(f"ema{EMA_FAST}", last["close"])),
        f"ema{EMA_SLOW}": float(last.get(f"ema{EMA_SLOW}", last["close"])),
        f"rsi{RSI_PERIOD}": float(last.get(f"rsi{RSI_PERIOD}", 50.0)),
        "atr14": float(last.get("atr14", 0.0)),
    }


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("cp_client", None)
    ss.setdefault("cp_council", None)
    ss.setdefault("cp_connect_error", "")
    ss.setdefault("cp_daily_pnl", 0.0)
    ss.setdefault("cp_trades_today", 0)
    ss.setdefault("cp_verdict", None)
    ss.setdefault("cp_activity", [])


def _apply_pending() -> None:
    """Fold queued button deltas into the keyed P&L widgets *before* they render."""
    ss = st.session_state
    if "cp_pnl_pending" in ss:
        ss.cp_daily_pnl = round(float(ss.cp_daily_pnl) + float(ss.cp_pnl_pending), 2)
        del ss.cp_pnl_pending
    if "cp_trades_pending" in ss:
        ss.cp_trades_today = max(0, int(ss.cp_trades_today) + int(ss.cp_trades_pending))
        del ss.cp_trades_pending


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    entry = f"{stamp} UTC · {message}"
    log: List[str] = st.session_state.cp_activity
    if not log or log[0] != entry:
        log.insert(0, entry)
    del log[40:]


def _client() -> MT5Client:
    ss = st.session_state
    if ss.cp_client is None:
        ss.cp_client = MT5Client(symbols=PAIRS)
    return ss.cp_client


def _council(groq_key: str, gemini_key: str) -> SentinelCouncil:
    ss = st.session_state
    if ss.cp_council is None:
        ss.cp_council = SentinelCouncil(
            groq_api_key=groq_key or None, gemini_api_key=gemini_key or None, risk_engine=RISK_ENGINE
        )
    else:
        ss.cp_council.configure(groq_api_key=groq_key or None, gemini_api_key=gemini_key or None)
    return ss.cp_council


# --------------------------------------------------------------------------- #
# UI - sidebar
# --------------------------------------------------------------------------- #
def render_sidebar(client: MT5Client) -> Dict[str, Any]:
    ss = st.session_state
    with st.sidebar:
        st.markdown("## ⚙️ Control Panel")

        st.markdown("### 🔌 MetaTrader 5")
        if client.connected:
            st.success("Terminal connected", icon="✅")
        elif client.available:
            st.warning("Terminal not connected", icon="⚠️")
        else:
            st.info("`MetaTrader5` not installed (Windows-only) - offline simulator active.", icon="🧪")

        with st.expander("Connection options (optional)", expanded=not client.connected):
            path = st.text_input("Terminal path (mt5.exe)", value="", help="Leave blank to use the running terminal.")
            login = st.text_input("Login (optional)", value="")
            password = st.text_input("Password (optional)", value="", type="password")
            server = st.text_input("Server (optional)", value="")
            col_c, col_d = st.columns(2)
            if col_c.button("Connect", use_container_width=True, type="primary"):
                ok = client.initialize(
                    path=path.strip(),
                    login=int(login) if login.strip().isdigit() else 0,
                    password=password,
                    server=server.strip(),
                )
                ss.cp_connect_error = "" if ok else client.last_error
                _log("MT5 connect " + ("succeeded." if ok else f"failed: {client.last_error}"))
                st.rerun()
            if col_d.button("Disconnect", use_container_width=True):
                client.shutdown()
                _log("MT5 disconnected.")
                st.rerun()
        if ss.cp_connect_error and not client.connected:
            st.caption(f"Last error: {ss.cp_connect_error}")

        st.divider()

        st.markdown("### 📈 Instrument")
        symbol = st.selectbox("Symbol", PAIRS, index=PAIRS.index(DEFAULT_SYMBOL))
        timeframe = st.selectbox("Timeframe", list(TIMEFRAMES.keys()), index=list(TIMEFRAMES.keys()).index(DEFAULT_TIMEFRAME))
        stop_atr = st.slider("Stop = ATR ×", 0.5, 3.0, DEFAULT_STOP_ATR, 0.25)
        target_rrr = st.slider("Target RRR", float(MIN_RRR), 4.0, DEFAULT_TARGET_RRR, 0.5, help=f"Hard floor is 1:{MIN_RRR:g}.")

        st.divider()

        st.markdown("### 🧮 Daily Guardrail Tracker")
        auto_default = not client.connected
        manual = st.checkbox("Manual P&L / trade override", value=auto_default)
        st.number_input("Daily P&L (USD)", key="cp_daily_pnl", step=float(RISK_PER_TRADE_USD), format="%.2f")
        st.number_input("Trades taken today", key="cp_trades_today", step=1, min_value=0, max_value=MAX_TRADES_PER_DAY)
        b1, b2, b3 = st.columns(3)
        if b1.button(f"+1R", use_container_width=True, help=f"+${RISK_PER_TRADE_USD:.0f}"):
            ss.cp_pnl_pending = RISK_PER_TRADE_USD
            ss.cp_trades_pending = 1
            st.rerun()
        if b2.button(f"-1R", use_container_width=True, help=f"-${RISK_PER_TRADE_USD:.0f}"):
            ss.cp_pnl_pending = -RISK_PER_TRADE_USD
            ss.cp_trades_pending = 1
            st.rerun()
        if b3.button("Reset", use_container_width=True):
            ss.cp_pnl_pending = -float(ss.cp_daily_pnl)
            ss.cp_trades_pending = -int(ss.cp_trades_today)
            st.rerun()
        st.caption(
            f"Lock ≤ {DAILY_LOSS_LOCK_USD:+.0f} (2R) · Kill ≤ {DAILY_LOSS_KILL_USD:+.0f} (3R) · "
            f"Bank ≥ {DAILY_PROFIT_TARGET_USD:+.0f} · Max {MAX_TRADES_PER_DAY} trades."
        )

        st.divider()

        st.markdown("### 🧠 Sentinel Council (optional LLMs)")
        groq_key = st.text_input("Groq API key (Scout)", value=os.getenv("GROQ_API_KEY", ""), type="password")
        gemini_key = st.text_input("Gemini API key (Auditor)", value=os.getenv("GEMINI_API_KEY", ""), type="password")
        auto_refresh = st.toggle("Auto-refresh", value=False, help=f"Re-read the terminal every {REFRESH_SECONDS}s.")

    daily_pnl = float(ss.cp_daily_pnl) if manual or not client.connected else float(client.daily_pnl())
    trades_today = int(ss.cp_trades_today) if manual or not client.connected else int(client.trades_today())

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "stop_atr": float(stop_atr),
        "target_rrr": float(target_rrr),
        "daily_pnl": daily_pnl,
        "trades_today": trades_today,
        "groq_key": groq_key.strip(),
        "gemini_key": gemini_key.strip(),
        "auto_refresh": bool(auto_refresh),
        "manual": bool(manual),
    }


# --------------------------------------------------------------------------- #
# UI - panels
# --------------------------------------------------------------------------- #
def render_status(client: MT5Client) -> None:
    if client.connected:
        st.success(
            f"🟢 **MT5 LIVE** - connected to the local terminal. Prices shown are the terminal's real quotes.",
        )
    elif client.available:
        st.warning(
            "🟡 **MT5 not connected** - the terminal appears closed or not logged in. "
            "Open MetaTrader 5 (or click *Connect* in the sidebar). Showing **simulated** data.",
        )
    else:
        st.info(
            "🔵 **Offline simulator** - the `MetaTrader5` package is Windows-only and is not installed here. "
            "All figures below are clearly-labelled simulated data so you can test-drive the dashboard. "
            "Run this on Windows with MT5 open for live data.",
        )


def render_circuit(assessment: RiskAssessment) -> None:
    style = CIRCUIT_STYLE.get(assessment.circuit, CIRCUIT_STYLE["SAFE"])
    locked = assessment.circuit == "LOCKED"
    st.markdown(
        f"""
        <div style="border:2px solid {style['color']};border-radius:12px;padding:14px 18px;
                    background:{style['color']}1a;margin-bottom:8px;">
          <div style="font-size:22px;font-weight:700;color:{style['color']};">
            {style['icon']} KILL SWITCH / CIRCUIT BREAKER: {style['label']}
          </div>
          <div style="color:#c9cdd4;font-size:14px;margin-top:4px;">{style['blurb']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if locked:
        for reason in assessment.lock_reasons:
            st.error(reason, icon="🚫")
    elif assessment.circuit == "WATCH":
        for reason in assessment.lock_reasons:
            st.warning(reason, icon="⚠️")


def render_account(client: MT5Client, daily_pnl: float, trades_today: int, manual: bool) -> None:
    acct = client.account_info()
    cols = st.columns(5)
    cols[0].metric("Balance", f"${acct.get('balance', 0.0):,.2f}", help=f"Demo base ${ACCOUNT_SIZE_USD:,.0f} → funded ${ACCOUNT_SIZE_MAX_USD:,.0f}")
    cols[1].metric("Equity", f"${acct.get('equity', 0.0):,.2f}")
    cols[2].metric("Floating P/L", f"${acct.get('profit', 0.0):+,.2f}")
    cols[3].metric("Daily P/L", f"${daily_pnl:+,.2f}", help="Manual override" if manual else "From MT5 history + floating")
    cols[4].metric("Trades today", f"{trades_today}/{MAX_TRADES_PER_DAY}")
    if acct.get("offline"):
        st.caption(
            f"Account base: ${ACCOUNT_SIZE_USD:,.0f} demo (scaling to ${ACCOUNT_SIZE_MAX_USD:,.0f}) · "
            f"risk/trade ${RISK_PER_TRADE_USD:.0f} (1R) · source: offline simulator"
        )


def render_prices(client: MT5Client) -> None:
    st.markdown("#### 💱 Live Market Prices")
    rows = []
    for symbol in PAIRS:
        tick = client.tick(symbol)
        rows.append(
            {
                "Symbol": symbol,
                "Bid": f"{tick.get('bid', 0.0):.{client.spec(symbol).digits}f}",
                "Ask": f"{tick.get('ask', 0.0):.{client.spec(symbol).digits}f}",
                "Spread": f"{tick.get('spread', 0.0):.{client.spec(symbol).digits}f}",
                "Source": "SIM" if tick.get("offline") else "MT5",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_market_intelligence(df: pd.DataFrame, symbol: str, digits: int) -> None:
    st.markdown(f"#### 📊 Market Intelligence - {symbol}")
    snapshot = indicator_snapshot(df)
    if not snapshot:
        st.warning("No candle data available for this symbol yet.")
        return
    m = st.columns(5)
    m[0].metric("Close", f"{snapshot['close']:.{digits}f}")
    m[1].metric(f"EMA{EMA_FAST}", f"{snapshot[f'ema{EMA_FAST}']:.{digits}f}")
    m[2].metric(f"EMA{EMA_SLOW}", f"{snapshot[f'ema{EMA_SLOW}']:.{digits}f}")
    m[3].metric(f"RSI{RSI_PERIOD}", f"{snapshot[f'rsi{RSI_PERIOD}']:.1f}")
    m[4].metric("ATR14", f"{snapshot['atr14']:.{digits}f}")

    trend = "UPTREND" if snapshot[f"ema{EMA_FAST}"] > snapshot[f"ema{EMA_SLOW}"] else "DOWNTREND"
    st.caption(f"Bias: **{trend}** (EMA{EMA_FAST} vs EMA{EMA_SLOW}) · RSI{RSI_PERIOD} {snapshot[f'rsi{RSI_PERIOD}']:.1f}")

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        view = df.tail(CANDLES).reset_index(drop=True)
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04,
            subplot_titles=("", "RSI"),
        )
        fig.add_trace(
            go.Candlestick(
                x=view["time"], open=view["open"], high=view["high"], low=view["low"], close=view["close"],
                name=symbol, increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
            ),
            row=1, col=1,
        )
        fig.add_trace(go.Scatter(x=view["time"], y=view[f"ema{EMA_FAST}"], name=f"EMA{EMA_FAST}",
                                 line=dict(color="#42a5f5", width=1.4)), row=1, col=1)
        fig.add_trace(go.Scatter(x=view["time"], y=view[f"ema{EMA_SLOW}"], name=f"EMA{EMA_SLOW}",
                                 line=dict(color="#ffa726", width=1.4)), row=1, col=1)
        fig.add_trace(go.Scatter(x=view["time"], y=view[f"rsi{RSI_PERIOD}"], name=f"RSI{RSI_PERIOD}",
                                 line=dict(color="#ab47bc", width=1.4)), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#787b86", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#787b86", row=2, col=1)
        fig.update_layout(
            height=460, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:  # noqa: BLE001 - charting must never kill the page
        st.caption(f"Chart unavailable: {exc}")
        st.dataframe(df.tail(60), use_container_width=True)


def render_signal_card(assessment: RiskAssessment, council_status: Dict[str, Any]) -> None:
    st.markdown("#### 🎯 Sentinel Signal Card")
    if assessment.direction == "neutral":
        st.info("No qualified directional setup right now (EMA50/EMA200 and RSI disagree). Wait for alignment.", icon="⏳")
        return

    color = VERDICT_COLORS.get(assessment.direction, "#787b86")
    status = "APPROVED" if assessment.allowed else "BLOCKED"
    status_color = "#26a69a" if assessment.allowed else "#ef5350"
    st.markdown(
        f"""
        <div style="border:2px solid {color};border-radius:12px;padding:14px 18px;background:{color}14;">
          <div style="font-size:20px;font-weight:700;color:{color};">
            {assessment.direction.upper()} {assessment.symbol}
          </div>
          <div style="color:{status_color};font-weight:700;margin-top:2px;">COUNCIL: {status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c = st.columns(4)
    c[0].metric("Entry", f"{assessment.entry:g}")
    c[1].metric("Stop loss", f"{assessment.stop:g}")
    c[2].metric("Take profit", f"{assessment.take_profit:g}")
    c[3].metric("Lot size", f"{assessment.lot:.2f}")

    r = st.columns(4)
    r[0].metric("RRR", f"1:{assessment.rrr:.2f}", delta="ok" if assessment.rrr_ok else f"min 1:{MIN_RRR:g}",
                delta_color="normal" if assessment.rrr_ok else "inverse")
    r[1].metric("Risk", f"${assessment.risk_usd:+,.2f}")
    r[2].metric("Reward", f"${assessment.reward_usd:+,.2f}")
    r[3].metric("Trades left", f"{assessment.trades_remaining}")

    sessions = ", ".join(assessment.sessions) if assessment.sessions else "None (off-session)"
    st.caption(f"Session: **{sessions}** · {'session open ✅' if assessment.session_ok else 'session closed ⛔'}")
    if council_status:
        st.caption(
            f"Scout: {'🟢 ' + str(council_status.get('scout_models', [''])[0]) if council_status.get('scout') else '⚪ offline'} · "
            f"Auditor: {'🟢 ' + str(council_status.get('auditor_models', [''])[0]) if council_status.get('auditor') else '⚪ offline'}"
        )

    for message in assessment.messages:
        st.caption(f"• {message}")

    if not assessment.allowed:
        st.error("This setup does NOT pass the risk gate - do not place it.", icon="🚫")
    else:
        st.success("Passes the deterministic risk gate. Review, then place by hand in MT5.", icon="✅")


def render_council_verdict(verdict: Any) -> None:
    if verdict is None:
        return
    st.markdown("##### 🧠 Council Deliberation")
    if verdict.degraded:
        st.caption("Council ran in degraded mode (one or both LLMs unavailable) - the deterministic Risk Auditor is authoritative.")
    cols = st.columns(2)
    for col, label, opinion in ((cols[0], "Scout (Groq)", verdict.scout), (cols[1], "Risk Auditor (Gemini)", verdict.auditor)):
        with col:
            if opinion is None:
                st.markdown(f"**{label}** · ⚪ not consulted")
            elif opinion.ok:
                st.markdown(f"**{label}** · `{opinion.model}` · {opinion.verdict.upper()} ({opinion.confidence:.0%})")
                if opinion.summary:
                    st.caption(opinion.summary)
                if opinion.fallback:
                    st.caption(f"↳ fallback (tried: {', '.join(opinion.attempted)})")
            else:
                st.markdown(f"**{label}** · 🔴 unavailable")
                st.caption(opinion.error or "no response")
    st.caption(f"Verdict: **{verdict.verdict.upper()}** · approved={verdict.approved} · {verdict.elapsed_ms} ms · {verdict.summary}")
    for message in verdict.messages:
        st.caption(f"• {message}")


def render_activity() -> None:
    st.markdown("#### 🗒️ Activity Log")
    log = st.session_state.cp_activity
    if not log:
        st.caption("No events yet.")
        return
    for entry in log[:15]:
        st.caption(entry)


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render_page(params: Dict[str, Any], client: MT5Client) -> None:
    symbol = params["symbol"]
    timeframe = params["timeframe"]
    df = client.fetch_frame(symbol, timeframe, CANDLES)
    spec = client.spec(symbol)
    tick = client.tick(symbol)

    now = datetime.now(timezone.utc)
    setup = build_setup(
        df, spec, tick, symbol=symbol, daily_pnl=params["daily_pnl"],
        trades_today=params["trades_today"], now=now,
        stop_atr_mult=params["stop_atr"], target_rrr=params["target_rrr"],
    )
    assessment = RISK_ENGINE.assess(setup or {"direction": "neutral"})

    top = st.columns([2, 1])
    with top[0]:
        render_status(client)
    with top[1]:
        st.metric("UTC clock", now.strftime("%H:%M:%S"), help="Sessions are evaluated in UTC.")

    render_circuit(assessment)
    render_account(client, params["daily_pnl"], params["trades_today"], params["manual"])

    st.divider()
    left, right = st.columns([1.35, 1])
    with left:
        render_market_intelligence(df, symbol, spec.digits)
    with right:
        render_prices(client)

    st.divider()
    render_signal_card(assessment, (st.session_state.cp_council.status() if st.session_state.cp_council else {}))

    consult_cols = st.columns([1, 2])
    if consult_cols[0].button("🧠 Consult Sentinel Council", use_container_width=True, type="primary", disabled=setup is None):
        council = _council(params["groq_key"], params["gemini_key"])
        with st.spinner("Scout and Risk Auditor are deliberating…"):
            verdict = council.evaluate(setup or {})
        st.session_state.cp_verdict = verdict
        _log(f"Council consulted -> {verdict.verdict} (approved={verdict.approved}).")
    if consult_cols[1].button("🧹 Clear verdict"):
        st.session_state.cp_verdict = None
        st.rerun()

    render_council_verdict(st.session_state.cp_verdict)
    st.divider()
    render_activity()


def main() -> None:
    st.set_page_config(page_title="AI Co-Pilot · Sentinel Council", page_icon="🛰️", layout="wide")
    _init_state()
    _apply_pending()

    client = _client()
    params = render_sidebar(client)

    st.title("🛰️ AI Co-Pilot · Sentinel Council")
    st.caption(
        f"The5ers Bootcamp evaluation · ${ACCOUNT_SIZE_USD:,.0f} demo → ${ACCOUNT_SIZE_MAX_USD:,.0f} funded · "
        f"1R=${RISK_PER_TRADE_USD:.0f} · RRR ≥ 1:{MIN_RRR:g} · max {MAX_TRADES_PER_DAY} trades/day · "
        f"circuit breaker {DAILY_LOSS_LOCK_USD:+.0f}/{DAILY_LOSS_KILL_USD:+.0f} · "
        "advisory only - you place every order by hand."
    )

    if params["auto_refresh"]:
        st.fragment(run_every=REFRESH_SECONDS)(render_page)(params, client)
    else:
        render_page(params, client)


# --------------------------------------------------------------------------- #
# Headless smoke test
# --------------------------------------------------------------------------- #
def run_once() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = MT5Client(symbols=PAIRS)
    connected = client.initialize()
    print(f"MT5 package available: {client.available} | connected: {connected} | offline: {client.offline}")
    if not connected:
        print(f"Reason: {client.last_error or 'terminal unavailable'}")
    acct = client.account_info()
    print(f"Account: balance={acct['balance']:.2f} equity={acct['equity']:.2f} source={'offline' if acct.get('offline') else 'MT5'}")

    now = datetime.now(timezone.utc)
    for symbol in PAIRS:
        df = client.fetch_frame(symbol, DEFAULT_TIMEFRAME, CANDLES)
        spec = client.spec(symbol)
        tick = client.tick(symbol)
        setup = build_setup(df, spec, tick, symbol=symbol, daily_pnl=0.0, trades_today=0, now=now)
        assessment = RISK_ENGINE.assess(setup)
        print(
            f"{symbol:7s} rows={len(df):4d} bid={tick['bid']:.{spec.digits}f} ask={tick['ask']:.{spec.digits}f} "
            f"| {assessment.direction:7s} lot={assessment.lot:.2f} rrr=1:{assessment.rrr:.2f} "
            f"circuit={assessment.circuit} allowed={assessment.allowed} sessions={assessment.sessions}"
        )

    council = SentinelCouncil(risk_engine=RISK_ENGINE)
    verdict = council.evaluate(
        build_setup(
            client.fetch_frame(DEFAULT_SYMBOL, DEFAULT_TIMEFRAME, CANDLES),
            client.spec(DEFAULT_SYMBOL), client.tick(DEFAULT_SYMBOL),
            symbol=DEFAULT_SYMBOL, daily_pnl=0.0, trades_today=0, now=now,
        )
    )
    print(f"Council: verdict={verdict.verdict} approved={verdict.approved} degraded={verdict.degraded}")
    council.close()
    client.shutdown()
    print("run_once complete.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Co-Pilot & Sentinel Council dashboard (native MT5).")
    parser.add_argument("--once", action="store_true", help="Run a single headless pass and exit (smoke test).")
    args = parser.parse_args()
    if args.once:
        raise SystemExit(run_once())
    main()
