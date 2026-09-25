"""Small LLM-filtered backtest for scanner signals.

This script replays recent Binance candles, batches scanner signals by candle,
asks the compact LLM to approve/reject each batch in one call, then compares
rule-only win-rate against LLM-approved win-rate for those same signals.

It is intentionally small by default to protect API quota.
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import argparse
import json
import os
import re
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import _fetch_ohlcv
from tradingagents.default_config import CRYPTO_TRAIN_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.google_key_rotator import parse_google_api_keys
from tradingagents.scanner import FastCryptoScanner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM-filtered crypto scanner backtest")
    parser.add_argument("symbols", nargs="*", default=["BTC/USDT", "ETH/USDT", "SOL/USDT"], help="Binance symbols")
    parser.add_argument("--limit", type=int, default=220, help="Candles to fetch per symbol")
    parser.add_argument("--hold", type=int, default=8, help="Holding candles per simulated trade")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Fee per side in basis points; 10 = 0.10%% each side")
    parser.add_argument("--min-strength", type=float, default=0.50, help="Scanner threshold")
    parser.add_argument("--max-batches", type=int, default=3, help="Maximum LLM calls")
    parser.add_argument("--max-signals-per-batch", type=int, default=5, help="Maximum signals in one LLM prompt")
    parser.add_argument("--provider", default=None, help="Override LLM provider")
    parser.add_argument("--model", default=None, help="Override compact LLM model")
    parser.add_argument("--dry-run", action="store_true", help="Do not call LLM; print first prompt payload only")
    return parser.parse_args()


def _compact_llm(config: Dict[str, Any]):
    provider = config.get("llm_provider", "google")
    kwargs: Dict[str, Any] = {}
    if provider == "google":
        keys = parse_google_api_keys(config.get("google_api_keys", ""))
        if not keys:
            raise RuntimeError("GOOGLE_API_KEYS is empty. Add it to .env or environment before running LLM backtest.")
        kwargs["api_keys"] = keys
        kwargs["rotation_state_path"] = config.get(
            "google_key_rotation_state_path",
            os.path.join(config["data_cache_dir"], "google_key_rotation.json"),
        )
        kwargs["role"] = "compact"
        if config.get("google_thinking_level"):
            kwargs["thinking_level"] = config.get("google_thinking_level")

    return create_llm_client(
        provider=provider,
        model=config.get("quick_think_llm"),
        base_url=config.get("backend_url"),
        **kwargs,
    ).get_llm()


def _prompt(batch: List[Dict[str, Any]], trade_date: str) -> str:
    payload = json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True)
    return f"""Bạn là bộ lọc tín hiệu giao dịch crypto Binance spot.

Nhiệm vụ: với mỗi scanner signal bên dưới, quyết định có APPROVE trade hay SKIP.
Chỉ APPROVE nếu tín hiệu đủ rõ, risk/reward hợp lý, confidence đủ cao. Nếu nghi ngờ, SKIP.
Không dùng dữ liệu tương lai; chỉ dùng thông tin trong payload.
Lưu ý: với strategy=rsi_reversal, market_regime=trend_down là điều kiện đầu vào mong muốn, không phải lý do tự động SKIP. Hãy đánh giá thêm RSI, volume_spike, strength và stop_loss/take_profit.

Trả về đúng JSON object hợp lệ, không markdown:
{{
  "decisions": [
    {{"symbol": "BTC/USDT", "index": 123, "decision": "APPROVE|SKIP", "action": "BUY|SELL|WAIT", "confidence": 0.0, "reason": "..."}}
  ]
}}

Trade date: {trade_date}
Signals:
{payload}
"""


def _json_from_text(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {"decisions": []}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"decisions": []}


def _make_trade(symbol: str, i: int, signal, df, hold: int, fee_bps: float) -> Dict[str, Any]:
    entry = float(df.iloc[i]["Close"])
    direction = 1 if signal.action == "BUY" else -1
    stop_loss = float(signal.stop_loss)
    take_profit = float(signal.take_profit)
    exit_price = float(df.iloc[i + hold]["Close"])
    exit_reason = f"HOLD_{hold}_CANDLES"
    closed_at = df.iloc[i + hold]["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
    for forward in range(1, hold + 1):
        row = df.iloc[i + forward]
        high = float(row["High"])
        low = float(row["Low"])
        if signal.action == "BUY":
            stop_hit = low <= stop_loss
            take_hit = high >= take_profit
        else:
            stop_hit = high >= stop_loss
            take_hit = low <= take_profit
        if stop_hit:
            exit_price = stop_loss
            exit_reason = "STOP_LOSS"
            closed_at = row["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
            break
        if take_hit:
            exit_price = take_profit
            exit_reason = "TAKE_PROFIT"
            closed_at = row["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
            break
    gross_pnl_pct = direction * (exit_price - entry) / entry * 100
    fees_pct = (float(fee_bps) * 2) / 100.0
    pnl_pct = gross_pnl_pct - fees_pct
    return {
        "symbol": symbol,
        "index": i,
        "timestamp_utc": signal.timestamp_utc,
        "closed_at": closed_at,
        "strategy": signal.strategy,
        "action": signal.action,
        "strength": signal.strength,
        "entry": round(entry, 8),
        "exit": round(exit_price, 8),
        "stop_loss": round(stop_loss, 8),
        "take_profit": round(take_profit, 8),
        "exit_reason": exit_reason,
        "gross_pnl": round(gross_pnl_pct, 4),
        "fees_pct": round(fees_pct, 4),
        "pnl": round(pnl_pct, 4),
        "result": "WIN" if pnl_pct > 0 else "LOSS" if pnl_pct < 0 else "FLAT",
        "rsi": signal.rsi,
        "atr": signal.atr,
        "volume_spike": signal.volume_spike,
        "market_regime": signal.market_regime,
        "reason": signal.reason,
    }


def _summarize(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = sum(1 for trade in trades if trade["result"] == "WIN")
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate": wins / len(trades) if trades else 0.0,
        "avg_pnl_pct": mean([trade["pnl"] for trade in trades]) if trades else 0.0,
    }


def main() -> None:
    args = parse_args()
    config = CRYPTO_TRAIN_CONFIG.copy()
    config["crypto_ohlcv_limit"] = args.limit
    config["scanner_min_strength"] = args.min_strength
    if args.provider:
        config["llm_provider"] = args.provider
    if args.model:
        config["quick_think_llm"] = args.model
    if not config.get("google_api_keys"):
        config["google_api_keys"] = os.getenv("GOOGLE_API_KEYS", "")
    set_config(config)

    scanner = FastCryptoScanner(config)
    frames = {symbol: _fetch_ohlcv(symbol, limit=args.limit) for symbol in args.symbols}
    llm = None if args.dry_run else _compact_llm(config)
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    baseline_trades: List[Dict[str, Any]] = []
    llm_trades: List[Dict[str, Any]] = []
    llm_decisions: List[Dict[str, Any]] = []
    calls = 0

    for i in range(80, max(80, args.limit - args.hold)):
        batch: List[Dict[str, Any]] = []
        trade_lookup: Dict[tuple[str, int], Dict[str, Any]] = {}
        for symbol, df in frames.items():
            signal = scanner.scan_dataframe(symbol, df.iloc[: i + 1])
            if not signal or signal.action not in {"BUY", "SELL"} or signal.strength < scanner.min_strength:
                continue
                trade = _make_trade(symbol, i, signal, df, args.hold, args.fee_bps)
            baseline_trades.append(trade)
            trade_lookup[(symbol, i)] = trade
            batch.append(
                {
                    "symbol": symbol,
                    "index": i,
                    "timestamp_utc": signal.timestamp_utc,
                    "action": signal.action,
                    "strategy": signal.strategy,
                    "strength": signal.strength,
                    "entry": signal.entry,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "rsi": signal.rsi,
                    "atr": signal.atr,
                    "volume_spike": signal.volume_spike,
                    "market_regime": signal.market_regime,
                    "reason": signal.reason,
                }
            )
            if len(batch) >= args.max_signals_per_batch:
                break

        if not batch:
            continue
        calls += 1
        prompt = _prompt(batch, trade_date)
        if args.dry_run:
            print(prompt)
            break
        response = llm.invoke(prompt)
        content = getattr(response, "content", str(response))
        parsed = _json_from_text(content)
        decisions = parsed.get("decisions", []) if isinstance(parsed, dict) else []
        for decision in decisions:
            symbol = str(decision.get("symbol", ""))
            index = int(decision.get("index", -1))
            approved = str(decision.get("decision", "")).upper() == "APPROVE"
            action = str(decision.get("action", "")).upper()
            trade = trade_lookup.get((symbol, index))
            llm_decisions.append(
                {
                    "symbol": symbol,
                    "index": index,
                    "decision": str(decision.get("decision", "")),
                    "action": action,
                    "confidence": decision.get("confidence"),
                    "reason": decision.get("reason", ""),
                    "baseline_result": trade.get("result") if trade else "n/a",
                    "baseline_pnl": trade.get("pnl") if trade else "n/a",
                }
            )
            if approved and trade and action == trade["action"]:
                enriched = dict(trade)
                enriched["llm_confidence"] = decision.get("confidence")
                enriched["llm_reason"] = decision.get("reason")
                llm_trades.append(enriched)
        if calls >= args.max_batches:
            break

    baseline = _summarize(baseline_trades)
    llm_filtered = _summarize(llm_trades)
    print("\nLLM-filtered scanner backtest")
    print("=" * 80)
    print(f"Symbols: {', '.join(args.symbols)}")
    print(f"Candles={args.limit} hold={args.hold} min_strength={args.min_strength} llm_calls={calls}")
    print(
        "Rule-only on same sampled signals: "
        f"trades={baseline['trades']} wins={baseline['wins']} losses={baseline['losses']} "
        f"win_rate={baseline['win_rate']:.1%} avg_pnl={baseline['avg_pnl_pct']:.4f}%"
    )
    print(
        "LLM-approved only: "
        f"trades={llm_filtered['trades']} wins={llm_filtered['wins']} losses={llm_filtered['losses']} "
        f"win_rate={llm_filtered['win_rate']:.1%} avg_pnl={llm_filtered['avg_pnl_pct']:.4f}%"
    )
    if llm_decisions:
        print("\nLLM decisions:")
        for decision in llm_decisions:
            print(
                f"  {decision['symbol']} idx={decision['index']} {decision['decision']} "
                f"action={decision['action']} conf={decision['confidence']} "
                f"baseline={decision['baseline_result']} pnl={decision['baseline_pnl']}% "
                f"reason={decision['reason']}"
            )
    if llm_trades:
        print("\nLLM-approved trades:")
        for trade in llm_trades:
            print(
                f"  {trade['timestamp_utc']} {trade['symbol']} {trade['action']} "
                f"result={trade['result']} pnl={trade['pnl']}% llm_conf={trade.get('llm_confidence')}"
            )


if __name__ == "__main__":
    main()
