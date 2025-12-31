from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from datetime import datetime
import asyncio

# Import your trading agents
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.dataflows.config import get_config
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

config = get_config()

# Create FastAPI app instance
app = FastAPI(
    title="TradingAgents API",
    description="API for TradingAgents financial trading framework",
    version="0.1.0"
)

# Pydantic models for request/response
class TradingRequest(BaseModel):
    symbol: str
    date: str

class TradingResponse(BaseModel):
    symbol: str
    date: str
    decision: dict
    timestamp: str
    status: str

# Initialize trading agent once at startup
def create_trading_agent():
    """Create trading agent with fixed configuration"""
    return TradingAgentsGraph(debug=True, config=config)

# Create the trading agent instance once
trading_agent = create_trading_agent()

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to TradingAgents API"}

@app.get("/ping")
async def ping():
    """Simple ping endpoint that returns pong"""
    return {"message": "pong"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "tradingagents-api"
    }

@app.post("/trading/analyze", response_model=TradingResponse)
async def analyze_trading_decision(request: TradingRequest):
    """
    Analyze trading decision for a given symbol and date
    
    Example usage:
    POST /trading/analyze
    {
        "symbol": "NVDA",
        "date": "2024-05-10"
    }
    """
    try:
        # Run the analysis (this might take a while, so we run it in a thread pool)
        def run_analysis():
            _, decision = trading_agent.propagate(request.symbol, request.date)
            return decision
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        decision = await loop.run_in_executor(None, run_analysis)
        
        return TradingResponse(
            symbol=request.symbol,
            date=request.date,
            decision=decision,
            timestamp=datetime.now().isoformat(),
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trading analysis failed: {str(e)}")


if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "webapp:app",
        host=config.get("APP_HOST", "localhost"),
        port=config.get("APP_PORT", 8000),
        reload=True,
        log_level="info"
    )
