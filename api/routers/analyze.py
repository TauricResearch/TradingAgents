from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from api.auth import get_user_claims_async
from api.scheduler import scheduler

router = APIRouter(tags=["analyze"])


@router.post("/signals-ms/analyze")
async def analyze_on_demand(
    request: Request,
    background_tasks: BackgroundTasks,
    ticker: str = Query(..., description="Ticker to analyze (e.g. AAPL, BTC)"),
    asset_type: str = Query("stocks", description="'stocks' or 'crypto'"),
):
    _, tier = await get_user_claims_async(request)
    if tier != "pro":
        raise HTTPException(
            status_code=403, detail="On-demand analysis requires Pro tier"
        )
    ticker_upper = ticker.strip().upper()
    background_tasks.add_task(
        scheduler.execute_agent_run, ticker_upper, asset_type.lower(), None
    )
    return {"status": "triggered", "ticker": ticker_upper, "asset_type": asset_type}
