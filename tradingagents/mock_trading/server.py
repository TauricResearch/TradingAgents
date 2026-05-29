"""FastAPI backend server for mock trading system."""

import os
import sys
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Add project root to sys.path to ensure absolute imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from tradingagents.mock_trading import (
        TradingDatabase, TradingScheduler, PortfolioManager, OrderManager, PriceType
    )
except ImportError:
    # Fallback to local import if package structure is different
    from database import TradingDatabase
    from scheduler import TradingScheduler
    from portfolio_manager import PortfolioManager
    from order_manager import OrderManager, PriceType

# Attempt yfinance import for real-time stock prices
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    yf = None
    HAS_YFINANCE = False


# Server Global State
db: Optional[TradingDatabase] = None
scheduler: Optional[TradingScheduler] = None
active_portfolio_id: int = 1
watchlist: List[str] = ["NVDA", "AAPL", "TSLA"]


app = FastAPI(
    title="TradingAgents Mock Trading Terminal",
    description="REST API & Dashboard for AI Multi-Agent financial trading framework",
    version="0.2.5"
)


# Input models
class AnalysisRequest(BaseModel):
    ticker: str
    model: str = "gemini-1.5-flash"


class ExecutionRequest(BaseModel):
    decision_id: int


class WatchlistRequest(BaseModel):
    ticker: str


class SchedulerEditRequest(BaseModel):
    job_id: str
    time: str


def get_stock_price(ticker: str) -> float:
    """Fetch live price of a stock using yfinance or return a simulated price."""
    ticker_upper = ticker.strip().upper()
    
    # Static fallbacks for offline or fails
    default_prices = {
        "NVDA": 122.45,
        "AAPL": 189.30,
        "MSFT": 415.60,
        "TSLA": 178.20,
        "AMZN": 181.90,
        "GOOGL": 173.50,
        "META": 475.40,
        "BTC-USD": 68450.0,
        "ETH-USD": 3750.0,
    }
    
    price = default_prices.get(ticker_upper, 100.0)
    
    if HAS_YFINANCE and yf:
        try:
            stock = yf.Ticker(ticker_upper)
            # Try fast info safely as it is a custom FastInfo object, not a dict
            if hasattr(stock, 'fast_info'):
                try:
                    price_val = stock.fast_info.last_price
                    if price_val is not None:
                        return float(price_val)
                except Exception:
                    pass
            
            # Fallback to history
            hist = stock.history(period="1d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"Failed to fetch live price for {ticker_upper}: {e}")
            
    # Add minor fluctuation to simulated prices to make it feel alive
    fluctuation = random.uniform(-0.005, 0.005)
    return round(price * (1 + fluctuation), 2)


def morning_analysis_task():
    """Simulated daily morning analysis cron for active watchlist tickers."""
    global db, active_portfolio_id
    if not db:
        return
    logger.info(f"[Scheduler] Triggered daily morning analysis for watchlist: {watchlist}")
    
    for ticker in watchlist:
        try:
            price = get_stock_price(ticker)
            rand = random.random()
            decision = "BUY" if rand < 0.45 else ("HOLD" if rand < 0.75 else "SELL")
            confidence = round(random.uniform(0.60, 0.90), 2)
            reasoning = f"Automated daily analysis for {ticker}. Multi-Agent indicator scans suggest standard target adjustments."
            
            db.add_ai_decision(
                portfolio_id=active_portfolio_id,
                ticker=ticker,
                decision=decision,
                confidence_score=confidence,
                reasoning=reasoning,
                analysis_start_time=datetime.now() - timedelta(seconds=2),
                analysis_end_time=datetime.now()
            )
            logger.info(f"[Scheduler] Daily auto-analysis saved for {ticker}: {decision}")
        except Exception as e:
            logger.error(f"[Scheduler] Failed auto-analysis for {ticker}: {e}")


def afternoon_execution_task():
    """Simulated daily afternoon trade execution cron for active watchlist signals."""
    global db, active_portfolio_id
    if not db:
        return
    logger.info("[Scheduler] Triggered daily afternoon trade execution.")
    
    try:
        pending_decisions = db.execute_query("SELECT * FROM ai_decisions WHERE executed = 0")
        for d in pending_decisions:
            ticker = d["ticker"]
            decision_type = d["decision"]
            confidence = d["confidence_score"]
            decision_id = d["id"]
            
            if decision_type == "HOLD":
                db.cursor.execute("UPDATE ai_decisions SET executed = 1, execution_status = 'FILLED' WHERE id = ?", (decision_id,))
                db.conn.commit()
                continue
                
            price = get_stock_price(ticker)
            portfolio = db.get_portfolio(active_portfolio_id)
            cash = portfolio["cash_available"]
            
            if decision_type == "BUY":
                allocation = cash * 0.15 * confidence
                qty = round(allocation / price, 4)
                total_cost = round(qty * price, 2)
                if qty > 0 and total_cost <= cash:
                    new_cash = round(cash - total_cost, 2)
                    db.update_portfolio_balance(active_portfolio_id, portfolio["current_balance"], new_cash)
                    db.add_transaction(
                        portfolio_id=active_portfolio_id,
                        transaction_type="BUY",
                        ticker=ticker,
                        quantity_requested=qty,
                        quantity_filled=qty,
                        order_status="FILLED",
                        price_type="LAST",
                        price_per_share=price,
                        total_value=total_cost,
                        ai_decision_id=decision_id,
                        notes=f"Daily auto-execution of BUY signal for {ticker}"
                    )
                    holdings = db.execute_query("SELECT quantity_held, avg_buy_price FROM holdings WHERE portfolio_id = ? AND ticker = ?", (active_portfolio_id, ticker))
                    if holdings:
                        old_qty = holdings[0]["quantity_held"]
                        old_avg = holdings[0]["avg_buy_price"]
                        new_qty = old_qty + qty
                        new_avg = round(((old_qty * old_avg) + (qty * price)) / new_qty, 2)
                    else:
                        new_qty = qty
                        new_avg = price
                    db.add_holding(active_portfolio_id, ticker, new_qty, new_avg, price)
                    db.cursor.execute("UPDATE ai_decisions SET executed = 1, execution_status = 'FILLED', execution_price = ? WHERE id = ?", (price, decision_id))
                    db.conn.commit()
                    logger.info(f"[Scheduler] Daily auto-execution BOUGHT {qty} shares of {ticker}")
                    
            elif decision_type == "SELL":
                holdings = db.execute_query("SELECT quantity_held, avg_buy_price FROM holdings WHERE portfolio_id = ? AND ticker = ?", (active_portfolio_id, ticker))
                if holdings and holdings[0]["quantity_held"] > 0:
                    qty = holdings[0]["quantity_held"]
                    avg_price = holdings[0]["avg_buy_price"]
                    total_value = round(qty * price, 2)
                    realized_pl = round(total_value - (qty * avg_price), 2)
                    new_cash = round(cash + total_value, 2)
                    db.update_portfolio_balance(active_portfolio_id, portfolio["current_balance"], new_cash)
                    db.add_transaction(
                        portfolio_id=active_portfolio_id,
                        transaction_type="SELL",
                        ticker=ticker,
                        quantity_requested=qty,
                        quantity_filled=qty,
                        order_status="FILLED",
                        price_type="LAST",
                        price_per_share=price,
                        total_value=total_value,
                        ai_decision_id=decision_id,
                        notes=f"Daily auto-execution of SELL signal for {ticker}"
                    )
                    db.add_holding(active_portfolio_id, ticker, 0, 0, price)
                    db.cursor.execute("UPDATE ai_decisions SET executed = 1, execution_status = 'FILLED', execution_price = ?, realized_pl = ? WHERE id = ?", (price, realized_pl, decision_id))
                    db.conn.commit()
                    logger.info(f"[Scheduler] Daily auto-execution SOLD {qty} shares of {ticker}")
    except Exception as e:
        logger.error(f"[Scheduler] Failed daily auto-execution: {e}")


TASK_FUNCTIONS = {
    "morning_analysis": morning_analysis_task,
    "afternoon_execution": afternoon_execution_task
}


@app.on_event("startup")
def startup_event():
    """Initialize DB and background scheduler on startup."""
    global db, scheduler, active_portfolio_id
    
    db_path = os.environ.get("TRADING_DB_PATH", None)
    db = TradingDatabase(db_path)
    
    # Retrieve the latest portfolio or create a new one
    portfolios = db.execute_query("SELECT id FROM portfolios ORDER BY id DESC LIMIT 1")
    if portfolios:
        active_portfolio_id = portfolios[0]["id"]
        logger.info(f"Loaded existing portfolio ID: {active_portfolio_id}")
    else:
        active_portfolio_id = db.create_portfolio(1000.0)
        logger.info(f"Created new default portfolio ID: {active_portfolio_id}")
        
    # Start the scheduler
    try:
        scheduler = TradingScheduler()
        
        # Schedule daily tasks
        scheduler.schedule_daily_execution(9, 30, morning_analysis_task, job_id="morning_analysis")
        scheduler.schedule_daily_execution(14, 0, afternoon_execution_task, job_id="afternoon_execution")
        scheduler.start()
        logger.info("Background trading scheduler started successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize trading scheduler: {e}")


@app.on_event("shutdown")
def shutdown_event():
    """Stop the background scheduler on shutdown."""
    global scheduler
    if scheduler:
        scheduler.stop()
        logger.info("Background trading scheduler shut down.")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the single page application HTML."""
    static_dir = Path(__file__).resolve().parent / "static"
    index_path = static_dir / "index.html"
    
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
            
    # Fallback inline minimal HTML if index.html is missing
    return HTMLResponse(
        content="""
        <html>
            <head><title>TradingAgents Terminal</title></head>
            <body style="font-family: sans-serif; background: #0b0f19; color: #fff; text-align: center; padding-top: 100px;">
                <h1>TradingAgents UI Terminal</h1>
                <p style="color: #64748b;">static/index.html is missing or still being created. Please refresh shortly!</p>
            </body>
        </html>
        """,
        status_code=200
    )


@app.get("/api/status")
def get_status():
    """Retrieve portfolio metrics, available capital, and system parameters."""
    global db, active_portfolio_id
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    portfolio = db.get_portfolio(active_portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
        
    holdings = db.get_holdings(active_portfolio_id)
    
    # Calculate holdings current market value
    total_holdings_value = 0.0
    unrealized_pnl = 0.0
    for h in holdings:
        live_price = get_stock_price(h["ticker"])
        current_val = live_price * h["quantity_held"]
        total_holdings_value += current_val
        unrealized_pnl += (live_price - h["avg_buy_price"]) * h["quantity_held"]
        
    current_balance = portfolio["cash_available"] + total_holdings_value
    initial_capital = portfolio["initial_capital"]
    total_roi = ((current_balance - initial_capital) / initial_capital) * 100.0
    
    # Auto-update portfolio balances in database if changed
    if abs(portfolio["current_balance"] - current_balance) > 0.01:
        db.update_portfolio_balance(active_portfolio_id, current_balance, portfolio["cash_available"])
        
    return {
        "portfolio_id": active_portfolio_id,
        "initial_capital": round(initial_capital, 2),
        "cash_available": round(portfolio["cash_available"], 2),
        "holdings_value": round(total_holdings_value, 2),
        "current_balance": round(current_balance, 2),
        "total_roi_pct": round(total_roi, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "status": portfolio["status"],
        "has_yfinance": HAS_YFINANCE,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@app.get("/api/holdings")
def get_holdings():
    """Retrieve a detailed list of current active stock holdings with real-time profits."""
    global db, active_portfolio_id
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    holdings = db.get_holdings(active_portfolio_id)
    result = []
    
    for h in holdings:
        if h["quantity_held"] <= 0:
            continue
            
        live_price = get_stock_price(h["ticker"])
        avg_price = h["avg_buy_price"]
        qty = h["quantity_held"]
        
        cost_basis = avg_price * qty
        market_value = live_price * qty
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis) * 100.0 if cost_basis > 0 else 0.0
        
        result.append({
            "ticker": h["ticker"],
            "shares": qty,
            "avg_buy_price": round(avg_price, 2),
            "current_price": round(live_price, 2),
            "market_value": round(market_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2)
        })
        
    return result


@app.get("/api/transactions")
def get_transactions(limit: int = 50):
    """Retrieve transaction logs for the active portfolio."""
    global db, active_portfolio_id
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    transactions = db.execute_query(
        "SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY timestamp DESC LIMIT ?",
        (active_portfolio_id, limit)
    )
    
    return [dict(tx) for tx in transactions]


@app.get("/api/scheduler")
def get_scheduler_info():
    """Get status and configured job parameters for the cron scheduler."""
    global scheduler
    if not scheduler:
        return {"running": False, "jobs": [], "timezone": "UTC", "num_jobs": 0}
        
    return scheduler.get_scheduler_status()


@app.post("/api/scheduler/{action}")
def control_scheduler(action: str, background_tasks: BackgroundTasks, job_id: Optional[str] = None):
    """Control the scheduler: pause, resume, or trigger daily jobs immediately."""
    global scheduler
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler not active")
        
    if action == "pause" and job_id:
        success = scheduler.pause_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "message": f"Paused job {job_id}"}
        
    elif action == "resume" and job_id:
        success = scheduler.resume_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "message": f"Resumed job {job_id}"}
        
    elif action == "trigger" and job_id:
        session = scheduler.get_job(job_id)
        if not session:
            raise HTTPException(status_code=404, detail="Job not found")
            
        # Execute the job function asynchronously in background via FastAPI's background_tasks
        func = session.get("job").func
        background_tasks.add_task(func)
        return {"status": "success", "message": f"Manually triggered job {job_id} successfully."}
        
    else:
        raise HTTPException(status_code=400, detail="Invalid action or parameters")


# Watchlist and Schedule Rescheduling Endpoints
@app.get("/api/watchlist")
def get_watchlist():
    """Retrieve the current daily active watchlist."""
    return {"watchlist": watchlist}


@app.post("/api/watchlist/add")
def add_to_watchlist(request: WatchlistRequest):
    """Add a stock ticker to the daily active watchlist."""
    ticker = request.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol required")
    if ticker not in watchlist:
        watchlist.append(ticker)
        logger.info(f"Added {ticker} to active watchlist")
    return {"status": "success", "watchlist": watchlist}


@app.post("/api/watchlist/remove")
def remove_from_watchlist(request: WatchlistRequest):
    """Remove a stock ticker from the daily active watchlist."""
    ticker = request.ticker.strip().upper()
    if ticker in watchlist:
        watchlist.remove(ticker)
        logger.info(f"Removed {ticker} from active watchlist")
    return {"status": "success", "watchlist": watchlist}


@app.post("/api/scheduler-edit")
def edit_scheduler_time(request: SchedulerEditRequest):
    """Dynamically modify the daily cron hour/minute configuration for a job."""
    global scheduler
    if not scheduler:
        raise HTTPException(status_code=500, detail="Scheduler not active")
        
    job_id = request.job_id
    time_str = request.time.strip()
    
    if job_id not in TASK_FUNCTIONS:
        raise HTTPException(status_code=404, detail=f"Job template '{job_id}' not found")
        
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")
        
    # Reschedule the job
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
        
    func = TASK_FUNCTIONS[job_id]
    scheduler.schedule_daily_execution(hour, minute, func, job_id=job_id)
    logger.info(f"Rescheduled job '{job_id}' to daily at {hour:02d}:{minute:02d}")
    
    return {"status": "success", "message": f"Rescheduled job '{job_id}' to {time_str} daily."}


@app.post("/api/analyze")
def run_analysis(request: AnalysisRequest):
    """Run a dynamic multi-agent simulation that produces a trading signal."""
    global db, active_portfolio_id
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    ticker = request.ticker.strip().upper()
    model = request.model
    
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol required")
        
    # Get current price
    price = get_stock_price(ticker)
    
    # Define realistic, colorful multi-agent trace logs
    logs = [
        f"[SYSTEM] 🟢 Starting TradingAgents Multi-Agent framework for {ticker} using model {model}...",
        f"[SYSTEM] Connecting to market database. Loading 100-day candlesticks...",
        f"[TECHNICAL AGENT] 📊 Analyzing indicators for {ticker} at price ${price:.2f}...",
        f"[TECHNICAL AGENT] RSI (14) = {random.randint(35, 78)}. MACD = {'Bullish Crossover' if random.random() > 0.4 else 'Slight Bearish Divergence'}.",
        f"[TECHNICAL AGENT] Moving averages: 50-EMA is {'above' if random.random() > 0.3 else 'below'} 200-EMA. Support level identified at ${price * 0.95:.2f}.",
        f"[SENTIMENT AGENT] 📰 Scanning news feeds, social posts, and quarterly filings...",
        f"[SENTIMENT AGENT] Found 27 recent articles. Social sentiment index: {random.randint(60, 92)}% Bullish.",
        f"[SENTIMENT AGENT] Key news flash: Corporate earnings report shows beating estimates. Sentiment weight: +0.35.",
        f"[RISK MANAGER AGENT] ⚖️ Auditing current portfolio allocation...",
        f"[RISK MANAGER AGENT] Cash reserves check out. Maximum allowed portfolio size per ticker: 15%. Volatility is within acceptable bounds."
    ]
    
    # Decide BUY, SELL, or HOLD with random weights matching realistic behavior
    rand = random.random()
    if rand < 0.45:
        decision = "BUY"
        confidence = round(random.uniform(0.65, 0.92), 2)
        reasoning = (
            f"Strong positive catalyst combined with a bullish MACD crossover on the 4-hour chart. "
            f"Technicals show solid support at ${price * 0.95:.2f} and volume spikes indicate institutional accumulation. "
            f"Risk allocation permits building a long position."
        )
        logs.append(f"[DECIDER AGENT] 🎯 Decider agent generated BUY signal with {int(confidence*100)}% confidence.")
    elif rand < 0.75:
        decision = "HOLD"
        confidence = round(random.uniform(0.50, 0.78), 2)
        reasoning = (
            f"Indicators are overall neutral. RSI resides in the mid-range ({random.randint(45, 55)}), showing no clear "
            f"overbought or oversold conditions. Consolidating around the current moving averages. Advising patience."
        )
        logs.append(f"[DECIDER AGENT] 🎯 Decider agent generated HOLD signal with {int(confidence*100)}% confidence.")
    else:
        decision = "SELL"
        confidence = round(random.uniform(0.60, 0.88), 2)
        reasoning = (
            f"RSI is showing strongly overbought territory on daily frames. Divergence detected in moving average trendlines. "
            f"News flow shows slight profit-taking patterns by large stakeholders. Recommending exit or hedging."
        )
        logs.append(f"[DECIDER AGENT] 🎯 Decider agent generated SELL signal with {int(confidence*100)}% confidence.")
        
    logs.append(f"[SYSTEM] ✅ Analysis completed. Signal generated successfully.")
    
    # Save the decision inside SQLite database
    start_time = datetime.now() - timedelta(seconds=2.4)
    end_time = datetime.now()
    
    decision_id = db.add_ai_decision(
        portfolio_id=active_portfolio_id,
        ticker=ticker,
        decision=decision,
        confidence_score=confidence,
        reasoning=reasoning,
        analysis_start_time=start_time,
        analysis_end_time=end_time
    )
    
    return {
        "decision_id": decision_id,
        "ticker": ticker,
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasoning,
        "price": price,
        "logs": logs
    }


@app.post("/api/execute")
def execute_trade(request: ExecutionRequest):
    """Execute a recorded AI decision immediately, updating holdings and cash balances."""
    global db, active_portfolio_id
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    decision_id = request.decision_id
    
    # Fetch decision details
    decisions = db.execute_query("SELECT * FROM ai_decisions WHERE id = ?", (decision_id,))
    if not decisions:
        raise HTTPException(status_code=404, detail="AI decision not found")
        
    d = decisions[0]
    if d["executed"]:
        raise HTTPException(status_code=400, detail="This signal has already been executed")
        
    ticker = d["ticker"]
    decision_type = d["decision"]
    confidence = d["confidence_score"]
    
    if decision_type == "HOLD":
        # Mark as executed in DB and return
        db.cursor.execute("UPDATE ai_decisions SET executed = 1, execution_status = 'FILLED' WHERE id = ?", (decision_id,))
        db.conn.commit()
        return {"status": "success", "message": "HOLD signal recorded. No transactions needed."}
        
    # Get current price
    price = get_stock_price(ticker)
    portfolio = db.get_portfolio(active_portfolio_id)
    cash = portfolio["cash_available"]
    
    # Determine sizing based on confidence and capital
    if decision_type == "BUY":
        # Allocate up to 10% of cash balance on BUY
        allocation = cash * 0.15 * confidence
        qty = round(allocation / price, 4)
        total_cost = round(qty * price, 2)
        
        if qty <= 0 or total_cost > cash:
            raise HTTPException(status_code=400, detail=f"Insufficient cash available to buy {ticker}.")
            
        # Deduct cash, add transaction, update holding
        new_cash = round(cash - total_cost, 2)
        db.update_portfolio_balance(active_portfolio_id, portfolio["current_balance"], new_cash)
        
        tx_id = db.add_transaction(
            portfolio_id=active_portfolio_id,
            transaction_type="BUY",
            ticker=ticker,
            quantity_requested=qty,
            quantity_filled=qty,
            order_status="FILLED",
            price_type="LAST",
            price_per_share=price,
            total_value=total_cost,
            ai_decision_id=decision_id,
            notes=f"Interactive BUY signal via Web UI with confidence {confidence}"
        )
        
        # Add to holdings
        holdings = db.execute_query(
            "SELECT quantity_held, avg_buy_price FROM holdings WHERE portfolio_id = ? AND ticker = ?",
            (active_portfolio_id, ticker)
        )
        if holdings:
            old_qty = holdings[0]["quantity_held"]
            old_avg = holdings[0]["avg_buy_price"]
            new_qty = old_qty + qty
            new_avg = round(((old_qty * old_avg) + (qty * price)) / new_qty, 2)
        else:
            new_qty = qty
            new_avg = price
            
        db.add_holding(active_portfolio_id, ticker, new_qty, new_avg, price)
        
        # Update decision state in database
        db.cursor.execute(
            "UPDATE ai_decisions SET executed = 1, execution_status = 'FILLED', execution_price = ? WHERE id = ?",
            (price, decision_id)
        )
        db.conn.commit()
        
        return {
            "status": "success",
            "message": f"Successfully BOUGHT {qty:.4f} shares of {ticker} at ${price:.2f} (Total: ${total_cost:.2f})."
        }
        
    elif decision_type == "SELL":
        # Check holdings to see if we have this stock
        holdings = db.execute_query(
            "SELECT quantity_held, avg_buy_price FROM holdings WHERE portfolio_id = ? AND ticker = ?",
            (active_portfolio_id, ticker)
        )
        
        if not holdings or holdings[0]["quantity_held"] <= 0:
            raise HTTPException(status_code=400, detail=f"No active holdings of {ticker} available to sell.")
            
        qty = holdings[0]["quantity_held"]
        avg_price = holdings[0]["avg_buy_price"]
        total_value = round(qty * price, 2)
        realized_pl = round(total_value - (qty * avg_price), 2)
        
        # Add to cash
        new_cash = round(cash + total_value, 2)
        db.update_portfolio_balance(active_portfolio_id, portfolio["current_balance"], new_cash)
        
        tx_id = db.add_transaction(
            portfolio_id=active_portfolio_id,
            transaction_type="SELL",
            ticker=ticker,
            quantity_requested=qty,
            quantity_filled=qty,
            order_status="FILLED",
            price_type="LAST",
            price_per_share=price,
            total_value=total_value,
            ai_decision_id=decision_id,
            notes=f"Interactive SELL signal via Web UI with confidence {confidence}"
        )
        
        # Set holding to zero
        db.add_holding(active_portfolio_id, ticker, 0, 0, price)
        
        # Update decision state
        db.cursor.execute(
            "UPDATE ai_decisions SET executed = 1, execution_status = 'FILLED', execution_price = ?, realized_pl = ? WHERE id = ?",
            (price, realized_pl, decision_id)
        )
        db.conn.commit()
        
        return {
            "status": "success",
            "message": f"Successfully SOLD {qty:.4f} shares of {ticker} at ${price:.2f} (Realized P&L: ${realized_pl:+.2f})."
        }
        
    return {"status": "error", "message": "Failed to parse decision action"}


@app.get("/api/history")
def get_history():
    """Retrieve portfolio snapshot history for plotting performance charts."""
    global db, active_portfolio_id
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    snapshots = db.execute_query(
        "SELECT date, total_portfolio_value, cash_balance FROM daily_snapshots WHERE portfolio_id = ? ORDER BY date ASC",
        (active_portfolio_id,)
    )
    
    # Generate mock history data if database snapshots are empty to show a beautiful graph instantly
    if not snapshots:
        history = []
        base_value = 1000.0
        start_date = datetime.now() - timedelta(days=10)
        
        for i in range(11):
            date_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            # Create a nice upward curve with some fluctuations
            val = base_value + (i * 12.5) + random.uniform(-15.0, 15.0)
            if i == 10:
                # Sync final point with status balance
                status_res = get_status()
                val = status_res["current_balance"]
                
            history.append({
                "date": date_str,
                "total_portfolio_value": round(val, 2),
                "cash_balance": round(val * 0.4, 2)  # dummy cash split
            })
        return history
        
    return [dict(snap) for snap in snapshots]
