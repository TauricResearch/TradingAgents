"""
TradingAgents Auto-Trading Dashboard

Launch with:
    streamlit run tradingbot/dashboard/app.py

The dashboard reads from the same SQLite database written by AutoTrader,
so it works whether the bot is running or stopped.

Environment variables (same as run_bot.py / tradingbot/config.py):
    TRADINGBOT_BROKER       mock | alpaca
    ALPACA_API_KEY / ALPACA_API_SECRET
    TRADINGBOT_DB_PATH      path to SQLite DB
"""

import os
import sys
import logging
from pathlib import Path
from datetime import date, datetime

# Make sure the project root is on the path so all imports resolve.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from tradingbot.dashboard.i18n import t, language_selector

logging.basicConfig(level=logging.WARNING)

# ── Page config (must be first Streamlit call) ─────────────────────────
st.set_page_config(
    page_title=t("app.page_title"),
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide Streamlit's built-in chrome (⋮ menu, top header bar, "Made with Streamlit" footer,
# Deploy button, and the running-status indicator) so all visible UI is under our control.
st.markdown(
    """
    <style>
      #MainMenu {visibility: hidden !important;}
      header {visibility: hidden !important; height: 0 !important;}
      footer {visibility: hidden !important;}
      [data-testid="stToolbar"] {visibility: hidden !important; height: 0 !important; position: fixed !important;}
      [data-testid="stStatusWidget"] {visibility: hidden !important;}
      [data-testid="stDecoration"] {visibility: hidden !important;}
      [data-testid="stMainMenu"] {visibility: hidden !important;}
      [data-testid="stHeader"] {visibility: hidden !important; height: 0 !important;}
      .stDeployButton {display: none !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Cached singletons ──────────────────────────────────────────────────

@st.cache_resource
def _get_broker():
    from tradingbot.config import TRADINGBOT_CONFIG as cfg
    broker_type = cfg.get("broker", "mock").lower()
    if broker_type == "alpaca":
        from tradingbot.broker.alpaca import AlpacaBroker
        return AlpacaBroker(
            api_key=cfg["alpaca_api_key"],
            api_secret=cfg["alpaca_api_secret"],
            paper=cfg.get("paper_trading", True),
        )
    from tradingbot.broker.mock import MockBroker
    return MockBroker(starting_cash=100_000.0)


@st.cache_resource
def _get_db():
    from tradingbot.config import TRADINGBOT_CONFIG as cfg
    from tradingbot.portfolio.database import PortfolioDatabase
    return PortfolioDatabase(cfg["db_path"])


@st.cache_resource
def _get_portfolio_manager():
    from tradingbot.portfolio.manager import PortfolioManager
    return PortfolioManager(_get_broker(), _get_db())


@st.cache_resource
def _get_trading_graph():
    """Load TradingAgentsGraph — expensive, cached for the session."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    return TradingAgentsGraph(config=DEFAULT_CONFIG)


def _get_config():
    from tradingbot.config import TRADINGBOT_CONFIG
    return TRADINGBOT_CONFIG


# ── Sidebar ────────────────────────────────────────────────────────────

PAGE_KEYS = ["nav.portfolio", "nav.performance", "nav.trades", "nav.signals", "nav.risk"]


def render_sidebar(config):
    language_selector()
    st.sidebar.markdown("---")

    st.sidebar.title(t("app.sidebar.title"))
    st.sidebar.caption(t("app.sidebar.last_refresh", time=datetime.now().strftime("%H:%M:%S")))

    broker_type = config.get("broker", "mock")
    paper = config.get("paper_trading", True)
    mode_word = t("app.sidebar.mode_paper") if paper else t("app.sidebar.mode_live")
    mode_label = f"{mode_word} — {broker_type.upper()}"
    colour = "#4CAF50" if paper else "#F44336"
    st.sidebar.markdown(
        f'<div style="background:{colour};color:white;padding:6px 10px;border-radius:6px;'
        f'font-weight:bold;text-align:center">{mode_label}</div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("---")
    page_key = st.sidebar.radio(
        t("app.sidebar.navigate"),
        PAGE_KEYS,
        index=0,
        format_func=lambda k: t(k),
    )

    st.sidebar.markdown("---")
    watchlist = config.get("watchlist", [])
    st.sidebar.markdown(t("app.sidebar.watchlist"))
    st.sidebar.code(", ".join(watchlist))

    st.sidebar.markdown("---")
    if st.sidebar.button(t("app.sidebar.refresh")):
        st.cache_resource.clear()
        st.rerun()

    return page_key


# ── Quick trade panel (sidebar) ────────────────────────────────────────

def render_quick_trade(config, broker, db):
    st.sidebar.markdown("---")
    st.sidebar.markdown(t("qt.header"))
    ticker_in = st.sidebar.text_input(t("qt.ticker"), key="qt_ticker").upper().strip()
    side_options = ["BUY", "SELL"]
    side_in = st.sidebar.selectbox(
        t("qt.side"),
        side_options,
        key="qt_side",
        format_func=lambda s: t("qt.side.buy") if s == "BUY" else t("qt.side.sell"),
    )
    qty_in = st.sidebar.number_input(
        t("qt.qty"), min_value=0.001, value=1.0, step=0.1, key="qt_qty"
    )

    if st.sidebar.button(t("qt.submit"), key="qt_submit"):
        if not ticker_in:
            st.sidebar.error(t("qt.err.no_ticker"))
            return
        from tradingbot.broker.base import OrderSide, OrderType
        from tradingbot.portfolio.manager import PortfolioManager
        from tradingbot.portfolio.database import PortfolioDatabase
        side = OrderSide.BUY if side_in == "BUY" else OrderSide.SELL
        try:
            order = broker.submit_order(ticker_in, qty_in, side, OrderType.MARKET)
            pm = PortfolioManager(broker, db)
            pm.record_trade(order, signal="MANUAL", agent_reasoning=t("qt.reasoning"))
            st.sidebar.success(
                t("qt.success", qty=f"{qty_in:.4f}", price=f"{order.filled_avg_price:.2f}")
            )
        except Exception as exc:
            st.sidebar.error(str(exc))


# ── Main ───────────────────────────────────────────────────────────────

def main():
    config = _get_config()
    page = render_sidebar(config)
    render_quick_trade(config, _get_broker(), _get_db())

    st.title(t("app.title"))

    broker = _get_broker()
    db = _get_db()
    pm = _get_portfolio_manager()

    if page == "nav.portfolio":
        from tradingbot.dashboard.components import portfolio_view
        portfolio_view.render(broker, pm)

    elif page == "nav.performance":
        from tradingbot.dashboard.components import performance_view
        performance_view.render(pm)

    elif page == "nav.trades":
        from tradingbot.dashboard.components import trades_view
        trades_view.render(pm, config)

    elif page == "nav.signals":
        from tradingbot.dashboard.components import signals_view
        graph = _get_trading_graph()
        signals_view.render(graph, config)

    elif page == "nav.risk":
        from tradingbot.dashboard.components import risk_view
        risk_view.render(broker, db, config)


if __name__ == "__main__":
    main()
