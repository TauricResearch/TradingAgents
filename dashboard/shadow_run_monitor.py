
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Shadow Run Monitor",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #4CAF50;
    }
    .status-ok { color: #4CAF50; }
    .status-warn { color: #FFC107; }
    .status-crit { color: #FF5252; }
</style>
""", unsafe_allow_html=True)

DB_PATH = "data/shadow_run.db"

def load_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        trades_df = pd.read_sql_query("SELECT * FROM shadow_trades ORDER BY date DESC", conn)
        metrics_df = pd.read_sql_query("SELECT * FROM daily_metrics ORDER BY date DESC", conn)
        conn.close()
        return trades_df, metrics_df
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

# Header
st.title("🦅 TradingAgents: Shadow Run Monitor")
st.markdown("Phase 9: 30-Day Paper Trading Validation")

trades_df, metrics_df = load_data()

if metrics_df.empty:
    st.warning("No data available yet. Waiting for first Shadow Run execution.")
    st.info("System is ready. Infrastructure initialized.")
else:
    # Top Level Metrics
    latest = metrics_df.iloc[0]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades (Cumulative)", len(trades_df))
    with col2:
        rej_rate = latest['rejection_rate']
        delta_color = "normal"
        if rej_rate > 0.20: delta_color = "inverse"
        st.metric("Rejection Rate (Daily)", f"{rej_rate:.1%}", delta_color=delta_color)
    with col3:
        st.metric("API Cost (Daily)", f"${latest['total_api_cost']:.3f}")
    with col4:
        st.metric("Max Latency", f"{latest['max_latency']:.2f}s")

    # Vital Signs Charts
    st.subheader("📊 Vital Signs")
    
    tab1, tab2, tab3 = st.tabs(["Rejection Rate", "Latency", "Cost Analysis"])
    
    with tab1:
        fig_rej = px.line(metrics_df, x='date', y='rejection_rate', title="Fact-Checker Rejection Rate")
        fig_rej.add_hline(y=0.20, line_dash="dash", line_color="red", annotation_text="Critical Threshold (20%)")
        fig_rej.add_hline(y=0.05, line_dash="dash", line_color="green", annotation_text="Healthy Floor (5%)")
        st.plotly_chart(fig_rej, use_container_width=True)
        
    with tab2:
        fig_lat = px.bar(trades_df, x='ticker', y='latency_fact_check', color='date', title="Fact-Check Latency per Trade")
        fig_lat.add_hline(y=2.0, line_dash="dash", line_color="red", annotation_text="Latency Budget (2s)")
        st.plotly_chart(fig_lat, use_container_width=True)
        
    with tab3:
        fig_cost = px.area(metrics_df, x='date', y='total_api_cost', title="Daily API Cost")
        st.plotly_chart(fig_cost, use_container_width=True)

    # Trade Log
    st.subheader("📝 Daily Trade Log")
    
    # Filters
    ticker_filter = st.multiselect("Filter by Ticker", options=trades_df['ticker'].unique())
    if ticker_filter:
        display_df = trades_df[trades_df['ticker'].isin(ticker_filter)]
    else:
        display_df = trades_df
        
    st.dataframe(
        display_df[['date', 'ticker', 'decision', 'quantity', 'confidence', 'fact_check_passed', 'rejection_reason']],
        use_container_width=True,
        hide_index=True
    )

    # System Health
    st.subheader("🏥 System Health")
    health_col1, health_col2 = st.columns(2)
    
    with health_col1:
        if rej_rate > 0.20:
             st.error("🚨 CRITICAL: Rejection rate > 20%. Prompts are drifting.")
        elif rej_rate < 0.05:
            st.warning("⚠️ WARNING: Rejection rate < 5%. Fact checker may be too loose.")
        else:
            st.success("✅ HEALTHY: Rejection rate nominal (5-20%).")
            
    with health_col2:
        if latest['max_latency'] > 2.0:
            st.error("🚨 CRITICAL: Latency > 2s. Optimize DeBERTa.")
        else:
            st.success("✅ HEALTHY: Latency within budget.")
