"""Streamlit landing page for TradingAgents.

Launch with:
    streamlit run gui/app.py

Or via the installed console script (after `pip install .`):
    tradingagents-gui
"""

from __future__ import annotations

import streamlit as st

from gui import storage
from gui.config import GUI_CONFIG_PATH, load as load_config
from gui.log_browser import discover_logs, memory_log_path

st.set_page_config(
    page_title="TradingAgents",
    page_icon=":material/finance:",
    layout="wide",
    initial_sidebar_state="expanded",
)

storage.init_db()

st.title("TradingAgents")
st.caption("Multi-agent LLM analysis for a single ticker on a single date. Decisions are recommendations, not orders.")

cfg = load_config()
key_count = sum(1 for v in cfg.get("api_keys", {}).values() if v)
runs = storage.list_runs(limit=5)
notes = storage.list_notes()
discovered = discover_logs()

col1, col2, col3, col4 = st.columns(4)
col1.metric("API keys configured", key_count)
col2.metric("Runs (DB)", len(storage.list_runs(limit=10_000)))
col3.metric("Logs on disk", len(discovered))
col4.metric("Notes", len(notes))

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Get started")
    st.markdown(
        "- **Run** — kick off a new analysis. Pick ticker, date, provider, model, depth.\n"
        "- **History** — every analysis run (whether launched from the GUI or the CLI) "
        "is indexed and the full debate transcript is browsable here.\n"
        "- **Notes** — markdown notes, optionally pinned to a ticker or a specific run.\n"
        "- **Memory** — view the rolling decision log with realised returns vs SPY.\n"
        "- **Settings** — API keys per provider and default run config."
    )

    st.subheader("Recent runs")
    if not runs:
        st.info("No runs recorded yet. Open **Run** in the sidebar to start one.")
    else:
        for r in runs:
            decision = r.get("decision") or "—"
            status = r.get("status")
            badge = {"done": ":green[done]", "running": ":blue[running]",
                     "error": ":red[error]"}.get(status, status)
            st.write(
                f"**{r['ticker']}** · {r['trade_date']} · "
                f"{r.get('provider')}/{r.get('deep_model')} · "
                f"decision **{decision}** · {badge}"
            )

with right:
    st.subheader("Where data lives")
    st.code(
        f"GUI config:    {GUI_CONFIG_PATH}\n"
        f"GUI database:  {storage.DB_PATH}\n"
        f"Memory log:    {memory_log_path()}\n"
        f"Run logs:      ~/.tradingagents/logs/<TICKER>/...\n"
        f"Cache:         ~/.tradingagents/cache/",
        language="text",
    )
    st.caption(
        "All paths can be overridden with env vars: TRADINGAGENTS_RESULTS_DIR, "
        "TRADINGAGENTS_CACHE_DIR, TRADINGAGENTS_MEMORY_LOG_PATH."
    )
