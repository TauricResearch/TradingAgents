"""
TradingAgents Dashboard - Streamlit React-like UI with Logging
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/workspace/dashboard/dashboard.log')
    ]
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="TradingAgents Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for React-like styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .log-entry {
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 4px;
    }
    .log-info { background-color: #e3f2fd; border-left: 4px solid #2196f3; }
    .log-warning { background-color: #fff3e0; border-left: 4px solid #ff9800; }
    .log-error { background-color: #ffebee; border-left: 4px solid #f44336; }
    .log-success { background-color: #e8f5e9; border-left: 4px solid #4caf50; }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'trades' not in st.session_state:
    st.session_state.trades = []
if 'agents_active' not in st.session_state:
    st.session_state.agents_active = False
if 'selected ticker' not in st.session_state:
    st.session_state.selected_ticker = "AAPL"

def add_log(level: str, message: str, agent: str = "System"):
    """Add a log entry to the session state"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "agent": agent
    }
    st.session_state.logs.append(log_entry)
    logger.info(f"[{agent}] {message}")
    return log_entry

def generate_sample_trade_data(ticker: str, days: int = 30):
    """Generate sample trading data for visualization"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    base_price = np.random.uniform(100, 500)
    prices = base_price + np.cumsum(np.random.randn(days) * 5)
    
    df = pd.DataFrame({
        'Date': dates,
        'Price': prices,
        'Volume': np.random.randint(1000000, 10000000, days),
        'Ticker': ticker
    })
    return df

def create_price_chart(df: pd.DataFrame):
    """Create interactive price chart using Plotly"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['Date'],
        y=df['Price'],
        mode='lines+markers',
        name='Price',
        line=dict(color='#667eea', width=2),
        marker=dict(size=6)
    ))
    fig.update_layout(
        title=f"{df['Ticker'].iloc[0]} Price Chart",
        xaxis_title="Date",
        yaxis_title="Price ($)",
        hovermode='x unified',
        template='plotly_white',
        height=400
    )
    return fig

def create_volume_chart(df: pd.DataFrame):
    """Create volume bar chart"""
    fig = px.bar(
        df,
        x='Date',
        y='Volume',
        title='Trading Volume',
        labels={'Volume': 'Volume', 'Date': 'Date'},
        color='Volume',
        color_continuous_scale='Blues'
    )
    fig.update_layout(
        template='plotly_white',
        height=300,
        showlegend=False
    )
    return fig

def create_agent_activity_chart():
    """Create agent activity visualization"""
    agents = ['Bull Researcher', 'Bear Researcher', 'Research Manager', 'Trader', 'Risk Manager']
    activities = np.random.randint(5, 25, len(agents))
    
    fig = px.bar(
        x=agents,
        y=activities,
        title='Agent Activity Levels',
        labels={'x': 'Agent', 'y': 'Actions'},
        color=activities,
        color_continuous_scale='Viridis'
    )
    fig.update_layout(
        template='plotly_white',
        height=350,
        showlegend=False
    )
    return fig

def render_dashboard():
    """Main dashboard rendering function"""
    
    # Header
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown('<h1 class="main-header">📈 TradingAgents Dashboard</h1>', unsafe_allow_html=True)
    with col2:
        if st.button("🔄 Refresh Data", use_container_width=True):
            add_log("INFO", "Dashboard data refreshed", "UI")
            st.rerun()
    with col3:
        if st.button("🗑️ Clear Logs", use_container_width=True):
            st.session_state.logs = []
            add_log("INFO", "Logs cleared", "UI")
            st.rerun()
    
    st.divider()
    
    # Sidebar controls
    with st.sidebar:
        st.markdown("### 🎛️ Control Panel")
        
        # Ticker selection
        tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]
        selected_ticker = st.selectbox(
            "Select Ticker",
            tickers,
            index=tickers.index(st.session_state.selected_ticker)
        )
        st.session_state.selected_ticker = selected_ticker
        
        # Agent controls
        st.markdown("### 👥 Agent Controls")
        agents = st.multiselect(
            "Active Agents",
            ["Bull Researcher", "Bear Researcher", "Research Manager", "Trader", "Risk Manager"],
            default=["Bull Researcher", "Bear Researcher"]
        )
        
        # Start/Stop simulation
        if st.toggle("Enable Live Trading Simulation", value=st.session_state.agents_active):
            st.session_state.agents_active = True
            add_log("INFO", "Trading simulation started", "System")
        else:
            st.session_state.agents_active = False
            add_log("WARNING", "Trading simulation stopped", "System")
        
        # Time range
        time_range = st.slider("Days to Display", 7, 90, 30)
        
        st.divider()
        
        # Quick stats
        st.markdown("### 📊 Quick Stats")
        if len(st.session_state.trades) > 0:
            st.metric("Total Trades", len(st.session_state.trades))
            profitable = sum(1 for t in st.session_state.trades if t.get('profit', 0) > 0)
            st.metric("Profitable Trades", f"{profitable}/{len(st.session_state.trades)}")
        else:
            st.info("No trades executed yet")
    
    # Main content area
    # Generate sample data
    trade_data = generate_sample_trade_data(selected_ticker, time_range)
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        current_price = trade_data['Price'].iloc[-1]
        st.metric(
            label=f"{selected_ticker} Price",
            value=f"${current_price:.2f}",
            delta=f"{np.random.uniform(-5, 5):.2f}%"
        )
    with col2:
        avg_volume = trade_data['Volume'].mean()
        st.metric(
            label="Avg Volume",
            value=f"{avg_volume:,.0f}",
            delta=f"{np.random.uniform(-10, 10):.1f}%",
            delta_color="normal"
        )
    with col3:
        total_trades = len(st.session_state.trades)
        st.metric(
            label="Total Trades",
            value=total_trades,
            delta="+" if total_trades > 0 else "0"
        )
    with col4:
        if total_trades > 0:
            avg_profit = np.mean([t.get('profit', 0) for t in st.session_state.trades])
            st.metric(
                label="Avg Profit/Loss",
                value=f"${avg_profit:.2f}",
                delta="Positive" if avg_profit > 0 else "Negative",
                delta_color="inverse" if avg_profit < 0 else "normal"
            )
        else:
            st.metric("Avg Profit/Loss", "$0.00")
    
    st.divider()
    
    # Charts row
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(create_price_chart(trade_data), use_container_width=True)
    with col2:
        st.plotly_chart(create_volume_chart(trade_data), use_container_width=True)
    
    # Agent activity and logs
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("### 🤖 Agent Activity")
        st.plotly_chart(create_agent_activity_chart(), use_container_width=True)
        
        # Recent trades table
        if len(st.session_state.trades) > 0:
            st.markdown("### 💼 Recent Trades")
            trades_df = pd.DataFrame(st.session_state.trades[-10:])
            st.dataframe(
                trades_df[['ticker', 'action', 'quantity', 'price', 'profit']],
                use_container_width=True,
                hide_index=True
            )
    
    with col2:
        st.markdown("### 📝 Activity Log")
        
        # Log level filter
        log_levels = st.multiselect(
            "Filter Logs",
            ["INFO", "WARNING", "ERROR", "SUCCESS"],
            default=["INFO", "WARNING", "ERROR", "SUCCESS"],
            label_visibility="collapsed"
        )
        
        # Display logs
        log_container = st.container()
        with log_container:
            filtered_logs = [log for log in st.session_state.logs[-50:] if log['level'] in log_levels]
            
            if filtered_logs:
                for log in reversed(filtered_logs):
                    css_class = f"log-{log['level'].lower()}"
                    log_html = f"""
                    <div class="log-entry {css_class}">
                        <strong>[{log['timestamp']}]</strong> 
                        <em>{log['agent']}:</em> {log['message']}
                    </div>
                    """
                    st.markdown(log_html, unsafe_allow_html=True)
            else:
                st.info("No logs to display")
    
    # Simulation button
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 Run Trading Simulation", type="primary", use_container_width=True):
            run_simulation(selected_ticker, agents)

def run_simulation(ticker: str, active_agents: list):
    """Run a trading simulation and log activities"""
    add_log("INFO", f"Starting trading simulation for {ticker}", "System")
    
    progress_bar = st.progress(0)
    
    # Simulate agent activities
    steps = [
        ("Bull Researcher", "Analyzing market trends..."),
        ("Bear Researcher", "Evaluating risks..."),
        ("Research Manager", "Consolidating research..."),
        ("Trader", "Executing trade decision..."),
        ("Risk Manager", "Validating risk parameters...")
    ]
    
    for i, (agent, message) in enumerate(steps):
        if agent in active_agents or agent == "System":
            progress_bar.progress((i + 1) / len(steps))
            add_log("INFO", message, agent)
            
            # Simulate trade execution
            if agent == "Trader" and st.session_state.agents_active:
                trade = {
                    "ticker": ticker,
                    "action": np.random.choice(["BUY", "SELL"]),
                    "quantity": np.random.randint(10, 100),
                    "price": round(np.random.uniform(100, 500), 2),
                    "timestamp": datetime.now().isoformat(),
                    "profit": round(np.random.uniform(-100, 500), 2)
                }
                st.session_state.trades.append(trade)
                add_log("SUCCESS", f"Executed {trade['action']} {trade['quantity']} shares of {ticker} at ${trade['price']}", "Trader")
    
    progress_bar.empty()
    add_log("SUCCESS", "Trading simulation completed successfully", "System")
    st.success("Simulation completed! Check the logs and trades table for details.")

def main():
    """Main application entry point"""
    add_log("INFO", "Dashboard initialized", "System")
    
    # Welcome message
    st.markdown("""
    ### Welcome to TradingAgents Dashboard
    
    This interactive dashboard provides real-time visualization of trading activities,
    agent performance, and comprehensive logging for the TradingAgents system.
    
    **Features:**
    - 📊 Real-time price and volume charts
    - 🤖 Multi-agent activity monitoring
    - 📝 Comprehensive activity logging
    - 💼 Trade execution tracking
    - 🎛️ Interactive control panel
    """)
    
    render_dashboard()
    
    # Footer
    st.divider()
    st.markdown(
        """
        <div style="text-align: center; color: #666;">
            <small>TradingAgents Dashboard v1.0 | Built with Streamlit & Plotly</small>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
