"""
API route definitions for TradingAgentsX Backend
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import logging
import threading

from backend.app.models.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    ConfigResponse,
    HealthResponse,
    Ticker,
    TaskCreatedResponse,
    TaskStatusResponse,
    DownloadRequest,
)
from backend.app.services.trading_service import TradingService
from backend.app.services.task_manager import task_manager
from backend.app.api.dependencies import get_trading_service
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/api", tags=["TradingAgentsX"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    from backend.app.services.redis_client import is_redis_available
    
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=datetime.now().isoformat(),
        redis_connected=is_redis_available(),
    )


@router.get("/config", response_model=ConfigResponse)
async def get_config(service: TradingService = Depends(get_trading_service)):
    """Get available configuration options"""
    return ConfigResponse(
        available_analysts=service.get_available_analysts(),
        available_llms=service.get_available_llms(),
        default_config=service.get_default_config(),
    )


@router.post("/analyze", response_model=TaskCreatedResponse)
async def run_analysis(
    request: AnalysisRequest,
    service: TradingService = Depends(get_trading_service),
):
    """
    Start an async trading analysis task.
    
    This endpoint creates an async task and returns immediately with a task ID.
    Use the /api/task/{task_id} endpoint to check the status and get results.
    
    Args:
        request: Analysis request configuration
        service: Trading service instance (injected)
    
    Returns:
        TaskCreatedResponse: Task ID and initial status
    """
    logger.info(f"Creating analysis task for {request.ticker} on {request.analysis_date}")
    
    # Create task in Redis
    task_id = task_manager.create_task({
        "ticker": request.ticker,
        "analysis_date": request.analysis_date,
    })
    
    # Start background analysis
    def run_background_analysis():
        import asyncio
        
        try:
            task_manager.update_task_status(
                task_id,
                "running",
                progress="Starting analysis..."
            )
            
            # Run async function in sync context
            result = asyncio.run(service.run_analysis(
                ticker=request.ticker,
                analysis_date=request.analysis_date,
                analysts=request.analysts,
                research_depth=request.research_depth,
                market_type=request.market_type or "us",  # 預設美股
                deep_think_llm=request.deep_think_llm,
                quick_think_llm=request.quick_think_llm,
                openai_api_key=request.openai_api_key or "",  # Pass empty string if None, service handles it
                openai_base_url=request.openai_base_url,
                quick_think_base_url=request.quick_think_base_url,
                deep_think_base_url=request.deep_think_base_url,
                quick_think_api_key=request.quick_think_api_key or "",
                deep_think_api_key=request.deep_think_api_key or "",
                embedding_base_url=request.embedding_base_url,
                embedding_api_key=request.embedding_api_key or "",
                alpha_vantage_api_key=request.alpha_vantage_api_key or "",
                finmind_api_key=request.finmind_api_key or "",
            ))
            
            # Check for errors in result
            if "status" in result and result["status"] == "error":
                task_manager.set_task_error(
                    task_id,
                    error=result.get("message", "Analysis failed")
                )
            else:
                task_manager.set_task_result(task_id, result=result)
                
        except Exception as e:
            logger.error(f"Analysis task {task_id} failed: {str(e)}", exc_info=True)
            task_manager.set_task_error(
                task_id,
                error=str(e)
            )
    
    # Start background thread
    thread = threading.Thread(target=run_background_analysis, daemon=True)
    thread.start()
    
    return TaskCreatedResponse(
        task_id=task_id,
        status="pending",
        message="Analysis task created successfully"
    )


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status of an analysis task.
    
    Args:
        task_id: Task identifier
    
    Returns:
        TaskStatusResponse: Current task status and results if completed
    
    Raises:
        HTTPException: If task not found
    """
    task = task_manager.get_task_status(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return TaskStatusResponse(**task)


@router.delete("/task/{task_id}/cleanup")
async def cleanup_task(task_id: str):
    """
    Manually cleanup a completed/failed task from Redis storage.
    
    This endpoint allows the frontend to proactively delete task data
    after the user has saved the results locally or to cloud storage.
    This helps keep Redis storage clean and reduces memory usage.
    
    Note: Tasks are also automatically cleaned up 10 minutes after
    completion/failure, so calling this endpoint is optional but recommended.
    
    Args:
        task_id: Task identifier
    
    Returns:
        Success message
    
    Raises:
        HTTPException: If task not found
    """
    task = task_manager.get_task_status(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Only allow cleanup of completed or failed tasks
    if task.get("status") not in ["completed", "failed"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Can only cleanup completed or failed tasks. Current status: {task.get('status')}"
        )
    
    # Delete from both Redis and in-memory storage
    task_manager.delete_task(task_id)
    logger.info(f"🧹 Task {task_id} manually cleaned up from storage")
    
    return {
        "success": True,
        "message": f"Task {task_id} has been cleaned up from storage",
        "task_id": task_id
    }


@router.get("/tickers")
async def get_tickers():
    """Get list of popular tickers (example endpoint)"""
    return {
        "tickers": [
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "NVDA", "name": "NVIDIA Corporation"},
            {"symbol": "MSFT", "name": "Microsoft Corporation"},
            {"symbol": "GOOGL", "name": "Alphabet Inc."},
            {"symbol": "AMZN", "name": "Amazon.com Inc."},
            {"symbol": "TSLA", "name": "Tesla Inc."},
            {"symbol": "META", "name": "Meta Platforms Inc."},
            {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust"},
            {"symbol": "QQQ", "name": "Invesco QQQ Trust"},
        ]
    }


@router.post("/download/reports")
async def download_reports(request: DownloadRequest):
    """
    Download all analyst reports as a single combined PDF
    
    Creates a professional PDF with:
    - Cover page: Ticker + Analysis Date
    - Table of Contents: Price chart + Analyst list
    - All analyst reports as separate sections
    
    Supports two modes:
    1. Task-based: If task_id is provided, lookup reports from task manager
    2. Direct mode: If no task_id, use the directly provided reports data (for saved history)
    
    Args:
        request: Download request with ticker, date, analysts, and either task_id or direct reports
        
    Returns:
        Single combined PDF file (e.g., AVGO_Combined_Report_2025-12-16.pdf)
    """
    from fastapi.responses import Response
    from backend.app.services.download_service import download_service
    
    # Determine data source: task-based or direct mode
    if request.task_id:
        # Task-based mode: lookup from task manager
        task = task_manager.get_task_status(request.task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {request.task_id} not found")
        
        if task.get("status") != "completed":
            raise HTTPException(status_code=400, detail="Task is not completed yet")
        
        result = task.get("result")
        if not result:
            raise HTTPException(status_code=404, detail="No analysis result found")
        
        reports_data = result.get("reports", {})
        price_data = result.get("price_data")
        price_stats = result.get("price_stats")
    else:
        # Direct mode: use provided reports data
        if not request.reports:
            raise HTTPException(status_code=400, detail="Either task_id or reports data is required")
        
        reports_data = request.reports
        price_data = request.price_data
        price_stats = request.price_stats
    
    # Analyst name mapping
    ANALYST_MAPPING = {
        "market": ("市場分析師", "market_report"),
        "social": ("社群媒體分析師", "sentiment_report"),
        "news": ("新聞分析師", "news_report"),
        "fundamentals": ("基本面分析師", "fundamentals_report"),
        "bull": ("看漲研究員", "investment_debate_state.bull_history"),
        "bear": ("看跌研究員", "investment_debate_state.bear_history"),
        "research_manager": ("研究經理", "investment_debate_state.judge_decision"),
        "trader": ("交易員", "trader_investment_plan"),
        "risky": ("激進分析師", "risk_debate_state.risky_history"),
        "safe": ("保守分析師", "risk_debate_state.safe_history"),
        "neutral": ("中立分析師", "risk_debate_state.neutral_history"),
        "risk_manager": ("風險經理", "risk_debate_state.judge_decision"),
    }
    
    # Helper function to get nested value
    def get_nested_value(obj: dict, path: str):
        keys = path.split('.')
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                return None
        return obj
    
    # Collect reports
    reports_to_download = []
    for analyst_key in request.analysts:
        if analyst_key not in ANALYST_MAPPING:
            continue
        
        analyst_name, report_key = ANALYST_MAPPING[analyst_key]
        report_content = get_nested_value(reports_data, report_key)
        
        if report_content:
            reports_to_download.append({
                "analyst_name": analyst_name,
                "report_content": report_content,
            })
    
    if not reports_to_download:
        raise HTTPException(status_code=404, detail="No reports found for selected analysts")
    
    # Always generate combined PDF
    pdf_bytes, filename = download_service.create_combined_pdf(
        ticker=request.ticker,
        analysis_date=request.analysis_date,
        reports=reports_to_download,
        price_data=price_data,
        price_stats=price_stats,
    )
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

