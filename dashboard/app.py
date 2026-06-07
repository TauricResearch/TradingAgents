from __future__ import annotations

from pathlib import Path

import streamlit as st


DISCLAIMER = (
    "Research and education only. Not investment advice. IndiaMarketAgents is not a "
    "SEBI-registered investment adviser or research analyst. Verify data with official filings."
)


def _report_root() -> Path:
    return Path("reports")


def _symbols(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _dates(root: Path, symbol: str) -> list[str]:
    base = root / symbol
    if not base.exists():
        return []
    return sorted((path.name for path in base.iterdir() if path.is_dir()), reverse=True)


def _read(path: Path) -> str:
    if not path.exists():
        return "UNAVAILABLE: This report section was not found."
    return path.read_text(encoding="utf-8", errors="replace")


st.set_page_config(page_title="IndiaMarketAgents", layout="wide")
st.title("IndiaMarketAgents")
st.warning(DISCLAIMER)

root = _report_root()
symbols = _symbols(root)
if not symbols:
    st.info("No saved reports found under reports/<SYMBOL>/<DATE>/.")
    st.stop()

symbol = st.sidebar.selectbox("Ticker", symbols)
dates = _dates(root, symbol)
if not dates:
    st.info("No dated report folders found for this ticker.")
    st.stop()

date = st.sidebar.selectbox("Date", dates)
base = root / symbol / date

summary_col, decision_col, quality_col = st.columns(3)
summary_col.metric("Ticker", symbol)
decision_col.metric("Date", date)
quality_col.metric("Scope", "India-only")

tabs = st.tabs(
    [
        "Complete",
        "Technical",
        "Fundamentals",
        "News/Filings",
        "Macro/Policy",
        "Flows",
        "Sentiment",
        "Risk/Compliance",
        "Sources",
    ]
)

files = [
    "complete_report.md",
    "1_market_technical.md",
    "2_fundamentals.md",
    "3_news_filings.md",
    "4_macro_policy.md",
    "5_flows_positioning.md",
    "6_sentiment.md",
    "8_risk.md",
    "sources.md",
]

for tab, filename in zip(tabs, files, strict=True):
    with tab:
        st.markdown(_read(base / filename))
        if filename == "8_risk.md":
            st.markdown(_read(base / "compliance.md"))
            st.markdown(_read(base / "disclaimer.md"))

st.sidebar.caption(f"Report folder: {base}")
