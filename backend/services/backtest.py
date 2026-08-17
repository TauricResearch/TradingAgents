from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.integrations.market_data import get_market_provider
from backend.models import Analysis, Backtest, Decision
from backend.schemas import BacktestCreate


def evaluate_saved_analyses(db: Session, user_id: str, body: BacktestCreate) -> dict:
    """Evaluate stored AI decisions against later prices. Does not invent trades."""
    rows = (
        db.query(Analysis)
        .filter(
            Analysis.user_id == user_id,
            Analysis.status == "completed",
            Analysis.analysis_date >= body.start_date,
            Analysis.analysis_date <= body.end_date,
        )
        .order_by(Analysis.analysis_date.asc())
        .all()
    )
    provider = get_market_provider()
    trades = []
    wins = 0
    returns: list[float] = []
    equity = [100000.0]
    for analysis in rows:
        decision = analysis.final_decision
        if not decision:
            continue
        outcome = _forward_return(provider, analysis.symbol, analysis.analysis_date, body.holding_days)
        if outcome is None:
            trades.append(
                {
                    "symbol": analysis.symbol,
                    "date": analysis.analysis_date,
                    "decision": decision,
                    "confidence": analysis.confidence,
                    "return": None,
                    "correct": None,
                }
            )
            continue
        signed = outcome if decision == "BUY" else (-outcome if decision == "SELL" else 0.0)
        returns.append(signed)
        if decision == "HOLD":
            correct = None
        else:
            correct = (decision == "BUY" and outcome > 0) or (decision == "SELL" and outcome < 0)
            if correct:
                wins += 1
        equity.append(equity[-1] * (1 + signed))
        trades.append(
            {
                "symbol": analysis.symbol,
                "date": analysis.analysis_date,
                "decision": decision,
                "confidence": analysis.confidence,
                "return": signed,
                "actual_return": outcome,
                "correct": correct,
            }
        )
    buy_hold = _index_buy_hold(provider, body.start_date, body.end_date)
    stats = _stats(equity, returns, wins, len([t for t in trades if t.get("correct") is not None]))
    result = {
        "universe": body.universe,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "initial_capital": 100000,
        "final_capital": equity[-1],
        "number_of_decisions": len(trades),
        "ai_strategy": stats,
        "buy_hold": buy_hold,
        "equity_curve": equity,
        "trades": trades,
        "note": "This evaluation uses your saved AI analyses only. It does not claim live profitability.",
    }
    record = Backtest(
        user_id=user_id,
        universe=body.universe,
        start_date=body.start_date,
        end_date=body.end_date,
        configuration=json.dumps(body.model_dump()),
        results=json.dumps(result, default=str),
        status="completed",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result["id"] = record.id
    return result


def _forward_return(provider, symbol: str, start: str, holding_days: int) -> float | None:
    try:
        candles = provider.history(symbol, "3M")
    except Exception:
        return None
    if not candles:
        return None
    start_dt = datetime.fromisoformat(start)
    after = [c for c in candles if datetime.fromisoformat(c.time[:10]) >= start_dt]
    if len(after) < 2:
        return None
    end_idx = min(holding_days, len(after) - 1)
    start_px = after[0].close
    end_px = after[end_idx].close
    if not start_px:
        return None
    return (end_px - start_px) / start_px


def _index_buy_hold(provider, start: str, end: str) -> dict:
    try:
        candles = provider.history("^NSEI", "5Y")
        window = [c for c in candles if start <= c.time[:10] <= end]
        if len(window) < 2:
            return {"total_return": None, "label": "NIFTY 50 buy & hold"}
        ret = (window[-1].close - window[0].close) / window[0].close
        return {"total_return": ret, "label": "NIFTY 50 buy & hold", "start": window[0].close, "end": window[-1].close}
    except Exception:
        return {"total_return": None, "label": "NIFTY 50 buy & hold"}


def _stats(equity: list[float], returns: list[float], wins: int, decided: int) -> dict:
    if not equity:
        return {}
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = min(max_dd, (value - peak) / peak if peak else 0)
    total = equity[-1] / equity[0] - 1 if equity[0] else 0
    avg = sum(returns) / len(returns) if returns else 0
    var = sum((r - avg) ** 2 for r in returns) / len(returns) if returns else 0
    sharpe = (avg / (var ** 0.5) * (252 ** 0.5)) if var > 0 else None
    return {
        "total_return": total,
        "cagr": None,
        "win_rate": (wins / decided) if decided else None,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "number_of_decisions": decided,
    }
