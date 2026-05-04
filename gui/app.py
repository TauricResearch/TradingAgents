"""Streamlit landing page for TradingAgents.

Launch with:
    streamlit run gui/app.py

Or via the installed console script (after `pip install .`):
    tradingagents-gui
"""

from __future__ import annotations

import sqlite3

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
all_runs = storage.list_runs(limit=10_000)
key_count = sum(1 for v in cfg.get("api_keys", {}).values() if v)
notes = storage.list_notes()
discovered = discover_logs()
errored = [r for r in all_runs if (r.get("status") or "") == "error"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("API keys configured", key_count)
col2.metric("Runs (DB)", len(all_runs), delta=f"{len(errored)} failed" if errored else None,
            delta_color="off" if not errored else "inverse")
col3.metric("Logs on disk", len(discovered))
col4.metric("Notes", len(notes))

st.divider()

# ---- Recent runs (left) + everything else (right) -----------------------
left, right = st.columns([3, 2])

_STATUS_BADGE = {
    "done":      ("✓",  "rgba(56, 161, 105, 0.18)", "#38a169"),
    "running":   ("•",  "rgba(49, 130, 206, 0.18)", "#3182ce"),
    "error":     ("!",  "rgba(229, 62, 62, 0.18)",  "#e53e3e"),
    "legacy":    ("·",  "rgba(160, 174, 192, 0.18)", "#a0aec0"),
}


def _badge_html(status: str) -> str:
    icon, bg, fg = _STATUS_BADGE.get(status, ("·", "rgba(160,174,192,0.18)", "#a0aec0"))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 8px;border-radius:10px;"
        f"font-size:11px;font-weight:600;'>{icon} {status}</span>"
    )


with left:
    st.subheader("Recent runs")
    if not all_runs:
        st.info("No runs recorded yet. Open **Run** in the sidebar to start one.")
    else:
        for r in all_runs[:8]:
            decision = r.get("decision") or "—"
            status = r.get("status") or "—"
            stats_bits = []
            if r.get("tokens_in") or r.get("tokens_out"):
                stats_bits.append(f"{(r.get('tokens_in') or 0):,}↑ / {(r.get('tokens_out') or 0):,}↓ tok")
            if r.get("started_at"):
                stats_bits.append(r["started_at"].replace("T", " ").rstrip("Z"))
            stats_line = " · ".join(stats_bits)
            line = (
                f"<div style='padding:6px 0;border-bottom:1px solid rgba(127,127,127,0.18);'>"
                f"<b>{r['ticker']}</b> · {r['trade_date']} · "
                f"{r.get('provider') or '—'}/{r.get('deep_model') or '—'} · "
                f"decision <b>{decision}</b> &nbsp; {_badge_html(status)}"
                f"<br><span style='color:#888;font-size:12px;'>{stats_line}</span>"
                f"</div>"
            )
            st.markdown(line, unsafe_allow_html=True)

        if errored:
            with st.expander(f"🧹 Clean up — {len(errored)} errored run(s)"):
                st.caption(
                    "Removes errored rows from the DB. On-disk transcripts (if any) are not touched."
                )
                if st.button("Delete errored DB rows", type="secondary"):
                    with sqlite3.connect(storage.DB_PATH) as c:
                        c.execute("DELETE FROM runs WHERE status='error'")
                        c.commit()
                    st.success(f"Deleted {len(errored)} row(s).")
                    st.rerun()

    st.subheader("Get started")
    st.markdown(
        "- **Run** — kick off a new analysis (ticker, date, provider, model, depth).\n"
        "- **History** — full debate transcripts, exports (md / HTML / PDF / JSON), and per-run chat.\n"
        "- **Notes** — markdown notes, optionally pinned to a ticker or run.\n"
        "- **Memory** — rolling decision log with realised returns vs SPY.\n"
        "- **Settings** — API keys per provider and default run config."
    )

with right:
    with st.expander("📁 Where data lives", expanded=False):
        st.code(
            f"GUI config:    {GUI_CONFIG_PATH}\n"
            f"GUI database:  {storage.DB_PATH}\n"
            f"Memory log:    {memory_log_path()}\n"
            f"Run logs:      ~/.tradingagents/logs/<TICKER>/...\n"
            f"Cache:         ~/.tradingagents/cache/\n"
            f"Exports:       ~/.tradingagents/exports/<TICKER>/...",
            language="text",
        )
        st.caption(
            "All paths can be overridden with env vars: TRADINGAGENTS_RESULTS_DIR, "
            "TRADINGAGENTS_CACHE_DIR, TRADINGAGENTS_MEMORY_LOG_PATH."
        )

    if key_count == 0:
        st.warning(
            "No API keys configured. Open **Settings** and add at least one provider key "
            "before starting a run.",
            icon="🔑",
        )
    elif not all_runs:
        st.info(
            "Ready to go. Open **Run** to start your first analysis.",
            icon="▶",
        )
