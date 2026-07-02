#!/usr/bin/env python3
"""Low-token TradingAgents desk wrapper for Y4Y.

This script keeps the useful TradingAgents multi-agent desk, but puts a cheap
code-only scanner in front of it so the expensive graph only runs on finalists.

Usage examples:

  # Scanner only; no LLM calls
  python scripts/y4y_low_token_desk.py --symbols AAPL,NVDA,TSLA,SMH,SPY --scan-only

  # Run TradingAgents only for top finalist(s), with a reduced analyst set
  OPENROUTER_API_KEY=... python scripts/y4y_low_token_desk.py \
      --symbols AAPL,NVDA,TSLA,SMH,SPY --run-agents --max-finalists 1

Outputs JSON to results/y4y_desk/latest.json by default.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass
class ScanResult:
    symbol: str
    score: float
    direction_bias: str
    eligible: bool
    close: float | None = None
    rsi14: float | None = None
    volume_ratio: float | None = None
    atr_pct: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    why: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class DeskDecision:
    symbol: str
    status: str  # SCAN_ONLY | WATCH | REJECT | AGENT_DECISION | ERROR
    scanner: ScanResult
    selected_analysts: tuple[str, ...]
    agent_decision: Any = None
    error: str | None = None


def _load_yfinance():
    try:
        import yfinance as yf  # type: ignore
        return yf
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "yfinance is required for scanner mode. Install repo deps with `pip install .` "
            "or at least `pip install yfinance`. Original error: " + repr(exc)
        ) from exc


def _rsi(values, period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for prev, curr in zip(values[-period - 1 : -1], values[-period:], strict=False):
        diff = curr - prev
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _sma(values, n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _atr_pct(highs, lows, closes, period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    trs = []
    for i in range(len(closes) - period, len(closes)):
        prev_close = closes[i - 1]
        tr = max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close))
        trs.append(tr)
    close = closes[-1]
    if close <= 0:
        return None
    return (sum(trs) / len(trs)) / close * 100


def scan_symbol(symbol: str, lookback: str = "6mo") -> ScanResult:
    """Cheap deterministic scanner: zero LLM/API-token burn."""
    yf = _load_yfinance()
    hist = yf.Ticker(symbol).history(period=lookback, interval="1d", auto_adjust=True)
    if hist is None or hist.empty or len(hist) < 55:
        return ScanResult(
            symbol=symbol,
            score=0,
            direction_bias="neutral",
            eligible=False,
            why=[],
            risk_flags=["insufficient_price_history"],
        )

    closes = [float(x) for x in hist["Close"].tolist()]
    highs = [float(x) for x in hist["High"].tolist()]
    lows = [float(x) for x in hist["Low"].tolist()]
    vols = [float(x) for x in hist["Volume"].tolist()]
    close = closes[-1]
    ma20 = _sma(closes, 20)
    ma50 = _sma(closes, 50)
    rsi14 = _rsi(closes, 14)
    atr = _atr_pct(highs, lows, closes, 14)
    avg_vol20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else 0
    volume_ratio = vols[-1] / avg_vol20 if avg_vol20 else None

    score = 0.0
    why: list[str] = []
    flags: list[str] = []

    if ma20 and close > ma20:
        score += 15
        why.append("close>20dma")
    if ma50 and close > ma50:
        score += 15
        why.append("close>50dma")
    if ma20 and ma50 and ma20 > ma50:
        score += 10
        why.append("20dma>50dma")
    if rsi14 is not None:
        if 45 <= rsi14 <= 68:
            score += 15
            why.append("rsi_constructive")
        elif rsi14 > 78:
            flags.append("rsi_overheated")
            score -= 10
        elif rsi14 < 35:
            flags.append("rsi_weak_or_oversold")
    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            score += 15
            why.append("volume_expansion")
        elif volume_ratio < 0.65:
            flags.append("low_relative_volume")
            score -= 5
    if atr is not None:
        if 1.0 <= atr <= 5.5:
            score += 10
            why.append("tradable_atr")
        elif atr > 8:
            flags.append("atr_too_wide")
            score -= 15

    # Simple momentum: 5-day and 20-day returns.
    ret5 = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
    ret20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0
    if ret5 > 0 and ret20 > 0:
        score += 15
        why.append("positive_5d_20d_momentum")
    elif ret5 < -4 and ret20 < 0:
        flags.append("downtrend_pressure")
        score -= 10

    direction = "long" if score >= 55 and close > (ma20 or close) else "neutral"
    eligible = score >= 60 and "atr_too_wide" not in flags and "low_relative_volume" not in flags

    return ScanResult(
        symbol=symbol.upper(),
        score=round(max(0, min(100, score)), 2),
        direction_bias=direction,
        eligible=eligible,
        close=round(close, 4),
        rsi14=round(rsi14, 2) if rsi14 is not None and math.isfinite(rsi14) else None,
        volume_ratio=round(volume_ratio, 2) if volume_ratio is not None and math.isfinite(volume_ratio) else None,
        atr_pct=round(atr, 2) if atr is not None and math.isfinite(atr) else None,
        ma20=round(ma20, 4) if ma20 else None,
        ma50=round(ma50, 4) if ma50 else None,
        why=why,
        risk_flags=flags,
    )


def analysts_for(result: ScanResult, mode: str) -> tuple[str, ...]:
    """Choose the smallest useful TradingAgents analyst set."""
    if mode == "intraday":
        return ("market", "news")
    if mode == "swing":
        return ("market", "news", "fundamentals")
    if mode == "sentiment":
        return ("market", "social", "news")
    if mode == "full":
        return ("market", "social", "news", "fundamentals")
    # Auto: keep it cheap unless the scanner says it is high-conviction.
    if result.score >= 80:
        return ("market", "news", "fundamentals")
    return ("market", "news")


def low_token_config() -> dict[str, Any]:
    """TradingAgents config tuned for low token burn."""
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(
        {
            "llm_provider": os.getenv("Y4Y_LLM_PROVIDER", "openrouter"),
            "quick_think_llm": os.getenv("Y4Y_QUICK_MODEL", "deepseek/deepseek-v4-flash"),
            "deep_think_llm": os.getenv("Y4Y_DEEP_MODEL", "deepseek/deepseek-v4-flash"),
            "max_debate_rounds": int(os.getenv("Y4Y_MAX_DEBATE_ROUNDS", "1")),
            "max_risk_discuss_rounds": int(os.getenv("Y4Y_MAX_RISK_ROUNDS", "1")),
            "news_article_limit": int(os.getenv("Y4Y_NEWS_ARTICLE_LIMIT", "5")),
            "global_news_article_limit": int(os.getenv("Y4Y_GLOBAL_NEWS_LIMIT", "3")),
            "global_news_lookback_days": int(os.getenv("Y4Y_GLOBAL_NEWS_DAYS", "3")),
            "temperature": float(os.getenv("Y4Y_TEMPERATURE", "0")),
            "checkpoint_enabled": True,
        }
    )
    return cfg


def run_tradingagents(symbol: str, trade_date: str, selected_analysts: tuple[str, ...]) -> Any:
    """Run the repo's TradingAgents graph only after scanner gates pass."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    cfg = low_token_config()
    ta = TradingAgentsGraph(selected_analysts=selected_analysts, debug=False, config=cfg)
    _state, decision = ta.propagate(symbol, trade_date)
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description="Y4Y low-token TradingAgents desk")
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")
    parser.add_argument("--trade-date", default=str(date.today()))
    parser.add_argument("--mode", choices=["auto", "intraday", "swing", "sentiment", "full"], default="auto")
    parser.add_argument("--max-finalists", type=int, default=2)
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--scan-only", action="store_true", help="never call LLMs")
    parser.add_argument("--run-agents", action="store_true", help="run TradingAgents for finalists")
    parser.add_argument("--out", default="results/y4y_desk/latest.json")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    scans = [scan_symbol(s) for s in symbols]
    scans.sort(key=lambda x: x.score, reverse=True)
    finalists = [s for s in scans if s.eligible and s.score >= args.min_score][: args.max_finalists]

    decisions: list[DeskDecision] = []
    for result in finalists:
        selected = analysts_for(result, args.mode)
        if args.run_agents and not args.scan_only:
            try:
                agent_decision = run_tradingagents(result.symbol, args.trade_date, selected)
                decisions.append(
                    DeskDecision(
                        symbol=result.symbol,
                        status="AGENT_DECISION",
                        scanner=result,
                        selected_analysts=selected,
                        agent_decision=agent_decision,
                    )
                )
            except Exception as exc:  # keep the desk from dying on one ticker
                decisions.append(
                    DeskDecision(
                        symbol=result.symbol,
                        status="ERROR",
                        scanner=result,
                        selected_analysts=selected,
                        error=repr(exc),
                    )
                )
        else:
            decisions.append(
                DeskDecision(
                    symbol=result.symbol,
                    status="SCAN_ONLY",
                    scanner=result,
                    selected_analysts=selected,
                )
            )

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trade_date": args.trade_date,
        "model_budget": {
            "default_provider": os.getenv("Y4Y_LLM_PROVIDER", "openrouter"),
            "quick_model": os.getenv("Y4Y_QUICK_MODEL", "deepseek/deepseek-v4-flash"),
            "deep_model": os.getenv("Y4Y_DEEP_MODEL", "deepseek/deepseek-v4-flash"),
            "full_graph_calls": len([d for d in decisions if d.status == "AGENT_DECISION"]),
        },
        "scanner_ranked": [asdict(s) for s in scans],
        "decisions": [asdict(d) for d in decisions],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
