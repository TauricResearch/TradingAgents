"""Portfolio simulation engine + REST.

The model is intentionally simple — we're not pretending to be Monte Carlo
quant infrastructure. Given a scenario:

    {
        "starting_capital": 10000,
        "trades": [
            {"ticker": "NVDA", "shares": 10, "entry_price": 198,
             "exit_strategy": {"hold_days": 30}}
        ],
    }

…we estimate trailing return + volatility from yfinance for each ticker,
project forward for the holding period (linear drift with a normal-noise
band), and compare to a SPY-only baseline over the same window.

POST /sim/run         — run a scenario, return result (also saved)
GET  /sim             — list saved simulations
GET  /sim/{id}        — fetch one saved simulation
DELETE /sim/{id}      — delete
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gui import storage

router = APIRouter(prefix="/sim", tags=["simulation"])


# ---- Schemas ---------------------------------------------------------

class SimTrade(BaseModel):
    ticker: str
    shares: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    hold_days: int = Field(default=30, ge=1, le=365 * 3)


class SimRunRequest(BaseModel):
    name: Optional[str] = None
    base_run_id: Optional[str] = None
    starting_capital: float = Field(default=10000.0)
    trades: List[SimTrade]
    # Look-back for drift / vol estimate.
    history_days: int = Field(default=180, ge=30, le=365 * 5)


class SimPoint(BaseModel):
    day: int
    portfolio: float
    baseline_spy: float
    portfolio_low: float
    portfolio_high: float


class SimResult(BaseModel):
    name: str
    starting_capital: float
    expected_final_value: float
    expected_return_pct: float
    baseline_final_value: float
    baseline_return_pct: float
    alpha_pct: float
    horizon_days: int
    points: List[SimPoint]
    per_trade: List[Dict[str, Any]]


class SimRow(BaseModel):
    id: int
    name: Optional[str] = None
    base_run_id: Optional[str] = None
    ticker: Optional[str] = None
    created_at: str


class SimDetail(SimRow):
    scenario: Dict[str, Any]
    result: SimResult


# ---- Engine ---------------------------------------------------------

def _stats(ticker: str, days: int) -> tuple[float, float]:
    """Return (annualised mu, annualised sigma) from daily log returns."""
    end = date.today()
    start = end - timedelta(days=int(days * 1.5) + 10)  # buffer for non-trading days
    df = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(),
                                   auto_adjust=True)
    if df.empty or len(df) < 5:
        return 0.0, 0.20  # 20% vol fallback
    close = df["Close"].astype(float)
    log_returns = np.log(close / close.shift(1)).dropna()
    if len(log_returns) < 2:
        return 0.0, 0.20
    daily_mu = float(log_returns.mean())
    daily_sigma = float(log_returns.std(ddof=1))
    # Annualise (252 trading days).
    return daily_mu * 252, daily_sigma * np.sqrt(252)


def _simulate(req: SimRunRequest) -> SimResult:
    horizon = max(t.hold_days for t in req.trades)

    # Per-trade stats.
    per_trade_stats: List[Dict[str, Any]] = []
    for t in req.trades:
        mu, sigma = _stats(t.ticker, req.history_days)
        per_trade_stats.append({
            "ticker": t.ticker, "shares": t.shares, "entry_price": t.entry_price,
            "hold_days": t.hold_days, "mu_annual": mu, "sigma_annual": sigma,
            "cost": t.shares * t.entry_price,
        })
    spy_mu, spy_sigma = _stats("SPY", req.history_days)

    # Daily projection.
    daily_factor = 1.0 / 252
    points: List[SimPoint] = []
    total_invested = sum(s["cost"] for s in per_trade_stats)
    cash = max(0.0, req.starting_capital - total_invested)

    for day in range(horizon + 1):
        # Each trade's expected price after `day` days (or hold_days if shorter).
        port_value = cash
        port_low = cash
        port_high = cash
        for t, s in zip(req.trades, per_trade_stats):
            d = min(day, t.hold_days)
            drift = np.exp(s["mu_annual"] * d * daily_factor)
            band = s["sigma_annual"] * np.sqrt(d * daily_factor)  # 1-sigma band
            mid_price = t.entry_price * drift
            low_price = t.entry_price * drift * np.exp(-band)
            high_price = t.entry_price * drift * np.exp(band)
            port_value += t.shares * mid_price
            port_low += t.shares * low_price
            port_high += t.shares * high_price

        baseline = req.starting_capital * np.exp(spy_mu * day * daily_factor)
        points.append(SimPoint(
            day=day,
            portfolio=round(port_value, 2),
            baseline_spy=round(baseline, 2),
            portfolio_low=round(port_low, 2),
            portfolio_high=round(port_high, 2),
        ))

    final = points[-1]
    expected_return_pct = (final.portfolio / req.starting_capital - 1) * 100
    baseline_return_pct = (final.baseline_spy / req.starting_capital - 1) * 100

    return SimResult(
        name=req.name or f"sim @ {datetime.utcnow().isoformat(timespec='seconds')}Z",
        starting_capital=req.starting_capital,
        expected_final_value=final.portfolio,
        expected_return_pct=expected_return_pct,
        baseline_final_value=final.baseline_spy,
        baseline_return_pct=baseline_return_pct,
        alpha_pct=expected_return_pct - baseline_return_pct,
        horizon_days=horizon,
        points=points,
        per_trade=per_trade_stats,
    )


# ---- Endpoints ------------------------------------------------------

@router.post("/run", response_model=SimDetail)
def run_simulation(req: SimRunRequest) -> SimDetail:
    if not req.trades:
        raise HTTPException(status_code=400, detail="at least one trade required")
    result = _simulate(req)
    sid = storage.add_simulation(
        name=result.name,
        base_run_id=req.base_run_id,
        ticker=req.trades[0].ticker if req.trades else None,
        scenario_json=req.model_dump_json(),
        result_json=result.model_dump_json(),
    )
    row = storage.get_simulation(sid)
    return SimDetail(
        id=sid,
        name=row["name"],
        base_run_id=row.get("base_run_id"),
        ticker=row.get("ticker"),
        created_at=row["created_at"],
        scenario=req.model_dump(),
        result=result,
    )


@router.get("", response_model=List[SimRow])
def list_sims() -> List[SimRow]:
    return [SimRow(**r) for r in storage.list_simulations()]


@router.get("/{sid}", response_model=SimDetail)
def get_sim(sid: int) -> SimDetail:
    row = storage.get_simulation(sid)
    if not row:
        raise HTTPException(status_code=404, detail="simulation not found")
    return SimDetail(
        id=row["id"],
        name=row["name"],
        base_run_id=row.get("base_run_id"),
        ticker=row.get("ticker"),
        created_at=row["created_at"],
        scenario=json.loads(row["scenario_json"]),
        result=SimResult.model_validate_json(row["result_json"]),
    )


@router.delete("/{sid}")
def delete_sim(sid: int) -> dict:
    storage.delete_simulation(sid)
    return {"deleted": sid}
