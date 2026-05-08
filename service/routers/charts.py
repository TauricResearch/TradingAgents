"""Ticker vs index comparison charts (using existing gui.charts module)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query

from gui import charts as charts_mod
from service.schemas import ChartComparisonResponse, ChartPoint

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/comparison", response_model=ChartComparisonResponse)
def comparison(
    ticker: str = Query(...),
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    days_back: int = 90,
    days_forward: int = 180,
    benchmarks: List[str] = Query(default=["SPY", "QQQ"]),
) -> ChartComparisonResponse:
    df = charts_mod.build_comparison_frame(
        ticker, trade_date,
        days_back=days_back, days_forward=days_forward,
        benchmarks=tuple(benchmarks),
    )
    points: list[ChartPoint] = []
    if df is not None and not df.empty:
        for ts, row in df.iterrows():
            points.append(ChartPoint(
                date=ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                values={str(k): float(v) for k, v in row.items() if v == v},  # filters NaN
            ))

    rt_df = charts_mod.realised_returns_table(ticker, trade_date)
    rt_records = [
        {str(k): str(v) for k, v in record.items()}
        for record in rt_df.to_dict(orient="records")
    ] if rt_df is not None else None

    return ChartComparisonResponse(
        ticker=ticker,
        trade_date=trade_date,
        benchmarks=benchmarks,
        points=points,
        realised_returns=rt_records,
    )
