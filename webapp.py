from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import uvicorn
from datetime import datetime

# Import your trading agents
from service import enqueue_analysis
from tradingagents.config import get_config

config = get_config()

# Create FastAPI app instance
app = FastAPI(
    title="TradingAgents API",
    description="API for TradingAgents financial trading framework",
    version="0.1.0"
)

class TradingAnalyzeRequest(BaseModel):
    symbol: str
    date: str

class TradingAnalyzeResponse(BaseModel):
    symbol: str
    date: str
    job_id: str
    timestamp: str
    status: str

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

@app.post("/v1/trading/analyze", response_model=TradingAnalyzeResponse, status_code=status.HTTP_202_ACCEPTED,)
async def analyze_trading_decision(request: TradingAnalyzeRequest):
    """
    Analyze trading decision for a given symbol and date
    
    Example usage:
    POST /trading/analyze
    {
        "symbol": "BTC/USDT",
        "date": "2024-05-10"
    }
    """
    response = enqueue_analysis(request.symbol, request.date)
    print(f"INFO: Enqueue response: {response}")

    if response.status == "error":
        raise HTTPException(status_code=500, detail=response.message)
    
    return TradingAnalyzeResponse(
        symbol=request.symbol,
        date=request.date,
        job_id=response.job_id,
        timestamp=datetime.now().isoformat(),
        status=response.status
    )


if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "webapp:app",
        host=config.get("APP_HOST", "localhost"),
        port=config.get("APP_PORT", 8000),
        reload=True,
        log_level="info"
    )
