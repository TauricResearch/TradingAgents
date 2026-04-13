"""
Hypotheses dashboard page — tracks active and concluded experiments.

Reads docs/iterations/hypotheses/active.json and the concluded/ directory.
No external API calls; all data is file-based.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from tradingagents.ui.theme import page_header

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_ACTIVE_JSON = _REPO_ROOT / "docs/iterations/hypotheses/active.json"
_CONCLUDED_DIR = _REPO_ROOT / "docs/iterations/hypotheses/concluded"


def load_active_hypotheses(active_path: str = str(_ACTIVE_JSON)) -> List[Dict[str, Any]]:
    """Load all hypotheses from active.json. Returns [] if file missing."""
    path = Path(active_path)
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("hypotheses", [])
    except Exception:
        return []


def load_concluded_hypotheses(concluded_dir: str = str(_CONCLUDED_DIR)) -> List[Dict[str, Any]]:
    """
    Load concluded hypothesis metadata by parsing markdown files in concluded/.
    Extracts: filename, title, scanner, period, outcome.
    """
    dir_path = Path(concluded_dir)
    if not dir_path.exists():
        return []
    results = []
    for md_file in sorted(dir_path.glob("*.md"), reverse=True):
        if md_file.name == ".gitkeep":
            continue
        try:
            text = md_file.read_text()
            title = _extract_md_field(text, r"^# Hypothesis: (.+)$")
            scanner = _extract_md_field(text, r"^\*\*Scanner:\*\* (.+)$")
            period = _extract_md_field(text, r"^\*\*Period:\*\* (.+)$")
            outcome = _extract_md_field(text, r"^\*\*Outcome:\*\* (.+)$")
            results.append(
                {
                    "filename": md_file.name,
                    "title": title or md_file.stem,
                    "scanner": scanner or "—",
                    "period": period or "—",
                    "outcome": outcome or "—",
                }
            )
        except Exception:
            continue
    return results


def _extract_md_field(text: str, pattern: str) -> str:
    """Extract a field value from a markdown line using regex."""
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def days_until_ready(hyp: Dict[str, Any]) -> int:
    """Return number of days remaining before hypothesis can conclude (min 0)."""
    return max(0, hyp.get("min_days", 14) - hyp.get("days_elapsed", 0))


def render() -> None:
    """Render the hypotheses tracking page."""
    st.markdown(
        page_header("Hypotheses", "Active experiments & concluded findings"),
        unsafe_allow_html=True,
    )

    hypotheses = load_active_hypotheses()
    concluded = load_concluded_hypotheses()

    if not hypotheses and not concluded:
        st.info(
            'No hypotheses yet. Run `/backtest-hypothesis "<description>"` to start an experiment.'
        )
        return

    running = [h for h in hypotheses if h["status"] == "running"]
    pending = [h for h in hypotheses if h["status"] == "pending"]

    st.markdown(
        f'<div class="section-title">Active Experiments '
        f'<span class="accent">// {len(running)} running, {len(pending)} pending</span></div>',
        unsafe_allow_html=True,
    )

    if running or pending:
        import pandas as pd

        active_rows = []
        for h in sorted(running + pending, key=lambda x: -x.get("priority", 0)):
            days_left = days_until_ready(h)
            ready_str = "concluding soon" if days_left == 0 else f"{days_left}d left"
            active_rows.append(
                {
                    "ID": h["id"],
                    "Title": h.get("title", "—"),
                    "Scanner": h.get("scanner", "—"),
                    "Status": h["status"],
                    "Progress": f"{h.get('days_elapsed', 0)}/{h.get('min_days', 14)}d",
                    "Picks": len(h.get("picks_log", [])),
                    "Ready": ready_str,
                    "Priority": h.get("priority", "—"),
                }
            )
        df = pd.DataFrame(active_rows)
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "ID": st.column_config.TextColumn(width="medium"),
                "Title": st.column_config.TextColumn(width="large"),
                "Scanner": st.column_config.TextColumn(width="medium"),
                "Status": st.column_config.TextColumn(width="small"),
                "Progress": st.column_config.TextColumn(width="small"),
                "Picks": st.column_config.NumberColumn(format="%d", width="small"),
                "Ready": st.column_config.TextColumn(width="medium"),
                "Priority": st.column_config.NumberColumn(format="%d/9", width="small"),
            },
        )
    else:
        st.info("No active experiments.")

    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

    st.markdown(
        f'<div class="section-title">Concluded Experiments '
        f'<span class="accent">// {len(concluded)} total</span></div>',
        unsafe_allow_html=True,
    )

    if concluded:
        import pandas as pd

        concluded_rows = []
        for c in concluded:
            outcome = c["outcome"]
            emoji = "✅" if "accepted" in outcome else "❌"
            concluded_rows.append(
                {
                    "Date": c["filename"][:10],
                    "Title": c["title"],
                    "Scanner": c["scanner"],
                    "Period": c["period"],
                    "Outcome": emoji,
                }
            )
        cdf = pd.DataFrame(concluded_rows)
        st.dataframe(
            cdf,
            width="stretch",
            hide_index=True,
            column_config={
                "Date": st.column_config.TextColumn(width="small"),
                "Title": st.column_config.TextColumn(width="large"),
                "Scanner": st.column_config.TextColumn(width="medium"),
                "Period": st.column_config.TextColumn(width="medium"),
                "Outcome": st.column_config.TextColumn(width="small"),
            },
        )
    else:
        st.info("No concluded experiments yet.")
