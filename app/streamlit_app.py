"""Handels-Agenten — Streamlit Web-UI"""
import queue
import threading
from datetime import date, timedelta

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

st.set_page_config(page_title="Handels-Agenten", page_icon="📈", layout="wide")
st.title("Handels-Agenten")
st.caption("Multi-Agent LLM Handelsanalyse")

with st.sidebar:
    st.header("Einstellungen")
    ticker = st.text_input("Ticker-Symbol", value="NVDA", help="z.B. NVDA, AAPL, TSLA")
    analysis_date = st.date_input(
        "Analyse-Datum",
        value=date.today() - timedelta(days=1),
        max_value=date.today() - timedelta(days=1),
    )
    st.divider()
    st.caption("LLM-Anbieter und API-Keys werden per Umgebungsvariablen konfiguriert.")

st.markdown(f"**Ticker:** `{ticker}` &nbsp;|&nbsp; **Datum:** `{analysis_date}`")

if st.button("Analyse starten", type="primary", disabled=not ticker.strip()):
    result_q: queue.Queue = queue.Queue()

    def run_analysis():
        try:
            config = DEFAULT_CONFIG.copy()
            ta = TradingAgentsGraph(debug=False, config=config)
            _, decision = ta.propagate(ticker.strip().upper(), str(analysis_date))
            result_q.put(("ok", decision))
        except Exception as exc:
            result_q.put(("error", str(exc)))

    thread = threading.Thread(target=run_analysis, daemon=True)
    thread.start()

    with st.spinner(f"Analysiere {ticker.upper()} für {analysis_date} ..."):
        thread.join(timeout=300)

    if not result_q.empty():
        kind, payload = result_q.get()
        if kind == "ok":
            st.success("Analyse abgeschlossen")
            st.subheader("Handelsentscheidung")
            st.write(payload)
        else:
            st.error(f"Fehler: {payload}")
    else:
        st.error("Zeitüberschreitung (5 min). Bitte erneut versuchen.")
