"""Risk Officer: deterministic + LLM hybrid that can hard-veto a trade.

Variation 3 of the experiment. Instead of three personality debaters
arguing about a position, an independent risk officer:

1. Computes deterministic risk checks from price history (realised
   vol, drawdown, momentum sign).
2. Asks the LLM to write a short risk memo using those numbers.
3. Applies hard rules that can force a veto regardless of what the
   trader proposed:
   - 30-day annualised vol > 80% → cap at Hold
   - 60-day max drawdown < -25% → cap at Hold

The veto is a *hard floor on caution*: a Buy can become a Hold, but a
Sell will never become a Buy. The LLM-written memo is what the
Portfolio Manager reads as the risk-debate history.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import yfinance as yf

VETO_VOL_THRESHOLD = 0.80
VETO_DRAWDOWN_THRESHOLD = -0.25


def _compute_risk_metrics(ticker: str, trade_date: str) -> Dict[str, Optional[float]]:
    """Compute realised vol and max drawdown for the 60 days ending on trade_date.

    Returns dict with vol_30d_annualised, max_drawdown_60d, momentum_30d_sign.
    All values may be None if price data is unavailable.
    """
    try:
        end = datetime.strptime(trade_date, "%Y-%m-%d")
        start = end - timedelta(days=120)
        hist = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"), end=trade_date)
        if len(hist) < 30:
            return {"vol_30d_annualised": None, "max_drawdown_60d": None, "momentum_30d_sign": None}
        close = hist["Close"].astype(float)
        returns = close.pct_change().dropna()
        vol = float(returns.tail(30).std() * np.sqrt(252)) if len(returns) >= 30 else None
        recent = close.tail(60)
        if len(recent) >= 2:
            running_max = recent.cummax()
            dd = float((recent / running_max - 1.0).min())
        else:
            dd = None
        if len(close) >= 31:
            mom_sign = 1.0 if close.iloc[-1] > close.iloc[-30] else -1.0
        else:
            mom_sign = None
        return {"vol_30d_annualised": vol, "max_drawdown_60d": dd, "momentum_30d_sign": mom_sign}
    except Exception:
        return {"vol_30d_annualised": None, "max_drawdown_60d": None, "momentum_30d_sign": None}


def _veto_reason(metrics: Dict[str, Optional[float]]) -> Optional[str]:
    vol = metrics.get("vol_30d_annualised")
    dd = metrics.get("max_drawdown_60d")
    if vol is not None and vol > VETO_VOL_THRESHOLD:
        return f"30-day annualised vol of {vol:.0%} exceeds the {VETO_VOL_THRESHOLD:.0%} ceiling."
    if dd is not None and dd < VETO_DRAWDOWN_THRESHOLD:
        return f"60-day drawdown of {dd:.0%} is worse than the {VETO_DRAWDOWN_THRESHOLD:.0%} floor."
    return None


def create_risk_officer(llm):
    def risk_officer_node(state) -> dict:
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        trader_decision = state["trader_investment_plan"]

        metrics = _compute_risk_metrics(ticker, trade_date)
        veto = _veto_reason(metrics)

        veto_block = (
            f"\n\n**HARD VETO TRIGGERED**: {veto} The PM must cap any rating at Hold.\n"
            if veto
            else "\n\n**No hard veto triggered** by deterministic risk thresholds.\n"
        )

        metrics_lines = []
        if metrics["vol_30d_annualised"] is not None:
            metrics_lines.append(f"- 30d annualised vol: {metrics['vol_30d_annualised']:.1%}")
        if metrics["max_drawdown_60d"] is not None:
            metrics_lines.append(f"- 60d max drawdown: {metrics['max_drawdown_60d']:.1%}")
        if metrics["momentum_30d_sign"] is not None:
            sign = "positive" if metrics["momentum_30d_sign"] > 0 else "negative"
            metrics_lines.append(f"- 30d momentum sign: {sign}")
        metrics_block = "\n".join(metrics_lines) if metrics_lines else "- (price data unavailable)"

        prompt = f"""You are an independent Risk Officer. You read the trader's proposal and the deterministic risk metrics, then write a short risk memo for the Portfolio Manager.

Trader's proposal:
{trader_decision}

Deterministic risk metrics (computed from price history):
{metrics_block}
{veto_block}
Write a focused 4–6 sentence memo:
- What the metrics imply for sizing.
- One or two non-quantitative risks that matter for this trade.
- Whether you concur, want a smaller size, or recommend a hold.

Be specific. Do not perform a debate."""

        response = llm.invoke(prompt)
        memo = f"Risk Officer:\n{response.content}"
        if veto:
            memo += f"\n\n[HARD VETO ENFORCED — {veto}]"

        risk_debate_state = state["risk_debate_state"]
        new_state = {
            "history": memo,
            "aggressive_history": memo,
            "conservative_history": memo,
            "neutral_history": memo,
            "latest_speaker": "RiskOfficer",
            "current_aggressive_response": memo,
            "current_conservative_response": memo,
            "current_neutral_response": memo,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state.get("count", 0) + 1,
        }
        return {"risk_debate_state": new_state, "risk_officer_veto": veto or ""}

    return risk_officer_node
