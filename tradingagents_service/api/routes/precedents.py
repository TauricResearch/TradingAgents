from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tradingagents_service.api.dependencies import get_shadow_run_repository
from tradingagents_service.db.repository import ShadowRunRepository
from tradingagents_service.schemas.shadow_runs import PrecedentItem, PrecedentListResponse

router = APIRouter(prefix="/v1/precedents", tags=["precedents"])


def _precedent_item(match) -> PrecedentItem:
    return PrecedentItem(
        run_id=match.run_id,
        ticker=match.ticker,
        trade_date=match.trade_date,
        similarity=match.similarity,
        content_hash=match.content_hash,
        content_text=match.content_text,
        embedding_model=match.embedding_model,
        metadata_json=match.metadata_json,
        created_at=match.created_at,
    )


@router.get("", response_model=PrecedentListResponse)
async def list_precedents(
    ticker: str | None = Query(default=None, min_length=1),
    trade_date: date | None = Query(default=None),
    query_text: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    repo: ShadowRunRepository = Depends(get_shadow_run_repository),
) -> PrecedentListResponse:
    if not hasattr(repo, "search_precedents"):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="precedent search unavailable")
    matches = await repo.search_precedents(
        ticker=ticker,
        before_trade_date=trade_date,
        query_text=query_text,
        limit=limit,
    )
    return PrecedentListResponse(
        query_ticker=ticker,
        query_trade_date=trade_date,
        query_text=query_text,
        precedents=[_precedent_item(match) for match in matches],
    )
