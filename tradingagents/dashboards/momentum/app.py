"""
Momentum Dashboard - Streamlit Web UI

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from __init__ import MomentumScanner, MomentumIndicator, MAGNIFICENT_SEVEN, get_top_momentum_stocks


# Page config
st.set_page_config(
    page_title="Momentum Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stMetric {
        background-color: #1E1E1E;
        padding: 10px;
        border-radius: 10px;
    }
    .bullish { color: #00FF00; }
    .bearish { color: #FF0000; }
    .squeeze { color: #FFA500; }
</style>
""", unsafe_allow_html=True)


def main():
    st.title("📈 Momentum Dashboard")
    st.subheader("Real-time Momentum Analysis for Trading")
    
    # Sidebar
    st.sidebar.header("Settings")
    
    # Stock selection
    stock_option = st.sidebar.radio(
        "Stock Universe",
        ["Magnificent Seven", "Top Momentum", "Custom"]
    )
    
    if stock_option == "Magnificent Seven":
        symbols = MAGNIFICENT_SEVEN
    elif stock_option == "Top Momentum":
        symbols = get_top_momentum_stocks(15)
    else:
        custom_symbols = st.sidebar.text_input(
            "Enter symbols (comma-separated)",
            "AAPL,MSFT,GOOGL"
        )
        symbols = [s.strip().upper() for s in custom_symbols.split(",")]
    
    # Timeframe selection
    timeframe = st.sidebar.selectbox(
        "Timeframe",
        ["1h", "1d", "1wk"]
    )
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data"):
        st.rerun()
    
    # Scan stocks
    with st.spinner("Scanning momentum signals..."):
        scanner = MomentumScanner(symbols)
        results = scanner.scan_all()
    
    # Display results
    col1, col2, col3 = st.columns(3)
    
    # Metrics
    bullish_count = sum(1 for r in results if r.get("trend") == "BULLISH" and "error" not in r)
    bearish_count = sum(1 for r in results if r.get("trend") == "BEARISH" and "error" not in r)
    squeeze_count = sum(1 for r in results if r.get("squeeze") and "error" not in r)
    
    with col1:
        st.metric("🟢 Bullish", bullish_count)
    with col2:
        st.metric("🔴 Bearish", bearish_count)
    with col3:
        st.metric("🟠 Squeeze", squeeze_count)
    
    st.divider()
    
    # Results table
    st.subheader("📊 Momentum Signals")
    
    # Create DataFrame
    df_data = []
    for r in results:
        if "error" not in r:
            df_data.append({
                "Symbol": r["symbol"],
                "Price": f"${r['price']}",
                "EMA 21": f"${r['ema_21']}",
                "Trend": r["trend"],
                "RSI": r["rsi"],
                "Vol Mom": f"{r['volume_momentum']:.2f}x",
                "Squeeze": "🔴" if r["squeeze"] else "",
                "Signal": r["signal"],
                "Strength": r["signal_strength"]
            })
    
    df = pd.DataFrame(df_data)
    
    # Style the dataframe
    def color_trend(val):
        if val == "BULLISH":
            return "color: green; font-weight: bold"
        elif val == "BEARISH":
            return "color: red; font-weight: bold"
        return ""
    
    def color_signal(val):
        if "BUY" in val:
            return "background-color: #1a4d1a; color: white"
        elif "SELL" in val:
            return "background-color: #4d1a1a; color: white"
        elif "BREAKOUT" in val:
            return "background-color: #4d3d1a; color: white"
        return ""
    
    styled_df = df.style.applymap(color_trend, subset=["Trend"]).applymap(color_signal, subset=["Signal"])
    st.dataframe(styled_df, use_container_width=True)
    
    st.divider()
    
    # Detailed chart for selected symbol
    st.subheader("📈 Detailed Analysis")
    
    selected_symbol = st.selectbox(
        "Select symbol for detailed view",
        [r["symbol"] for r in results if "error" not in r]
    )
    
    if selected_symbol:
        with st.spinner(f"Loading {selected_symbol} chart..."):
            # Fetch data for chart
            import yfinance as yf
            ticker = yf.Ticker(selected_symbol)
            hist = ticker.history(period="3mo", interval=timeframe)
            
            if not hist.empty:
                # Calculate indicators
                indicators = MomentumIndicator()
                close = hist['Close']
                
                ema_21 = indicators.ema(close, 21)
                bb_upper, bb_mid, bb_lower = indicators.bollinger_bands(close)
                
                # Create candlestick chart with indicators
                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.05,
                    row_heights=[0.6, 0.2, 0.2]
                )
                
                # Candlestick
                fig.add_trace(
                    go.Candlestick(
                        x=hist.index,
                        open=hist['Open'],
                        high=hist['High'],
                        low=hist['Low'],
                        close=hist['Close'],
                        name="Price"
                    ),
                    row=1, col=1
                )
                
                # EMA 21
                fig.add_trace(
                    go.Scatter(
                        x=hist.index,
                        y=ema_21,
                        line=dict(color='yellow', width=1),
                        name="EMA 21"
                    ),
                    row=1, col=1
                )
                
                # Bollinger Bands
                fig.add_trace(
                    go.Scatter(
                        x=hist.index,
                        y=bb_upper,
                        line=dict(color='gray', width=1, dash='dash'),
                        name="BB Upper"
                    ),
                    row=1, col=1
                )
                fig.add_trace(
                    go.Scatter(
                        x=hist.index,
                        y=bb_lower,
                        line=dict(color='gray', width=1, dash='dash'),
                        name="BB Lower"
                    ),
                    row=1, col=1
                )
                
                # Volume
                fig.add_trace(
                    go.Bar(
                        x=hist.index,
                        y=hist['Volume'],
                        name="Volume",
                        marker_color='lightblue'
                    ),
                    row=2, col=1
                )
                
                # RSI
                rsi = indicators.rsi(close)
                fig.add_trace(
                    go.Scatter(
                        x=hist.index,
                        y=rsi,
                        line=dict(color='purple', width=1),
                        name="RSI"
                    ),
                    row=3, col=1
                )
                # RSI levels
                fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
                
                fig.update_layout(
                    title=f"{selected_symbol} - Momentum Analysis",
                    xaxis_rangeslider_visible=False,
                    height=800
                )
                
                st.plotly_chart(fig, use_container_width=True)
    
    # Footer
    st.divider()
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data: Yahoo Finance")


if __name__ == "__main__":
    main()