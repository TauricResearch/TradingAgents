"""FastAPI server for Nifty50 AI recommendations."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import database as db

app = FastAPI(
    title="Nifty50 AI API",
    description="API for Nifty 50 stock recommendations",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StockAnalysis(BaseModel):
    symbol: str
    company_name: str
    decision: Optional[str] = None
    confidence: Optional[str] = None
    risk: Optional[str] = None
    raw_analysis: Optional[str] = None


class TopPick(BaseModel):
    rank: int
    symbol: str
    company_name: str
    decision: str
    reason: str
    risk_level: str


class StockToAvoid(BaseModel):
    symbol: str
    company_name: str
    reason: str


class Summary(BaseModel):
    total: int
    buy: int
    sell: int
    hold: int


class DailyRecommendation(BaseModel):
    date: str
    analysis: dict[str, StockAnalysis]
    summary: Summary
    top_picks: list[TopPick]
    stocks_to_avoid: list[StockToAvoid]


class SaveRecommendationRequest(BaseModel):
    date: str
    analysis: dict
    summary: dict
    top_picks: list
    stocks_to_avoid: list


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "Nifty50 AI API",
        "version": "1.0.0",
        "endpoints": {
            "GET /recommendations": "Get all recommendations",
            "GET /recommendations/latest": "Get latest recommendation",
            "GET /recommendations/{date}": "Get recommendation by date",
            "GET /stocks/{symbol}/history": "Get stock history",
            "GET /dates": "Get all available dates",
            "POST /recommendations": "Save a new recommendation"
        }
    }


@app.get("/recommendations")
async def get_all_recommendations():
    """Get all daily recommendations."""
    recommendations = db.get_all_recommendations()
    return {"recommendations": recommendations, "count": len(recommendations)}


@app.get("/recommendations/latest")
async def get_latest_recommendation():
    """Get the most recent recommendation."""
    recommendation = db.get_latest_recommendation()
    if not recommendation:
        raise HTTPException(status_code=404, detail="No recommendations found")
    return recommendation


@app.get("/recommendations/{date}")
async def get_recommendation_by_date(date: str):
    """Get recommendation for a specific date (format: YYYY-MM-DD)."""
    recommendation = db.get_recommendation_by_date(date)
    if not recommendation:
        raise HTTPException(status_code=404, detail=f"No recommendation found for {date}")
    return recommendation


@app.get("/stocks/{symbol}/history")
async def get_stock_history(symbol: str):
    """Get historical recommendations for a specific stock."""
    history = db.get_stock_history(symbol.upper())
    return {"symbol": symbol.upper(), "history": history, "count": len(history)}


@app.get("/dates")
async def get_available_dates():
    """Get all dates with recommendations."""
    dates = db.get_all_dates()
    return {"dates": dates, "count": len(dates)}


@app.post("/recommendations")
async def save_recommendation(request: SaveRecommendationRequest):
    """Save a new daily recommendation."""
    try:
        db.save_recommendation(
            date=request.date,
            analysis_data=request.analysis,
            summary=request.summary,
            top_picks=request.top_picks,
            stocks_to_avoid=request.stocks_to_avoid
        )
        return {"message": f"Recommendation for {request.date} saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "database": "connected"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
