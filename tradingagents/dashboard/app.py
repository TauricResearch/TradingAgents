"""Streamlit dashboard entrypoint.

Run via: streamlit run tradingagents/dashboard/app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect as iic_connect
from tradingagents.dashboard.panels.briefs import fetch_recent_briefs, fetch_brief_thread


st.set_page_config(page_title="IIC-FORGE Dashboard", layout="wide")


@st.cache_resource
def _conn():
    return iic_connect(DEFAULT_CONFIG["iic_db_path"])


st.title("IIC-FORGE")

tab_briefs, tab_costs, tab_queue, tab_actions = st.tabs(
    ["Briefs", "Costs", "Queue", "Actions"]
)

with tab_briefs:
    st.header("Recent briefs")
    rows = fetch_recent_briefs(_conn(), limit=50)
    if not rows:
        st.info("No briefs yet.")
    else:
        st.dataframe(rows, use_container_width=True)
        selected = st.selectbox(
            "View brief thread",
            options=[""] + [r["brief_id"] for r in rows],
        )
        if selected:
            thread = fetch_brief_thread(_conn(), brief_id=selected)
            for b in thread:
                st.subheader(f"{b['brief_id']} (depth={b['refine_depth']})")
                body_path = Path(DEFAULT_CONFIG["iic_data_dir"]) / b["content_path"]
                if body_path.exists():
                    st.markdown(body_path.read_text())

with tab_costs:
    st.header("Costs (placeholder — see Task 17)")

with tab_queue:
    st.header("Queue (placeholder — see Task 17)")

with tab_actions:
    st.header("Actions (placeholder — see Task 18)")
