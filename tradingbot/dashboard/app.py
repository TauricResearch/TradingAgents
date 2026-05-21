"""
TradingAgents Auto-Trading Dashboard.

URL routing (via st.navigation):
  /         dashboard (default, requires auth)
  /login    login / register page (public)

Launch with:
    streamlit run tradingbot/dashboard/app.py

The dashboard reads from the same SQLite database written by AutoTrader,
so it works whether the bot is running or stopped.

Environment variables (same as run_bot.py / tradingbot/config.py):
    TRADINGBOT_BROKER       mock | alpaca
    ALPACA_API_KEY / ALPACA_API_SECRET
    TRADINGBOT_DB_PATH      path to SQLite DB
    TRADINGBOT_USERS_DB     path to users SQLite DB
    TRADINGBOT_SESSION_SECRET / TRADINGBOT_SESSION_SECRET_PATH
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Make sure the project root is on the path so all imports resolve.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from tradingbot.auth import clear_session, restore_session, save_session
from tradingbot.dashboard.auth_app import get_auth_service, render_auth_flow
from tradingbot.dashboard.i18n import language_selector, t

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
      /* st.navigation's auto-injected page list — we drive routing ourselves */
      [data-testid="stSidebarNav"] {display: none !important;}
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
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    return TradingAgentsGraph(config=DEFAULT_CONFIG)


def _get_config():
    from tradingbot.config import TRADINGBOT_CONFIG
    return TRADINGBOT_CONFIG


# ── Sidebar ────────────────────────────────────────────────────────────

PAGE_KEYS = ["nav.portfolio", "nav.performance", "nav.trades", "nav.signals", "nav.risk"]


def render_sidebar(config):
    language_selector()
    st.sidebar.markdown("---")

    username = st.session_state.get("auth_user")
    if username:
        st.sidebar.markdown(t("auth.sidebar.signed_in_as", name=username))
        if st.sidebar.button(t("auth.sidebar.logout"), key="logout_btn"):
            # We can't clear the cookie + redirect from here directly — the
            # iframe that would write `document.cookie = ""` is queued via
            # st.components.v1.html, but st.switch_page discards the queue,
            # and a same-render st.stop() leaves the user staring at the
            # dashboard. Instead: pop the in-memory session, set a one-shot
            # flag, and switch to /login. The login page handles the cookie
            # clear in a render that actually completes normally.
            for k in ("auth_user", "auth_mode", "_sidebar_opened"):
                st.session_state.pop(k, None)
            st.session_state["_just_logged_out"] = True
            st.switch_page(_LOGIN_PAGE)
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
        from tradingbot.portfolio.database import PortfolioDatabase  # noqa: F401
        from tradingbot.portfolio.manager import PortfolioManager
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


# ── Page: /login ───────────────────────────────────────────────────────

def _login_page():
    # One-shot logout flag: came from /'s logout button. Clear the cookie
    # here (this page completes a normal render, so the iframe gets flushed)
    # and skip the auto-restore step that would otherwise re-log them in.
    if st.session_state.pop("_just_logged_out", False):
        clear_session()
    else:
        # Refresh-friendly auth restore from signed cookie.
        if restore_session():
            st.switch_page(_DASHBOARD_PAGE)

    # Login page: hide sidebar entirely AND constrain the main column to
    # a narrow, centred card so it doesn't inherit the dashboard's wide layout.
    st.markdown(
        """
        <style>
          html, body, #root, [data-testid="stAppViewContainer"] {
            height: 100vh !important;
            min-height: 100vh !important;
          }
          [data-testid="stSidebar"] {display: none !important;}
          [data-testid="collapsedControl"] {display: none !important;}
          section.main,
          [data-testid="stMain"] {
            min-height: 100vh !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            align-items: center !important;
          }
          [data-testid="stMainBlockContainer"],
          section.main > div.block-container,
          .block-container {
            max-width: 720px !important;
            width: 100% !important;
            margin-left: auto !important;
            margin-right: auto !important;
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Render the auth flow. On success, auth_app sets st.session_state["auth_user"]
    # then reruns; we catch that on the next pass and switch_page to /.
    # The dashboard page is responsible for issuing the persistence cookie —
    # st.rerun / st.switch_page discard any pending st.markdown JS, so we
    # only inject cookie-writes from a page that finishes a normal render.
    render_auth_flow(get_auth_service())

    if st.session_state.get("auth_user"):
        st.switch_page(_DASHBOARD_PAGE)


# ── Page: / (dashboard) ────────────────────────────────────────────────

def _dashboard_page():
    # Refresh-friendly auth restore from signed cookie.
    username = restore_session()
    if not username:
        st.switch_page(_LOGIN_PAGE)

    # Refresh the signed cookie every render so the logged-in session keeps
    # rolling. Doing it here (a page that completes normally) is the only
    # reliable place — st.rerun / st.switch_page would discard the JS write.
    save_session(username)

    # On the first dashboard render of a session, programmatically open the
    # sidebar — `initial_sidebar_state="expanded"` only applies on the very
    # first page load, and the user often lands here after a /login → /
    # navigation where Streamlit has remembered the previous collapsed state.
    # Note: <script> inside st.markdown is stripped; components.html runs in
    # an iframe whose JS *does* execute and can touch window.parent.
    if not st.session_state.get("_sidebar_opened"):
        st.session_state["_sidebar_opened"] = True
        import streamlit.components.v1 as components
        components.html(
            """
            <script>
              (function () {
                const tryOpen = (tries) => {
                  const doc = window.parent.document;
                  // If sidebar already has measurable width, it's open.
                  const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                  if (sidebar && sidebar.getBoundingClientRect().width > 100) return;
                  const btn = doc.querySelector('[data-testid="collapsedControl"] button')
                           || doc.querySelector('[data-testid="stSidebarCollapseButton"] button');
                  if (btn) { btn.click(); return; }
                  if (tries > 0) setTimeout(() => tryOpen(tries - 1), 100);
                };
                tryOpen(20);
              })();
            </script>
            """,
            height=0,
        )

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


# ── Routing ────────────────────────────────────────────────────────────

_DASHBOARD_PAGE = st.Page(
    _dashboard_page,
    url_path="",
    title=t("app.page_title"),
    default=True,
)
_LOGIN_PAGE = st.Page(
    _login_page,
    url_path="login",
    title=t("auth.app.title"),
)


def main():
    nav = st.navigation([_DASHBOARD_PAGE, _LOGIN_PAGE], position="hidden")
    nav.run()


main()
