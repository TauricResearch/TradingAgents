import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.core.database import get_db
from backend.models.analysis import AnalysisResult
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.analysis import (
    AnalysisRunRequest, AnalysisRunResponse,
    AnalysisResultRead, AnalysisListItem,
)
from backend.schemas.portfolio_analysis import (
    MultiTickerRunRequest, MultiTickerRunResponse,
    MultiTickerListItem, MultiTickerResultRead,
)
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.api.deps import get_current_user
from backend.api.settings import _get_or_create_settings
from backend.core.utils import safe_ticker_component

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
_logger = logging.getLogger(__name__)


@router.post("/run", response_model=AnalysisRunResponse)
async def run_analysis(
    body: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Validate ticker against path traversal
    try:
        safe_ticker_component(body.ticker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    settings = await _get_or_create_settings(db)

    import uuid
    task_id = str(uuid.uuid4())

    # Run analysis in background so the HTTP response returns immediately
    async def _bg():
        async with __import__("backend.core.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as bg_db:
            try:
                from backend.services.analysis_service import run_analysis as _run
                from backend.services.execution.factory import get_trader
                task_id_out, row = await _run(
                    body.ticker, body.trade_date, body.asset_type, settings, bg_db, "manual",
                    task_id=task_id,   # ← same id client's WS is connected to
                )
                await bg_db.commit()

                # Execute trade if warranted
                if row.signal in ("Buy", "Overweight", "Sell", "Underweight"):
                    from backend.services.execution.factory import get_trader
                    from backend.services.execution.base import OrderRequest
                    try:
                        trader = get_trader(
                            mode=settings.trading_mode,
                            broker=settings.active_broker,
                            portfolio_id=1,
                            initial_capital=100_000.0,
                            db=None,
                        )
                        price = trader.get_current_price(body.ticker) or 0.0
                        action = "BUY" if row.signal in ("Buy", "Overweight") else "SELL"
                        if price > 0:
                            quantity = (settings.max_risk_per_trade_pct / 100 * 100_000) / price
                            req = OrderRequest(
                                ticker=body.ticker,
                                action=action,
                                quantity=quantity,
                                reference_price=price,
                                ai_signal=row.signal or "",
                                ai_reasoning=row.final_decision[:500],
                            )
                            result = trader.place_order(req)
                            _logger.info("Order placed: %s", result)
                    except Exception as e:
                        _logger.warning("Order execution skipped: %s", e)
            except Exception as exc:
                # run_analysis already sends WS error + closes task for errors
                # inside its own try block. This catch handles any unexpected
                # failures that slip through (e.g. DB commit error after analysis).
                _logger.error("Background analysis failed: %s", exc, exc_info=True)
                try:
                    from backend.core.websocket import ws_manager as _wm
                    await _wm.send(task_id, {"type": "error", "message": f"Analiz hatası: {exc}"})
                    await _wm.close_task(task_id)
                except Exception:
                    pass
                await bg_db.rollback()

    background_tasks.add_task(_bg)

    return AnalysisRunResponse(task_id=task_id, ticker=body.ticker, trade_date=body.trade_date)


@router.get("/history", response_model=list[AnalysisListItem])
async def list_analysis(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(AnalysisResult).order_by(desc(AnalysisResult.created_at)).limit(limit).offset(offset)
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{task_id}/cancel")
async def cancel_analysis(
    task_id: str,
    _: User = Depends(get_current_user),
):
    """Cancel a running analysis task."""
    from backend.services.analysis_service import cancel_analysis as _cancel
    cancelled = await _cancel(task_id)
    return {"cancelled": cancelled, "task_id": task_id}


@router.get("/{analysis_id}", response_model=AnalysisResultRead)
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(AnalysisResult).where(AnalysisResult.id == analysis_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return row


# ── Multi-ticker (portfolio) analysis ────────────────────────────────────────

@router.post("/run-portfolio", response_model=MultiTickerRunResponse)
async def run_portfolio(
    body: MultiTickerRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Start a multi-ticker portfolio analysis in the background."""
    tickers = [t.upper() for t in body.tickers]
    for ticker in tickers:
        try:
            safe_ticker_component(ticker)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid ticker {ticker}: {e}")

    settings = await _get_or_create_settings(db)

    import uuid
    task_id = str(uuid.uuid4())

    async def _bg():
        async with __import__("backend.core.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as bg_db:
            try:
                from backend.services.analysis_service import run_portfolio_analysis
                await run_portfolio_analysis(tickers, body.trade_date, body.asset_type, settings, bg_db, "manual")
                await bg_db.commit()
            except Exception as exc:
                _logger.error("Portfolio analysis failed: %s", exc, exc_info=True)
                await bg_db.rollback()

    background_tasks.add_task(_bg)
    return MultiTickerRunResponse(task_id=task_id, tickers=tickers, trade_date=body.trade_date)


@router.get("/portfolio-history", response_model=list[MultiTickerListItem])
async def list_portfolio_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(MultiTickerAnalysis).order_by(desc(MultiTickerAnalysis.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        MultiTickerListItem(
            id=r.id,
            tickers=r.tickers,
            trade_date=r.trade_date,
            asset_type=r.asset_type,
            triggered_by=r.triggered_by,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/portfolio/{portfolio_id}", response_model=MultiTickerResultRead)
async def get_portfolio_analysis(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(MultiTickerAnalysis).where(MultiTickerAnalysis.id == portfolio_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio analysis not found")
    return MultiTickerResultRead(
        id=row.id,
        tickers=row.tickers,
        trade_date=row.trade_date,
        asset_type=row.asset_type,
        analysis_ids=row.analysis_ids,
        super_portfolio_report=row.super_portfolio_report,
        triggered_by=row.triggered_by,
        created_at=row.created_at,
    )
