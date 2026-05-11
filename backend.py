"""
TradingAgents Dashboard - FastAPI Backend
Streams multi-agent analysis for watched tickers via WebSocket.
"""

from dotenv import load_dotenv
load_dotenv()

import sys
sys.setrecursionlimit(10000)

import asyncio
import concurrent.futures
import io
import json
import os
import queue
import random
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional

import uvicorn
import yfinance as yf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from portfolio import Portfolio

DEMO_MODE = False
try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    print("[INFO] TradingAgents loaded successfully.")
except ImportError:
    DEMO_MODE = True
    print("[WARN] TradingAgents not found - running in DEMO MODE.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(refresh_loop())
    yield

app = FastAPI(title="TradingAgents Dashboard", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

executor = ThreadPoolExecutor(max_workers=4)
portfolio = Portfolio()
portfolio.load()
watched_tickers: Dict[str, dict] = {}
clients: List[WebSocket] = []
refresh_interval: int = 300

AGENT_SEQUENCE = [
    "Fundamentals Analyst", "Sentiment Analyst", "News Analyst", "Technical Analyst",
    "Bull Researcher", "Bear Researcher", "Trader", "Risk Manager", "Portfolio Manager",
]


async def broadcast(event: dict):
    dead = []
    for ws in clients:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in clients:
            clients.remove(ws)


class LiveCapture(io.StringIO):
    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def write(self, text: str):
        super().write(text)
        stripped = text.strip()
        if stripped:
            self._cb(stripped)
        return len(text)

    def flush(self):
        pass


async def _demo_analysis(ticker: str):
    messages = {
        "Fundamentals Analyst": [f"Fetching {ticker} financials...", f"EPS growth YoY: +{random.randint(5,30)}%", f"Free cash flow: ${random.randint(1,50)}B"],
        "Sentiment Analyst": [f"Scanning social media for {ticker}...", f"Reddit sentiment: {random.choice(['bullish','bearish','neutral'])}"],
        "News Analyst": [f"Parsing news for {ticker}...", f"Found {random.randint(8,40)} articles", f"Key theme: {random.choice(['earnings beat','product launch','regulatory concern'])}"],
        "Technical Analyst": [f"Computing indicators for {ticker}...", f"RSI(14): {random.randint(30,75)}", f"MACD: {'bullish crossover' if random.random()>0.5 else 'bearish divergence'}"],
        "Bull Researcher": [f"Bullish case for {ticker}...", f"Catalyst: {random.choice(['AI tailwinds','margin expansion','market share gains'])}"],
        "Bear Researcher": [f"Bearish case for {ticker}...", f"Risk: {random.choice(['valuation stretched','competition','regulatory risk'])}"],
        "Trader": [f"Synthesizing reports for {ticker}...", f"Signal alignment: {random.randint(60,90)}%"],
        "Risk Manager": [f"Risk assessment for {ticker}...", f"VaR (95%): {random.uniform(1,5):.2f}%"],
        "Portfolio Manager": [f"Final review for {ticker}...", f"Position sizing: {random.choice(['full','half','quarter'])}"],
    }
    decision = random.choices(["BUY", "SELL", "HOLD"], weights=[0.4, 0.3, 0.3])[0]
    confidence = random.randint(55, 92)
    reasons = {
        "BUY": f"Strong fundamentals and positive sentiment support a long position in {ticker}.",
        "SELL": f"Deteriorating margins and bearish signals suggest reducing exposure to {ticker}.",
        "HOLD": f"Mixed signals across analysts; maintaining current position in {ticker}.",
    }
    for agent in AGENT_SEQUENCE:
        if ticker not in watched_tickers:
            return None
        watched_tickers[ticker]["current_agent"] = agent
        await broadcast({"type": "agent_start", "ticker": ticker, "agent": agent})
        for msg in messages.get(agent, []):
            await asyncio.sleep(random.uniform(0.4, 1.2))
            await broadcast({"type": "agent_log", "ticker": ticker, "agent": agent, "message": msg})
        await asyncio.sleep(random.uniform(0.5, 1.5))
    return {
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasons[decision],
        "timestamp": datetime.now().isoformat(),
    }


def _run_real_analysis(ticker: str, log_callback, node_callback) -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "anthropic"
    config["deep_think_llm"] = "claude-sonnet-4-6"
    config["quick_think_llm"] = "claude-haiku-4-5-20251001"
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["max_recur_limit"] = 250

    analyst_keys = ["market", "social", "news", "fundamentals"]
    capture = LiveCapture(log_callback)
    old_stdout = sys.stdout
    sys.stdout = capture
    try:
        ta = TradingAgentsGraph(analyst_keys, debug=False, config=config)
        analysis_date = datetime.now().strftime("%Y-%m-%d")
        _, decision_raw = ta.propagate(ticker, analysis_date, on_node=node_callback)
    finally:
        sys.stdout = old_stdout

    if isinstance(decision_raw, dict):
        action = decision_raw.get("action", "HOLD").upper()
        reasoning = decision_raw.get("reasoning", "No reasoning provided.")
        confidence = int(decision_raw.get("confidence", 70))
    else:
        raw = str(decision_raw) if decision_raw else ""
        action = "HOLD"
        for word in ["BUY", "SELL", "HOLD"]:
            if word in raw.upper():
                action = word
                break
        reasoning = raw[:300] if raw else "Analysis complete."
        confidence = 70

    return {
        "decision": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "timestamp": datetime.now().isoformat(),
    }


async def analyse_ticker(ticker: str):
    print(f"[INFO] Starting analysis for {ticker}")
    if ticker not in watched_tickers:
        print(f"[WARN] {ticker} not in watchlist, skipping")
        return

    watched_tickers[ticker]["status"] = "analyzing"
    watched_tickers[ticker]["current_agent"] = None
    await broadcast({"type": "ticker_status", "ticker": ticker, "status": "analyzing"})
    print(f"[INFO] Broadcast 'analyzing' for {ticker}")

    try:
        if DEMO_MODE:
            result = await _demo_analysis(ticker)
        else:
            log_queue: queue.Queue = queue.Queue()

            def on_log(text: str):
                log_queue.put({"type": "log", "message": text})

            def on_node(node_name: str):
                log_queue.put({"type": "agent_start", "agent": node_name})

            async def drain_queue():
                while not log_queue.empty():
                    try:
                        event = log_queue.get_nowait()
                        if event["type"] == "agent_start":
                            agent = event["agent"]
                            watched_tickers[ticker]["current_agent"] = agent
                            await broadcast({"type": "agent_start", "ticker": ticker, "agent": agent})
                        elif event["type"] == "log":
                            agent = watched_tickers[ticker].get("current_agent") or "Agent"
                            await broadcast({"type": "agent_log", "ticker": ticker, "agent": agent, "message": event["message"]})
                    except queue.Empty:
                        break

            print(f"[INFO] Running TradingAgents for {ticker} in background thread...")
            future = executor.submit(_run_real_analysis, ticker, on_log, on_node)

            while not future.done():
                await asyncio.sleep(2)
                await drain_queue()

            result = future.result()
            await drain_queue()

        if result is None:
            raise ValueError("Analysis returned no result")

        watched_tickers[ticker]["status"] = "done"
        watched_tickers[ticker]["last_result"] = result
        watched_tickers[ticker]["last_updated"] = datetime.now().isoformat()
        watched_tickers[ticker]["current_agent"] = None
        await broadcast({
            "type": "analysis_complete",
            "ticker": ticker,
            "result": result,
            "last_updated": watched_tickers[ticker]["last_updated"],
        })
        print(f"[INFO] Done: {ticker} -> {result['decision']} ({result['confidence']}%)")

    except Exception as e:
        print(f"[ERROR] Analysis failed for {ticker}:")
        traceback.print_exc()
        if ticker in watched_tickers:
            watched_tickers[ticker]["status"] = "error"
        await broadcast({"type": "ticker_error", "ticker": ticker, "error": str(e)})


async def refresh_loop():
    while True:
        await asyncio.sleep(refresh_interval)
        for ticker in list(watched_tickers.keys()):
            if watched_tickers[ticker]["status"] != "analyzing":
                asyncio.create_task(analyse_ticker(ticker))


class TickerPayload(BaseModel):
    ticker: str


class ConfigPayload(BaseModel):
    refresh_interval: Optional[int] = None


class TradePayload(BaseModel):
    ticker: str
    side: str
    amount_usd: float


@app.get("/api/tickers")
def get_tickers():
    return JSONResponse(watched_tickers)


@app.post("/api/tickers")
async def add_ticker(payload: TickerPayload):
    t = payload.ticker.upper().strip()
    if not t:
        return JSONResponse({"error": "Invalid ticker"}, status_code=400)
    if t in watched_tickers:
        return JSONResponse({"error": "Already watching"}, status_code=409)
    watched_tickers[t] = {
        "status": "pending",
        "current_agent": None,
        "last_result": None,
        "last_updated": None,
        "logs": [],
    }
    await broadcast({"type": "ticker_added", "ticker": t})
    asyncio.create_task(analyse_ticker(t))
    return JSONResponse({"ticker": t, "status": "added"})


@app.delete("/api/tickers/{ticker}")
async def remove_ticker(ticker: str):
    t = ticker.upper()
    if t not in watched_tickers:
        return JSONResponse({"error": "Not found"}, status_code=404)
    del watched_tickers[t]
    await broadcast({"type": "ticker_removed", "ticker": t})
    return JSONResponse({"ticker": t, "status": "removed"})


@app.post("/api/tickers/{ticker}/refresh")
async def refresh_ticker(ticker: str):
    t = ticker.upper()
    if t not in watched_tickers:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if watched_tickers[t]["status"] == "analyzing":
        return JSONResponse({"error": "Analysis in progress"}, status_code=409)
    asyncio.create_task(analyse_ticker(t))
    return JSONResponse({"ticker": t, "status": "refreshing"})


@app.patch("/api/config")
async def update_config(payload: ConfigPayload):
    global refresh_interval
    if payload.refresh_interval is not None:
        refresh_interval = max(60, payload.refresh_interval)
    return JSONResponse({"refresh_interval": refresh_interval, "demo_mode": DEMO_MODE})


@app.get("/api/status")
def get_status():
    return JSONResponse({
        "demo_mode": DEMO_MODE,
        "refresh_interval": refresh_interval,
        "watched_count": len(watched_tickers),
        "connected_clients": len(clients),
    })


@app.get("/api/tickers/{ticker}/chart")
def get_chart(ticker: str):
    t = ticker.upper()
    try:
        df = yf.Ticker(t).history(period="30d")
    except Exception:
        return JSONResponse({"error": "No data"}, status_code=404)
    if df.empty:
        return JSONResponse({"error": "No data"}, status_code=404)
    return JSONResponse({
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "close": [round(float(v), 4) for v in df["Close"]],
        "volume": [int(v) for v in df["Volume"]],
    })


@app.get("/api/portfolio")
def get_portfolio():
    prices = {}
    for t in portfolio.positions:
        try:
            prices[t] = float(yf.Ticker(t).fast_info["last_price"])
        except Exception:
            pass
    return JSONResponse(portfolio.get_state(prices))


@app.get("/api/price/{ticker}")
def get_price(ticker: str):
    t = ticker.upper()
    try:
        price = float(yf.Ticker(t).fast_info["last_price"])
        return JSONResponse({"ticker": t, "price": price})
    except Exception:
        return JSONResponse({"error": "Price unavailable"}, status_code=404)


@app.post("/api/trade")
async def post_trade(payload: TradePayload):
    t = payload.ticker.upper()
    side = payload.side.upper()
    amount_usd = payload.amount_usd

    if side not in ("BUY", "SELL"):
        return JSONResponse({"error": "side must be BUY or SELL"}, status_code=400)
    if amount_usd <= 0:
        return JSONResponse({"error": "amount_usd must be positive"}, status_code=400)

    try:
        price = float(yf.Ticker(t).fast_info["last_price"])
    except Exception:
        return JSONResponse({"error": "Price unavailable"}, status_code=503)

    if side == "BUY":
        if amount_usd > portfolio.cash:
            return JSONResponse({"error": "Insufficient cash"}, status_code=400)
        portfolio.buy(t, amount_usd, price)
    else:
        if t not in portfolio.positions:
            return JSONResponse({"error": "No position"}, status_code=400)
        portfolio.sell(t, amount_usd, price)

    portfolio.save()

    prices = {}
    for held in portfolio.positions:
        try:
            prices[held] = float(yf.Ticker(held).fast_info["last_price"])
        except Exception:
            pass
    state = portfolio.get_state(prices)
    last_trade = portfolio.trades[-1] if portfolio.trades else None
    update_payload = {"type": "portfolio_update", **state, "last_trade": last_trade}

    await broadcast(update_payload)
    return JSONResponse(update_payload)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    await ws.send_text(json.dumps({
        "type": "init",
        "tickers": watched_tickers,
        "demo_mode": DEMO_MODE,
        "refresh_interval": refresh_interval,
    }))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in clients:
            clients.remove(ws)


@app.get("/")
def serve_dashboard():
    return FileResponse("dashboard.html")


if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
