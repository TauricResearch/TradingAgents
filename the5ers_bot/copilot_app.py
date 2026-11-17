"""
copilot_app.py
==============
**AI Co-Pilot Dashboard** - a signal generator + risk auditor for *manual*
forex/crypto day & swing trading on a The5ers $2,500 High Stakes account.

This app **never executes a trade**. It is a co-pilot: it reads the market, proposes
a fully-specified setup on the "AI Signal Card" and has the Sentinel Council audit it
against the account's hard risk rules. *You* review the card and place the order by
hand in MetaTrader 5.

Design
------
* **Data** - read-only feed via MetaApi (investor password), so prices match the MT5
  terminal exactly. :mod:`metaapi_client` owns the async SDK behind a sync facade.
* **Advisory** - :class:`sentinel_council.SentinelCouncil` blends a Groq *Scout*
  (trend/momentum) with a Gemini *Risk Auditor*. It is advisory only, hard-timeboxed
  and fails **open** - it can never block or crash this dashboard.
* **Risk model ($2,500 High Stakes)** - 1R = $10, TP = $30 (RRR 1:3), daily profit
  ceiling +$40 (lock-profit alert), daily kill-switch -$50 (a hard stop *before* the
  prop-firm's -$125 limit). Lot size is kept inside 0.01-0.02 micro lots.

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from metaapi_client import TIMEFRAMES, MetaApiFeed, symbol_spec  # noqa: E402
from sentinel_council import MIN_RRR, CouncilVerdict, SentinelCouncil  # noqa: E402

LOGGER = logging.getLogger("copilot.app")

# --------------------------------------------------------------------------- #
# Risk parameters - The5ers "$2,500 High Stakes" account
# --------------------------------------------------------------------------- #
ACCOUNT_SIZE_USD = 2_500.0
RISK_PER_TRADE_USD = 10.0            # 1R
TAKE_PROFIT_USD = 30.0               # 3R (minimum)
DAILY_PROFIT_CEILING_USD = 40.0      # lock-profit alert
DAILY_LOSS_KILL_USD = -50.0          # daily kill-switch (prop-firm limit is -$125)
MIN_LOT = 0.01
MAX_LOT = 0.02
LOT_STEP = 0.01
TARGET_RRR = TAKE_PROFIT_USD / RISK_PER_TRADE_USD  # 3.0

# Strategy / signal-engine parameters.
EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
RSI_LONG_MIN = 50.0
RSI_SHORT_MAX = 50.0
ATR_STOP_MULT = 1.5                  # volatility reference for lot sizing
CANDLES = 240
DEFAULT_SYMBOL = "EURUSD"
DEFAULT_TIMEFRAME = "15m"
REFRESH_SECONDS = 10

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF",
         "USDJPY", "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]

VERDICT_COLORS = {"long": "#26a69a", "short": "#ef5350", "neutral": "#787b86"}


# --------------------------------------------------------------------------- #
# Pure helpers (importable without streamlit)
# --------------------------------------------------------------------------- #
def mask(secret: str, keep: int = 4) -> str:
    """Mask a secret for display, keeping only the last few characters."""
    if not secret:
        return ""
    if len(secret) <= keep:
        return "*" * len(secret)
    return "*" * (len(secret) - keep) + secret[-keep:]


def clamp_lot(lot: float) -> float:
    """Snap ``lot`` to the broker step and clamp it into [MIN_LOT, MAX_LOT]."""
    try:
        value = float(lot)
    except (TypeError, ValueError):
        value = MAX_LOT
    value = max(MIN_LOT, min(MAX_LOT, value))
    return round(round(value / LOT_STEP) * LOT_STEP, 2)


def guardrail_state(daily_pnl: float) -> str:
    """``"KILL"`` / ``"LOCK"`` / ``"ACTIVE"`` for the daily guardrail."""
    if daily_pnl <= DAILY_LOSS_KILL_USD:
        return "KILL"
    if daily_pnl >= DAILY_PROFIT_CEILING_USD:
        return "LOCK"
    return "ACTIVE"


def day_progress(daily_pnl: float) -> Dict[str, float]:
    """Fractions (0-1) of the distance travelled toward each guardrail boundary."""
    to_ceiling = max(0.0, min(1.0, daily_pnl / DAILY_PROFIT_CEILING_USD)) if daily_pnl > 0 else 0.0
    to_kill = max(0.0, min(1.0, -daily_pnl / abs(DAILY_LOSS_KILL_USD))) if daily_pnl < 0 else 0.0
    return {"to_ceiling": to_ceiling, "to_kill": to_kill}


@dataclass
class SignalSetup:
    """A complete, manually executable setup with exact money-based SL/TP."""

    symbol: str
    timeframe: str
    verdict: str                     # LONG / SHORT / NEUTRAL / STOP
    entry: float
    stop_loss: float
    take_profit: float
    lot: float
    risk_usd: float
    reward_usd: float
    rrr: float
    digits: int
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    rsi: float = 50.0
    atr: float = 0.0
    armed: bool = False
    notes: List[str] = field(default_factory=list)

    def signature(self) -> str:
        return f"{self.symbol}|{self.timeframe}|{self.verdict}|{self.entry:.{self.digits}f}|{self.lot:.2f}"

    def to_council_payload(self, daily_pnl: float) -> Dict[str, Any]:
        return {
            "pair": self.symbol,
            "timeframe": self.timeframe,
            "proposed_direction": self.verdict,
            "entry": round(self.entry, self.digits),
            "stop_loss": round(self.stop_loss, self.digits),
            "take_profit": round(self.take_profit, self.digits),
            "risk_usd": self.risk_usd,
            "reward_usd": self.reward_usd,
            "rrr": self.rrr,
            "lot": self.lot,
            "ema50": round(self.ema_fast, self.digits),
            "ema200": round(self.ema_slow, self.digits),
            "rsi14": round(self.rsi, 2),
            "atr14": round(self.atr, self.digits),
            "daily_pnl_usd": daily_pnl,
            "daily_ceiling_usd": DAILY_PROFIT_CEILING_USD,
            "daily_kill_switch_usd": DAILY_LOSS_KILL_USD,
        }


def compute_signal(
    frame: Any,
    symbol: str,
    timeframe: str,
    spec: Any = None,
    lot_preference: Optional[float] = None,
) -> Optional[SignalSetup]:
    """Turn an indicator frame into a :class:`SignalSetup`.

    Direction comes from the EMA50/EMA200 trend stack confirmed by RSI(14). The
    stop and target distances are derived from the *money* budget so the card always
    shows exactly 1R = $10 and 3R = $30 at the recommended lot (RRR = 1:3), while the
    lot itself is scaled to volatility (ATR) and clamped to 0.01-0.02.
    """
    if frame is None or frame.empty:
        return None
    required = {"close", f"ema{EMA_FAST}", f"ema{EMA_SLOW}", f"rsi{RSI_PERIOD}", "atr14"}
    if not required.issubset(frame.columns):
        LOGGER.warning("compute_signal: missing columns %s", required - set(frame.columns))
        return None

    last = frame.iloc[-1]
    entry = float(last["close"])
    ema_fast = float(last[f"ema{EMA_FAST}"])
    ema_slow = float(last[f"ema{EMA_SLOW}"])
    rsi = float(last[f"rsi{RSI_PERIOD}"])
    atr = float(last["atr14"])

    spec = spec or symbol_spec(symbol)
    digits = int(getattr(spec, "digits", 5))
    value_per_unit = float(getattr(spec, "value_per_price_unit_per_lot", 100_000.0) or 0.0)
    notes: List[str] = []

    if ema_fast > ema_slow and rsi >= RSI_LONG_MIN:
        verdict = "LONG"
        notes.append("EMA50 above EMA200 with RSI above 50 - bullish trend + momentum.")
    elif ema_fast < ema_slow and rsi <= RSI_SHORT_MAX:
        verdict = "SHORT"
        notes.append("EMA50 below EMA200 with RSI below 50 - bearish trend + momentum.")
    else:
        verdict = "NEUTRAL"
        notes.append("EMA stack and RSI disagree - no edge, stand down.")

    # Volatility-aware lot: keep the 1.5xATR stop near the $10 risk budget.
    stop_dist_atr = ATR_STOP_MULT * atr
    if lot_preference:
        lot = clamp_lot(lot_preference)
    elif stop_dist_atr > 0 and value_per_unit > 0:
        lot = clamp_lot(RISK_PER_TRADE_USD / (stop_dist_atr * value_per_unit))
    else:
        lot = MAX_LOT

    # Money-based distances guarantee exactly 1R = $10 and 3R = $30 at this lot.
    if value_per_unit > 0 and lot > 0:
        stop_distance = RISK_PER_TRADE_USD / (value_per_unit * lot)
        tp_distance = TAKE_PROFIT_USD / (value_per_unit * lot)
    else:  # unknown contract - fall back to the ATR stop
        stop_distance = stop_dist_atr
        tp_distance = stop_dist_atr * TARGET_RRR

    if verdict == "SHORT":
        stop_loss = entry + stop_distance
        take_profit = entry - tp_distance
    else:
        stop_loss = entry - stop_distance
        take_profit = entry + tp_distance

    if atr > 0:
        notes.append(
            f"ATR({digits}d) stop 1.5xATR = {stop_dist_atr:.{digits}f} vs money-stop "
            f"{stop_distance:.{digits}f} ({'wider' if stop_distance >= stop_dist_atr else 'tighter'})."
        )
        if verdict != "NEUTRAL" and stop_distance < stop_dist_atr:
            notes.append("Money-stop sits inside 1.5xATR - expect noise; consider 0.01 lot to widen it.")
    if lot <= MIN_LOT:
        notes.append("Lot pinned at the 0.01 micro-lot floor (safe-margin default).")

    return SignalSetup(
        symbol=symbol,
        timeframe=timeframe,
        verdict=verdict,
        entry=round(entry, digits),
        stop_loss=round(stop_loss, digits),
        take_profit=round(take_profit, digits),
        lot=lot,
        risk_usd=RISK_PER_TRADE_USD,
        reward_usd=TAKE_PROFIT_USD,
        rrr=TARGET_RRR,
        digits=digits,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        atr=atr,
        armed=verdict in {"LONG", "SHORT"},
        notes=notes,
    )


def bid_ask_wall(book: Dict[str, Any]) -> Dict[str, Any]:
    """Return the largest resting level on each side of the book ("the wall")."""
    def _biggest(levels: List[Any]) -> Optional[Dict[str, float]]:
        best: Optional[Dict[str, float]] = None
        for price, size in levels or []:
            if best is None or size > best["size"]:
                best = {"price": float(price), "size": float(size)}
        return best

    return {
        "bid_wall": _biggest(book.get("bids") or []),
        "ask_wall": _biggest(book.get("asks") or []),
    }


# --------------------------------------------------------------------------- #
# Streamlit helpers (imported lazily so `--once` works without streamlit)
# --------------------------------------------------------------------------- #
def _secret(key: str) -> str:
    """Read ``st.secrets[key]`` on the UI thread; ``""`` when absent/not in Streamlit."""
    try:
        import streamlit as st
    except Exception:
        return ""
    try:
        value = st.secrets.get(key, "")
    except Exception:
        return ""
    return str(value).strip() if value not in (None, "") else ""


def _cred_source(session_value: str, *keys: str) -> str:
    """Label where a credential came from: dashboard input, ``st.secrets``/env, or missing."""
    if session_value:
        return "dashboard input"
    for key in keys:
        if _secret(key) or os.getenv(key, "").strip():
            return "secrets/env"
    return "missing"


def resolve_credentials() -> Dict[str, str]:
    """Sidebar inputs -> ``st.secrets`` -> environment. UI thread only."""
    token = st_session("cp_token", "") or _secret("METAAPI_TOKEN") or os.getenv("METAAPI_TOKEN", "")
    account_id = st_session("cp_account_id", "") or _secret("METAAPI_ACCOUNT_ID") or os.getenv("METAAPI_ACCOUNT_ID", "")
    gemini = st_session("cp_gemini_key", "") or _secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    groq = st_session("cp_groq_key", "") or _secret("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")
    return {
        "token": token.strip(),
        "account_id": account_id.strip(),
        "gemini_api_key": gemini.strip(),
        "groq_api_key": groq.strip(),
    }


def st_session(key: str, default: Any = None) -> Any:
    """``st.session_state.get`` that is a no-op outside a Streamlit runtime."""
    try:
        import streamlit as st
    except Exception:
        return default
    return st.session_state.get(key, default)


def _fragment(run_every: int):
    """Return a ``@st.fragment(run_every=...)`` decorator, or a no-op fallback."""
    try:
        import streamlit as st
    except Exception:
        return lambda fn: fn
    factory = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
    if factory is None:
        return lambda fn: fn
    try:
        return factory(run_every=run_every)
    except TypeError:
        return lambda fn: fn


def get_feed() -> MetaApiFeed:
    import streamlit as st

    if "cp_feed" not in st.session_state:
        st.session_state["cp_feed"] = MetaApiFeed()
    return st.session_state["cp_feed"]


def get_council(creds: Dict[str, str]) -> SentinelCouncil:
    import streamlit as st

    council: Optional[SentinelCouncil] = st.session_state.get("cp_council")
    if council is None:
        council = SentinelCouncil(
            timeout=8.0,
            groq_api_key=creds.get("groq_api_key", ""),
            gemini_api_key=creds.get("gemini_api_key", ""),
        )
        st.session_state["cp_council"] = council
    else:
        council.configure(
            groq_api_key=creds.get("groq_api_key", ""),
            gemini_api_key=creds.get("gemini_api_key", ""),
        )
    return council


def log_event(message: str) -> None:
    import streamlit as st

    entries = st.session_state.setdefault("cp_log", [])
    entries.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z  {message}")
    del entries[:-200]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _render_sidebar() -> Dict[str, Any]:
    import streamlit as st

    st.sidebar.header("Control Panel")

    env_account = os.getenv("METAAPI_ACCOUNT_ID", "").strip()
    st.session_state.setdefault("cp_token", "")
    st.session_state.setdefault("cp_account_id", "")
    st.session_state.setdefault("cp_gemini_key", "")
    st.session_state.setdefault("cp_groq_key", "")

    with st.sidebar.expander("🔐 MetaApi Feed (read-only)", expanded=not st.session_state["cp_account_id"]):
        st.caption("Use your **investor / read-only** password. The co-pilot never trades.")
        st.text_input("MetaApi Token", key="cp_token", type="password", placeholder="paste token")
        st.text_input("Account ID", key="cp_account_id", placeholder="MetaApi account id")
        st.caption(f"Token: {_cred_source(st.session_state['cp_token'], 'METAAPI_TOKEN')} · "
                   f"Account: {_cred_source(st.session_state['cp_account_id'], 'METAAPI_ACCOUNT_ID')}")
        if env_account:
            st.caption(f"env fallback · {mask(env_account)}")

    with st.sidebar.expander("🧠 Sentinel Council AI keys", expanded=not st.session_state["cp_gemini_key"]):
        st.text_input("Gemini API key (Risk Auditor)", key="cp_gemini_key", type="password",
                      placeholder="leave empty to use secrets/.env")
        st.text_input("Groq API key (Scout)", key="cp_groq_key", type="password",
                      placeholder="leave empty to use secrets/.env")
        st.caption(f"Gemini: {_cred_source(st.session_state['cp_gemini_key'], 'GEMINI_API_KEY', 'GOOGLE_API_KEY')}"
                   f" · Groq: {_cred_source(st.session_state['cp_groq_key'], 'GROQ_API_KEY')}")

    symbol = st.sidebar.selectbox("Pair", PAIRS, index=PAIRS.index(DEFAULT_SYMBOL))
    timeframe = st.sidebar.selectbox("Timeframe", list(TIMEFRAMES.keys()),
                                     index=list(TIMEFRAMES.keys()).index(DEFAULT_TIMEFRAME))
    lot_choice = st.sidebar.selectbox("Lot sizing", ["Auto (ATR-scaled)", "0.01 (micro)", "0.02 (max)"])
    lot_preference = {"Auto (ATR-scaled)": None, "0.01 (micro)": 0.01, "0.02 (max)": 0.02}[lot_choice]
    auto_refresh = st.sidebar.toggle(f"Auto-refresh ({REFRESH_SECONDS}s)", value=True)
    offline_toggle = st.sidebar.toggle("Offline demo data", value=False)

    st.sidebar.divider()
    st.sidebar.caption(
        f"Account ${ACCOUNT_SIZE_USD:,.0f} · 1R ${RISK_PER_TRADE_USD:.0f} · "
        f"TP ${TAKE_PROFIT_USD:.0f} (1:{TARGET_RRR:.0f})"
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "lot_preference": lot_preference,
        "auto_refresh": auto_refresh,
        "offline": offline_toggle,
    }


def _render_guardrail(daily_pnl: float, state: str) -> None:
    import streamlit as st

    st.subheader("🛡️ Daily PnL Tracker & Guardrails")
    cols = st.columns([1, 2])
    with cols[0]:
        st.metric("Today's realized P&L", f"${daily_pnl:+.2f}",
                  delta=f"{(daily_pnl / ACCOUNT_SIZE_USD) * 100:+.2f}% of account")
        badge = {
            "ACTIVE": "🟢 ACTIVE - within guardrails",
            "LOCK": "🔒 LOCK-PROFIT - daily ceiling reached",
            "KILL": "🛑 KILL-SWITCH - daily loss limit hit",
        }[state]
        (st.success if state == "LOCK" else st.error if state == "KILL" else st.info)(badge)
    with cols[1]:
        prog = day_progress(daily_pnl)
        st.caption(f"Distance to +${DAILY_PROFIT_CEILING_USD:.0f} ceiling")
        st.progress(prog["to_ceiling"])
        st.caption(f"Distance to -${abs(DAILY_LOSS_KILL_USD):.0f} kill-switch "
                   f"(prop-firm limit -$125)")
        st.progress(prog["to_kill"])

    if state == "LOCK":
        st.success(f"🔒 Lock-profit: +${DAILY_PROFIT_CEILING_USD:.0f} target reached. "
                   "Bank the day - stop opening new positions.")
    elif state == "KILL":
        st.error(f"🛑 Kill-switch: -${abs(DAILY_LOSS_KILL_USD):.0f} reached. Flat now, "
                 "no new trades until tomorrow.")
    else:
        st.caption(
            f"Risk budget left today: ${daily_pnl - DAILY_LOSS_KILL_USD:,.2f} above the kill-switch "
            f"· ${DAILY_PROFIT_CEILING_USD - daily_pnl:,.2f} below the ceiling."
        )


def _render_market_intelligence(frame: Any, quote: Dict[str, Any], book: Dict[str, Any],
                                offline: bool, digits: int = 5) -> None:
    import streamlit as st

    st.subheader("📊 Market Intelligence")
    if frame is None or frame.empty:
        st.warning("No market data yet.")
        return

    last = frame.iloc[-1]
    tag = "offline demo" if offline else "MetaApi live"
    st.caption(f"{tag} · {len(frame)} candles · last {pd_timestamp(last.get('time'))}")

    ohlc = st.columns(5)
    ohlc[0].metric("Open", f"{float(last['open']):.{digits}f}")
    ohlc[1].metric("High", f"{float(last['high']):.{digits}f}")
    ohlc[2].metric("Low", f"{float(last['low']):.{digits}f}")
    ohlc[3].metric("Close", f"{float(last['close']):.{digits}f}")
    ohlc[4].metric("Volume", f"{float(last.get('volume', 0.0)):,.0f}")

    ind = st.columns(4)
    ind[0].metric(f"EMA{EMA_FAST}", f"{float(last[f'ema{EMA_FAST}']):.{digits}f}")
    ind[1].metric(f"EMA{EMA_SLOW}", f"{float(last[f'ema{EMA_SLOW}']):.{digits}f}")
    trend = "bullish stack" if float(last[f"ema{EMA_FAST}"]) >= float(last[f"ema{EMA_SLOW}"]) else "bearish stack"
    ind[2].metric(f"RSI({RSI_PERIOD})", f"{float(last[f'rsi{RSI_PERIOD}']):.1f}", trend)
    ind[3].metric("ATR(14)", f"{float(last['atr14']):.{digits}f}")
    st.caption(f"Bid {quote.get('bid')} · Ask {quote.get('ask')} · Spread {quote.get('spread')}")

    walls = bid_ask_wall(book)
    wall_cols = st.columns(2)
    with wall_cols[0]:
        bw = walls["bid_wall"]
        st.metric("🧱 Bid wall (largest size)", f"{bw['price']:.{digits}f}" if bw else "-",
                  f"size {bw['size']:,.2f}" if bw else None)
    with wall_cols[1]:
        aw = walls["ask_wall"]
        st.metric("🧱 Ask wall (largest size)", f"{aw['price']:.{digits}f}" if aw else "-",
                  f"size {aw['size']:,.2f}" if aw else None)


def pd_timestamp(value: Any) -> str:
    try:
        import pandas as pd

        ts = pd.to_datetime(value, utc=True, errors="coerce")
        return "-" if ts is pd.NaT or ts is None else ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def _render_chart(frame: Any, symbol: str, setup: Optional[SignalSetup]) -> None:
    import streamlit as st

    if frame is None or frame.empty:
        return
    try:
        import pandas as pd
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        st.line_chart(frame.set_index("time")["close"])
        return

    df = frame.copy()
    x = pd.to_datetime(df["time"], utc=True, errors="coerce")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28],
                        vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(x=x, open=df["open"], high=df["high"], low=df["low"],
                                 close=df["close"], name=symbol,
                                 increasing_line_color="#26a69a",
                                 decreasing_line_color="#ef5350"), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df[f"ema{EMA_FAST}"], name=f"EMA{EMA_FAST}",
                             line=dict(color="#42a5f5", width=1.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df[f"ema{EMA_SLOW}"], name=f"EMA{EMA_SLOW}",
                             line=dict(color="#ffb300", width=1.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df[f"rsi{RSI_PERIOD}"], name=f"RSI{RSI_PERIOD}",
                             line=dict(color="#ab47bc", width=1.4)), row=2, col=1)
    fig.add_hline(y=70, line=dict(color="#787b86", width=1, dash="dot"), row=2, col=1)
    fig.add_hline(y=30, line=dict(color="#787b86", width=1, dash="dot"), row=2, col=1)

    if setup is not None and setup.armed:
        for level, label, color in ((setup.entry, "Entry", "#ffffff"),
                                    (setup.stop_loss, "SL", "#ef5350"),
                                    (setup.take_profit, "TP", "#26a69a")):
            fig.add_hline(y=level, line=dict(color=color, width=1, dash="dash"),
                          annotation_text=f"{label} {level:.{setup.digits}f}",
                          annotation_position="right", row=1, col=1)

    fig.update_yaxes(range=[0, 100], row=2, col=1)
    fig.update_layout(template="plotly_dark", height=520, margin=dict(l=10, r=10, t=30, b=10),
                      uirevision="copilot", legend=dict(orientation="h", y=1.02, x=0),
                      xaxis_rangeslider_visible=False, hovermode="x unified", dragmode="pan",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)")
    st.plotly_chart(fig, use_container_width=True)


def _render_signal_card(
    setup: Optional[SignalSetup],
    daily_pnl: float,
    guard_state: str,
    council_verdict: Optional[CouncilVerdict],
    stale: bool,
) -> None:
    import streamlit as st

    st.subheader("🎯 AI Signal Card")
    if setup is None:
        st.info("Waiting for market data to build a setup.")
        return

    with st.container(border=True):
        if guard_state == "KILL":
            st.error("🛑 KILL-SWITCH ACTIVE - signal suppressed. Flat and safe until tomorrow.")
            return
        if guard_state == "LOCK":
            st.success("🔒 LOCK-PROFIT reached - no new entries. This is a review-only card.")

        if not setup.armed:
            st.warning("NEUTRAL - no trend/momentum alignment. Stand down; no order to place.")

        color = VERDICT_COLORS.get(setup.verdict.lower(), VERDICT_COLORS["neutral"])
        head = st.columns([2, 2, 2, 2])
        head[0].metric("Pair", f"{setup.symbol} · {setup.timeframe}")
        head[1].markdown(
            f"<div style='padding-top:6px'><span style='background:{color};color:#fff;"
            f"padding:6px 14px;border-radius:8px;font-weight:700;font-size:1.05rem'>"
            f"{setup.verdict}</span></div>",
            unsafe_allow_html=True,
        )
        head[2].metric("Recommended lot", f"{setup.lot:.2f}")
        head[3].metric("RRR score", f"1 : {setup.rrr:.1f}")

        body = st.columns(4)
        body[0].metric("Entry", f"{setup.entry:.{setup.digits}f}")
        body[1].metric("Stop loss", f"{setup.stop_loss:.{setup.digits}f}", f"-${setup.risk_usd:.0f} (1R)")
        body[2].metric("Take profit", f"{setup.take_profit:.{setup.digits}f}", f"+${setup.reward_usd:.0f} (3R)")
        body[3].metric("Risk / Reward", f"${setup.risk_usd:.0f} / ${setup.reward_usd:.0f}")

        st.markdown("**Deterministic checks**")
        st.markdown(
            f"- RRR floor ≥ 1:{MIN_RRR:.0f}: **{'PASS' if setup.rrr >= MIN_RRR else 'FAIL'}**\n"
            f"- Lot within 0.01-0.02: **{'PASS' if MIN_LOT <= setup.lot <= MAX_LOT else 'FAIL'}**\n"
            f"- Daily kill-switch headroom: **${daily_pnl - DAILY_LOSS_KILL_USD:,.2f}**"
        )
        for note in setup.notes:
            st.caption(f"• {note}")

        st.divider()
        st.markdown("**🧠 Sentinel Council - Risk Auditor notes**")
        if council_verdict is None:
            st.caption("Not consulted yet. Press **Consult Sentinel Council** below.")
        else:
            approved = council_verdict.approved
            (st.success if approved else st.error)(
                f"{'✅ APPROVED' if approved else '⛔ REJECTED'} · "
                f"{council_verdict.summary or 'no summary'}"
            )
            st.caption(
                f"verdict={council_verdict.verdict} · confidence={council_verdict.confidence:.2f} · "
                f"scout={council_verdict.scout_model_used or 'offline'} · "
                f"auditor={council_verdict.auditor_model_used or 'offline'}"
                + (" · ⚠ FALLBACK" if council_verdict.fallback_used else "")
                + (" · degraded" if council_verdict.degraded else "")
            )
            if council_verdict.notes:
                st.markdown(f"> {council_verdict.notes}")
            for message in council_verdict.messages:
                st.caption(f"– {message}")
            if stale:
                st.warning("⚠ Setup changed since this consultation - re-run the council.")


def _render_dashboard() -> None:
    import streamlit as st

    st.set_page_config(page_title="The5ers AI Co-Pilot", page_icon="🧭", layout="wide")
    st.title("🧭 The5ers AI Co-Pilot · $2,500 High Stakes")
    st.caption("Manual-execution signal generator & risk auditor · MetaApi read-only feed · "
               "Sentinel Council (Groq Scout + Gemini Risk Auditor). **No auto-trading.**")

    opts = _render_sidebar()
    creds = resolve_credentials()

    feed = get_feed()
    offline = bool(opts["offline"])
    feed.configure(token=creds["token"], account_id=creds["account_id"], offline=offline)
    council = get_council(creds)

    st.session_state.setdefault("cp_daily_pnl", 0.0)

    # ---- sidebar: daily PnL tracker (manual co-pilot bookkeeping) -------- #
    # The log buttons cannot touch the number_input's key directly (Streamlit
    # forbids mutating a widget key after it is instantiated), so they queue a
    # delta that is applied here, *before* the widget is (re)created.
    pending = float(st.session_state.pop("cp_pnl_pending", 0.0) or 0.0)
    if pending:
        st.session_state["cp_daily_pnl"] = round(
            float(st.session_state.get("cp_daily_pnl", 0.0)) + pending, 2
        )
    with st.sidebar.expander("📓 Daily P&L tracker", expanded=True):
        st.number_input("Today's realized P&L (USD)", step=1.0, format="%.2f", key="cp_daily_pnl")
        bcols = st.columns(2)
        if bcols[0].button("＋ TP hit (+$30)", use_container_width=True):
            st.session_state["cp_pnl_pending"] = TAKE_PROFIT_USD
            log_event(f"logged TP hit (+${TAKE_PROFIT_USD:.0f})")
            st.rerun()
        if bcols[1].button("－ SL hit (-$10)", use_container_width=True):
            st.session_state["cp_pnl_pending"] = -RISK_PER_TRADE_USD
            log_event(f"logged SL hit (-${RISK_PER_TRADE_USD:.0f})")
            st.rerun()
        if st.button("↺ Reset day", use_container_width=True):
            st.session_state["cp_pnl_pending"] = -float(st.session_state.get("cp_daily_pnl", 0.0))
            log_event("daily P&L reset")
            st.rerun()

    daily_pnl = float(st.session_state["cp_daily_pnl"])
    guard_state = guardrail_state(daily_pnl)

    snapshot = feed.account_snapshot()
    if snapshot.get("balance"):
        st.caption(
            f"Account · balance ${snapshot['balance']:,.2f} · equity ${snapshot['equity']:,.2f} "
            f"{snapshot.get('currency', 'USD')}"
            + (" · offline demo" if snapshot.get("offline") else "")
        )

    _render_guardrail(daily_pnl, guard_state)
    if feed.last_error:
        st.warning(f"Feed warning: {feed.last_error}")

    # ---- live market block (native fragment refresh, Community-Cloud friendly) -- #
    @_fragment(REFRESH_SECONDS if opts["auto_refresh"] else None)
    def _live() -> None:
        frame = feed.fetch_frame(opts["symbol"], opts["timeframe"], CANDLES)
        quote = feed.quote(opts["symbol"])
        book = feed.orderbook(opts["symbol"])
        spec = feed.spec(opts["symbol"])
        setup = compute_signal(frame, opts["symbol"], opts["timeframe"], spec,
                               lot_preference=opts["lot_preference"])

        _render_market_intelligence(frame, quote, book, bool(frame.attrs.get("offline", offline)),
                                    digits=int(getattr(spec, "digits", 5)))
        _render_chart(frame, opts["symbol"], setup)

        # ---- council consultation (quota-friendly: button-driven) --------- #
        stored = st.session_state.get("cp_council_verdict")
        stale = bool(stored and setup is not None and stored.get("sig") != setup.signature())
        verdict_obj = stored.get("verdict") if stored else None

        if st.button("🧠 Consult Sentinel Council", type="primary",
                     disabled=setup is None or guard_state == "KILL"):
            if setup is not None:
                with st.spinner("Scout (Groq) and Risk Auditor (Gemini) deliberating..."):
                    result = council.evaluate(setup.to_council_payload(daily_pnl))
                st.session_state["cp_council_verdict"] = {"sig": setup.signature(), "verdict": result}
                verdict_obj, stale = result, False
                log_event(
                    f"council consult -> {'APPROVED' if result.approved else 'REJECTED'} "
                    f"(scout={result.scout_model_used or '-'}, auditor={result.auditor_model_used or '-'}"
                    + (", FALLBACK" if result.fallback_used else "") + ")"
                )

        _render_signal_card(setup, daily_pnl, guard_state, verdict_obj, stale)

        council_status = council.status()
        st.caption(
            f"Council · Scout {'on' if council_status['scout'] else 'off'} "
            f"({council_status['scout_models'][0]}) · Risk Auditor "
            f"{'on' if council_status['auditor'] else 'off'} ({council_status['auditor_models'][0]}) "
            f"· timeout {council_status['timeout']:.0f}s"
        )

    _live()

    with st.expander("📜 Activity log", expanded=False):
        entries = st.session_state.get("cp_log") or []
        st.code("\n".join(entries[-60:]) if entries else "No activity yet.", language="text")


def run_once() -> int:
    """Headless smoke pass: offline feed -> signal -> summary. Exit 0 on success."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    feed = MetaApiFeed()
    feed.configure(offline=True)
    frame = feed.fetch_frame(DEFAULT_SYMBOL, DEFAULT_TIMEFRAME, CANDLES)
    spec = feed.spec(DEFAULT_SYMBOL)
    setup = compute_signal(frame, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME, spec)
    if setup is None:
        print("FAILED: no signal produced")
        return 1
    print(f"rows={len(frame)} offline={feed.offline}")
    print(f"{setup.symbol} {setup.timeframe} {setup.verdict} entry={setup.entry} "
          f"sl={setup.stop_loss} tp={setup.take_profit} lot={setup.lot} rrr=1:{setup.rrr:.1f}")
    print(f"guardrail(daily_pnl=0)={guardrail_state(0.0)} "
          f"guardrail(+40)={guardrail_state(40.0)} guardrail(-50)={guardrail_state(-50.0)}")
    feed.close()
    print("OK")
    return 0


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _render_dashboard()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The5ers AI Co-Pilot dashboard (manual execution).")
    parser.add_argument("--once", action="store_true", help="run a single headless pass and exit")
    args, _unknown = parser.parse_known_args()
    if args.once:
        raise SystemExit(run_once())
    main()
