"""Memory page — render the rolling decision log.

The memory log is a markdown file the framework writes to and reads from
between runs. Pending entries are decisions whose holding window hasn't
closed yet; resolved entries have a realised return + reflection attached.
"""

from __future__ import annotations

import re

import streamlit as st

from gui.log_browser import memory_log_path, read_memory_log
from gui.md_utils import safe_md

st.set_page_config(page_title="Memory · TradingAgents", layout="wide")

st.title("Decision memory")

raw = read_memory_log()
if not raw:
    st.info(
        f"Memory log is empty or not yet created at:\n\n`{memory_log_path()}`\n\n"
        "It populates after your first run and resolves after the holding window closes."
    )
    st.stop()

# Try to parse entries. The format is append-only markdown with a known shape:
# ## TICKER on YYYY-MM-DD
# DECISION: ...
# REFLECTION: ... (or absent for pending)
entries = re.split(r"^##\s+", raw, flags=re.MULTILINE)
header = entries[0]
entries = ["## " + e for e in entries[1:]]

resolved, pending = [], []
for e in entries:
    if "REFLECTION:" in e:
        resolved.append(e)
    else:
        pending.append(e)

c1, c2 = st.columns(2)
c1.metric("Total entries", len(entries))
c2.metric("Resolved / Pending", f"{len(resolved)} / {len(pending)}")

view = st.radio("Show", ["All", "Resolved", "Pending"], horizontal=True, index=0)
shown = entries if view == "All" else (resolved if view == "Resolved" else pending)

st.markdown("---")
for e in shown:
    st.markdown(safe_md(e))
    st.markdown("---")

with st.expander("Show raw memory log file"):
    st.code(raw, language="markdown")
st.caption(f"Source: `{memory_log_path()}`")
