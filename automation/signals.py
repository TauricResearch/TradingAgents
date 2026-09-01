from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yfinance as yf

from tradingagents.agents.utils.rating import parse_rating


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    close: float
    atr: float
    currency: str | None = None


@dataclass(frozen=True)
class TradeSignal:
    ticker: str
    analysis_date: str
    rating: str
    action: str
    position_bias: str
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    confidence: str
    reasons: list[str]
    source_report_path: str
    generated_at: str
    disclaimer: str = "Información generada para apoyo operativo; no es recomendación financiera."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_signal(
    *,
    ticker: str,
    analysis_date: str,
    final_state: dict[str, Any],
    report_path: Path,
    risk_config: dict[str, Any],
    market_symbol: str | None = None,
    snapshot: MarketSnapshot | None = None,
) -> TradeSignal:
    final_decision = str(final_state.get("final_trade_decision") or "")
    trader_plan = str(final_state.get("trader_investment_plan") or "")
    rating = parse_rating(final_decision)
    snapshot = snapshot or fetch_market_snapshot(
        market_symbol or ticker,
        atr_period=int(risk_config.get("atr_period", 14)),
    )

    action, position_bias = _action_from_rating(rating, str(risk_config.get("portfolio_state", "unknown")))
    entry = _round_price(snapshot.close)
    stop_mult = float(risk_config.get("stop_atr_multiple", 1.5))
    target_mult = float(risk_config.get("take_profit_atr_multiple", 2.5))
    min_rr = float(risk_config.get("min_reward_risk", 1.5))

    llm_entry = _extract_number(trader_plan, "Entry Price")
    llm_stop = _extract_number(trader_plan, "Stop Loss")
    llm_target = _extract_number(final_decision, "Price Target")
    if llm_entry and llm_entry > 0:
        entry = _round_price(llm_entry)

    if action == "BUY":
        stop = _round_price(llm_stop) if llm_stop and llm_stop < entry else _round_price(entry - stop_mult * snapshot.atr)
        target = _round_price(llm_target) if llm_target and llm_target > entry else _round_price(entry + target_mult * snapshot.atr)
        rr = _risk_reward(entry, stop, target, long=True)
        if rr is not None and rr < min_rr:
            action = "HOLD"
            position_bias = "watchlist"
    elif action == "SELL":
        stop = _round_price(entry + stop_mult * snapshot.atr)
        target = _round_price(entry - target_mult * snapshot.atr)
        rr = _risk_reward(entry, stop, target, long=False)
    else:
        stop = _round_price(entry - stop_mult * snapshot.atr)
        target = _round_price(entry + target_mult * snapshot.atr)
        rr = _risk_reward(entry, stop, target, long=True)

    reasons = [
        f"Portfolio Manager rating: {rating}.",
        f"Precio base: {entry}. ATR usado: {_round_price(snapshot.atr)}.",
        f"Regla de riesgo: stop {stop_mult}x ATR, take profit {target_mult}x ATR.",
    ]
    if action == "HOLD" and rating in {"Buy", "Overweight"}:
        reasons.append(f"Señal alcista degradada a HOLD por reward/risk menor a {min_rr}.")

    return TradeSignal(
        ticker=ticker,
        analysis_date=analysis_date,
        rating=rating,
        action=action,
        position_bias=position_bias,
        entry_price=entry if action in {"BUY", "SELL"} else None,
        stop_loss=stop,
        take_profit=target,
        risk_reward=rr,
        confidence=_confidence_from_rating(rating, rr, min_rr),
        reasons=reasons,
        source_report_path=str(report_path),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def fetch_market_snapshot(ticker: str, *, atr_period: int = 14) -> MarketSnapshot:
    history = yf.Ticker(ticker).history(period="6mo", auto_adjust=False)
    if history.empty or len(history) < atr_period + 1:
        raise RuntimeError(f"No hay suficiente historia de precios para {ticker}.")

    high = history["High"].astype(float)
    low = history["Low"].astype(float)
    close = history["Close"].astype(float)
    previous_close = close.shift(1)
    true_range = (high - low).to_frame("hl")
    true_range["hc"] = (high - previous_close).abs()
    true_range["lc"] = (low - previous_close).abs()
    atr = true_range.max(axis=1).rolling(atr_period).mean().dropna().iloc[-1]
    last_close = close.dropna().iloc[-1]
    info = {}
    try:
        info = yf.Ticker(ticker).fast_info or {}
    except Exception:
        info = {}
    currency = getattr(info, "currency", None) or (info.get("currency") if isinstance(info, dict) else None)
    return MarketSnapshot(ticker=ticker, close=float(last_close), atr=float(atr), currency=currency)


def write_signal(signal: TradeSignal, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(signal.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def _action_from_rating(rating: str, portfolio_state: str) -> tuple[str, str]:
    if rating == "Buy":
        return "BUY", "full"
    if rating == "Overweight":
        return "BUY", "partial"
    if rating == "Sell":
        return "SELL", "exit" if portfolio_state == "long" else "avoid"
    if rating == "Underweight":
        return "SELL", "reduce" if portfolio_state == "long" else "avoid"
    return "HOLD", "watchlist"


def _confidence_from_rating(rating: str, rr: float | None, min_rr: float) -> str:
    if rating in {"Buy", "Sell"} and rr is not None and rr >= min_rr:
        return "high"
    if rating in {"Overweight", "Underweight"} and rr is not None and rr >= min_rr:
        return "medium"
    return "low"


def _extract_number(text: str, label: str) -> float | None:
    pattern = re.compile(
        rf"\**\s*{re.escape(label)}\s*\**\s*[:\-]\s*\$?\s*([0-9]+(?:[.,][0-9]+)?)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _risk_reward(entry: float, stop: float, target: float, *, long: bool) -> float | None:
    risk = entry - stop if long else stop - entry
    reward = target - entry if long else entry - target
    if risk <= 0 or reward <= 0:
        return None
    return round(reward / risk, 2)


def _round_price(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), 4)
