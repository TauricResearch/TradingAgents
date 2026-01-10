#!/usr/bin/env python3
"""
Shadow Run - Daily Paper Trading Execution

Runs after market close (4:30 PM ET) to:
1. Download latest market data
2. Run trading workflow for each ticker
3. Log decisions and metrics to SQLite
4. Update monitoring dashboard data
"""

import sys
import os
import time
import sqlite3
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingagents.workflows.integrated_workflow import IntegratedTradingWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/shadow_run.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = "data/shadow_run.db"

def init_db():
    """Initialize SQLite database if it doesn't exist."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Shadow Trades Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shadow_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        ticker TEXT,
        anon_ticker TEXT,
        decision TEXT,
        quantity INTEGER,
        decision_price REAL,
        confidence REAL,
        fact_check_passed BOOLEAN,
        risk_gate_passed BOOLEAN,
        rejection_reason TEXT,
        regime TEXT,
        volatility REAL,
        latency_total REAL,
        latency_fact_check REAL,
        api_cost_est REAL
    )
    ''')
    
    # Daily Metrics Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_metrics (
        date TEXT PRIMARY KEY,
        total_attempts INTEGER,
        rejections INTEGER,
        rejection_rate REAL,
        regime_steady BOOLEAN,
        avg_slippage REAL,
        total_api_cost REAL,
        max_latency REAL
    )
    ''')
    
    conn.commit()
    conn.close()

def get_market_data(ticker: str) -> dict:
    """Download and prepare market data."""
    # Download 100 days of data for warm-up
    end_date = datetime.now()
    start_date = end_date - timedelta(days=150)
    
    try:
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, multi_level_index=False)
        
        if len(df) < 60:
            logger.warning(f"Insufficient data for {ticker}: {len(df)} rows")
            return None
            
        # Calculate ATR (14-day)
        high = df['High']
        low = df['Low']
        close = df['Close']
        current_price = float(close.iloc[-1])
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Prepare data dict (Risk Gate Expects: close, volume, atr)
        market_data = {
            "price_series": df['Close'],
            "price_data": df,  # Full DF for regime detector
            "current_price": current_price,
            "close": current_price,  # REQUIRED by Risk Gate
            "volume_avg": float(df['Volume'].mean()),
            "volume": float(df['Volume'].iloc[-1]), # REQUIRED by Risk Gate
            "atr": float(atr) # Likely needed for position sizing
        }
        
        return market_data
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None

def run_shadow_trading():
    """Execute daily shadow trading cycle."""
    logger.info("Starting Shadow Run execution...")
    
    # Initialize DB
    init_db()
    
    # Configuration
    config = {
        "anonymizer_seed": "shadow_run_v1",
        "use_nli_model": True,  # Use real NLI model
        "max_json_retries": 2,
        "fact_check_latency_budget": 2.0,
        "portfolio_value": 100000,
        "risk_config": {
            "max_position_risk": 0.02,
            "max_portfolio_heat": 0.10,
            "circuit_breaker": 0.15
        }
    }
    
    # Initialize Workflow
    workflow = IntegratedTradingWorkflow(config)
    
    tickers = ["AAPL", "NVDA", "AMZN", "MSFT", "GOOGL", "TSLA", "AMD", "META"]
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    total_cost = 0.0
    latencies = []
    rejections = 0
    trade_count = 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Mock LLM agents (replace with real API calls for actual production)
    # For now, we reuse the mocks from ignition tests, but in a real shadow run
    # these would call GPT-4o-mini
    from unittest.mock import Mock
    llm_agents = {
        "market_analyst": lambda p: Mock(content='{"analyst_type": "market", "key_findings": ["Trend is clearly bullish on daily timeframe", "Volume is increasing on up days", "RSI is in bullish zone but not overbought"], "signal": "BUY", "confidence": 0.8, "reasoning": "The technical setup is looking very strong with price action above key moving averages and momentum indicators confirming the trend direction."}'),
        "bull_researcher": lambda p: Mock(content='{"researcher_type": "bull", "key_arguments": ["Revenue growth is accelerating quarter over quarter in key segments", "Market share expansion in cloud computing sector is significant"], "signal": "BUY", "confidence": 0.85, "supporting_evidence": ["Q3 Earnings Report showed 20% growth", "Gartner Magic Quadrant leadership"]}'),
        "bear_researcher": lambda p: Mock(content='{"researcher_type": "bear", "key_arguments": ["Valuation multiples are currently at historical highs compared to peers", "Macroeconomic headwinds could impact consumer discretionary spending"], "signal": "HOLD", "confidence": 0.4, "supporting_evidence": ["P/E ratio at 45x forward earnings", "Fed rate hike projections"]}'),
        "trader": lambda p: {"trader_investment_plan": "Based on the Market Regime being VOLATILE... FINAL TRANSACTION PROPOSAL: **BUY**", "sender": "Trader"},
    }
    
    for ticker in tickers:
        logger.info(f"Processing {ticker}...")
        
        market_data = get_market_data(ticker)
        if not market_data:
            continue
            
        # Ground truth for fact checking (in real run, fetch news/earnings)
        ground_truth = {
            "price": market_data['current_price'],
            "trend": "up" if market_data['current_price'] > market_data['price_series'].iloc[-20] else "down"
        }
        
        try:
            decision, metrics = workflow.execute_trade_decision(
                ticker=ticker,
                trading_date=today_str,
                market_data=market_data,
                ground_truth=ground_truth,
                llm_agents=llm_agents
            )
            
            # Log to DB
            est_cost = 0.003  # Estimated API cost per run
            total_cost += est_cost
            latencies.append(metrics.total_latency)
            
            if decision.action.value == "HOLD" and (not decision.fact_check_passed or not decision.risk_gate_passed):
                rejections += 1
            
            # Get regime info (hacky access, normally returned by execute)
            regime_val = "UNKNOWN" 
            # In a real impl, we'd capture this from the workflow return
            
            cursor.execute('''
                INSERT INTO shadow_trades 
                (date, ticker, anon_ticker, decision, quantity, decision_price, 
                confidence, fact_check_passed, risk_gate_passed, rejection_reason,
                regime, latency_total, latency_fact_check, api_cost_est)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                today_str, ticker, workflow.anonymizer.anonymize_ticker(ticker),
                decision.action.value, decision.quantity, market_data['current_price'],
                decision.confidence, decision.fact_check_passed, decision.risk_gate_passed,
                decision.reasoning if "REJECTED" in decision.reasoning else None,
                "VOLATILE", # Placeholder, would get from actual detection
                metrics.total_latency, metrics.fact_check_time, est_cost
            ))
            
            trade_count += 1
            conn.commit()
            
        except Exception as e:
            logger.error(f"Workflow failed for {ticker}: {e}")
            
    # Daily Summary
    rejection_rate = rejections / trade_count if trade_count > 0 else 0
    max_latency = max(latencies) if latencies else 0
    
    cursor.execute('''
        INSERT OR REPLACE INTO daily_metrics
        (date, total_attempts, rejections, rejection_rate, regime_steady, 
        avg_slippage, total_api_cost, max_latency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        today_str, trade_count, rejections, rejection_rate, 
        True, 0.0, total_cost, max_latency
    ))
    
    conn.commit()
    conn.close()
    logger.info("Shadow Run completed successfully.")

if __name__ == "__main__":
    run_shadow_trading()
