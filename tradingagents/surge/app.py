"""Run with: python -m streamlit run tradingagents/surge/app.py"""

from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from tradingagents.dataflows.vendors.eodhd import EODHDClient, EODHDError
from tradingagents.surge.chart import zone_chart
from tradingagents.surge.engine import DetectorConfig, detect_zones, zone_scorecard


@st.cache_data(max_entries=64, show_spinner=False)
def cached_zones(bars, symbol, config):
    return detect_zones(bars, symbol, config)


st.set_page_config(page_title="Surge Zone Lab", layout="wide")
st.title("Surge Zone Lab")
st.caption("Daily research prototype · deterministic measurements · historical EODHD data")
st.warning(
    "Reference Card boundary formulas are applied to experimental leg detection. "
    "Automatic scoring is partial (Time only). No validated probabilities or trade outcomes."
)
with st.sidebar.form("scan"):
    st.subheader("Historical scan")
    symbol = st.text_input("US EODHD ticker", "SPY.US", key="symbol")
    start = st.date_input("Start session", date(2020, 1, 1))
    end = st.date_input("End session", min(date(2026, 11, 6), date.today()))
    atr_period = st.number_input("ATR period", min_value=2, max_value=100, value=14)
    max_base = st.number_input("Maximum base candles", min_value=1, max_value=10, value=4)
    refresh = st.checkbox("Refresh full snapshot (uses API quota)")
    submitted = st.form_submit_button("Fetch and detect", key="fetch")
st.sidebar.caption("Set EODHD_API_TOKEN in your local .env. No API key is sent to an LLM.")
if submitted:
    try:
        config = DetectorConfig(atr_period=int(atr_period), max_base_candles=int(max_base))
        with st.spinner("Loading completed daily sessions"):
            snapshot = EODHDClient(Path(".surge-cache")).daily(
                symbol, start.isoformat(), end.isoformat(), refresh=refresh
            )
        st.session_state["surge_scan"] = (snapshot, config)
    except (EODHDError, ValueError, OSError) as exc:
        # Clear previous results rather than showing a different ticker after a failed scan.
        st.session_state.pop("surge_scan", None)
        st.error(str(exc))
if "surge_scan" not in st.session_state:
    st.info("Enter a ticker and fetch a historical window to begin.")
    st.stop()
snapshot, config = st.session_state["surge_scan"]
metadata = snapshot.metadata
st.subheader(metadata["symbol"] + " · daily")
st.caption(
    f"Last available completed bar: {metadata['last_completed_bar']} · "
    f"Retrieved: {metadata['retrieved_at']} · Cache: {metadata['cache_hit']}"
)
st.info(metadata["warning"])
if metadata["missing_sessions"]:
    st.warning(
        f"{len(metadata['missing_sessions'])} scheduled sessions are missing. "
        "Patterns crossing gaps are excluded."
    )
cutoff = st.select_slider(
    "Replay through completed session (UTC)",
    options=list(snapshot.bars.index),
    value=snapshot.bars.index[-1],
    format_func=lambda value: value.isoformat(),
)
bars = snapshot.bars.loc[:cutoff]
zones = cached_zones(bars, metadata["symbol"], config)
patterns = st.multiselect(
    "Patterns", ["RBR", "DBR", "RBD", "DBD"], default=["RBR", "DBR", "RBD", "DBD"]
)
zones = [zone for zone in zones if zone.pattern in patterns]
st.caption(
    f"{len(zones)} confirmations by {cutoff.isoformat()}. "
    "Confirmed does not mean fresh or currently valid; lifecycle tracking is pending."
)
labels = {zone.zone_id: f"{zone.pattern} · {zone.confirmed_at}" for zone in zones}
selected = st.selectbox(
    "Highlight formation",
    [None, *labels],
    format_func=lambda key: "All confirmations" if key is None else labels[key],
)
st.plotly_chart(
    zone_chart(bars, zones, selected_id=selected),
    width="stretch",
    alt="Historical daily prices with zone confirmations from experimental leg detection",
)
if zones:
    records = []
    for zone in zones:
        score = zone_scorecard(zone)
        records.append(
            {
                **asdict(zone),
                "partial_points": score.earned,
                "scored_maximum": score.available,
                "total_possible": 10,
            }
        )
    table = pd.DataFrame(records)
    st.dataframe(
        table, hide_index=True, alt="Confirmed zones, measured strength and partial points"
    )
    displayed = next((zone for zone in zones if zone.zone_id == selected), zones[-1])
    score = zone_scorecard(displayed)
    st.subheader(f"Partial scorecard · {displayed.pattern} · {displayed.confirmed_at}")
    st.caption(
        f"{score.earned:g}/{score.available:g} available points; full 10-point score unavailable. "
        "Missing components are unscored, not zero. No entry recommendation from a partial score."
    )
    st.dataframe(
        pd.DataFrame([asdict(component) for component in score.components]),
        hide_index=True,
        alt="Six criteria with unknown evidence left unscored",
    )
    st.download_button(
        "Export detected zones CSV",
        table.to_csv(index=False),
        file_name="surge-zones.csv",
        mime="text/csv",
    )
else:
    st.info("No confirmed patterns match these thresholds in the replay window.")
with st.expander("Data provenance and rule provenance"):
    st.json(metadata)
    st.json(asdict(config))
    st.write(
        "Reference Cards reviewed: version 20260501. Reversal distal boundaries include "
        "the incoming leg; continuation boundaries include base and departing leg only. "
        "The detector still selects experimental single-candle legs. Proximal uses the "
        "documented base body edge option. Only Time is automatically scored. BOS is "
        "a trailing price break, not a verified card breakout. Curve, controlling swings, "
        "revisits and profit-zone evidence remain pending. Scores are not probabilities."
    )
