"""Replay the latest Binance candles through scanner -> LLM -> paper orders.

This is an immediate demo for the live-trading flow without real money:
1. Fetch current/latest Binance OHLCV candles.
2. Replay historical scanner signals inside that fresh data window.
3. Batch-call the compact LLM for each signal candle.
4. Open fake-money paper positions for approved BUY signals.
5. Close by TP/SL or after a fixed hold window, then write results to dashboard memory.

Example:
    python scripts/crypto_paper_realtime_demo.py SOL/USDT XRP/USDT ADA/USDT \
      --memory-dir /tmp/tradingagents_crypto_memory_case --reset --deposit 1000 --max-batches 3
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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from tradingagents.agents.utils.crypto_memory import CryptoTrainingMemory
from tradingagents.crypto import CryptoTrainRunner
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import _fetch_ohlcv
from tradingagents.dataflows.crypto_news import get_global_crypto_news
from tradingagents.dataflows.crypto_sentiment import get_crypto_fear_greed
from tradingagents.default_config import CRYPTO_TRAIN_CONFIG
from tradingagents.execution import PaperTradingLedger
from tradingagents.scanner import FastCryptoScanner


def _json_from_text(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {"decisions": []}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"decisions": []}


def _fmt_money(value: float) -> str:
    return f"{value:.2f} USDT"


def _resolve_safe_memory_dir(memory_dir: str, allow_temp_memory: bool = False) -> Path:
    """Avoid writing paper-trading state to volatile temp folders by default."""
    requested = Path(memory_dir).expanduser()
    try:
        resolved = requested.resolve(strict=False)
        temp_roots = [Path(tempfile.gettempdir()).resolve(strict=False)]
    except OSError:
        resolved = requested.absolute()
        temp_roots = [Path(tempfile.gettempdir()).absolute()]
    for candidate in ("/tmp", "/private/tmp", "/var/tmp"):
        temp_roots.append(Path(candidate).resolve(strict=False))
    is_temp = any(resolved == root or root in resolved.parents for root in temp_roots)
    if not allow_temp_memory and is_temp:
        fallback = Path(CRYPTO_TRAIN_CONFIG.get("crypto_memory_dir", "~/.tradingagents/crypto_memory")).expanduser()
        print(
            f"WARNING: refusing volatile memory dir {requested}; using persistent {fallback}. "
            "Pass --allow-temp-memory only for throwaway tests.",
            flush=True,
        )
        return fallback
    return requested


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo paper trading flow on latest Binance data")
    parser.add_argument("symbols", nargs="*", default=["SOL/USDT", "XRP/USDT", "ADA/USDT"], help="Binance symbols")
    parser.add_argument("--memory-dir", default=CRYPTO_TRAIN_CONFIG.get("crypto_memory_dir"), help="Dashboard memory folder")
    parser.add_argument("--allow-temp-memory", action="store_true", help="Allow volatile /tmp memory directory for throwaway tests only")
    parser.add_argument("--deposit", type=float, default=1000.0, help="Fake USDT deposit")
    parser.add_argument("--reset", action="store_true", help="Reset paper account before demo")
    parser.add_argument("--limit", type=int, default=320, help="Latest OHLCV candles to fetch")
    parser.add_argument("--hold", type=int, default=8, help="Force close after this many candles if TP/SL not hit")
    parser.add_argument("--max-batches", type=int, default=3, help="Max LLM batch calls")
    parser.add_argument("--skip-batches", type=int, default=0, help="Skip this many scanner signal batches before calling LLM")
    parser.add_argument("--max-signals-per-batch", type=int, default=5)
    parser.add_argument("--min-strength", type=float, default=0.50)
    parser.add_argument("--allocation-pct", type=float, default=0.10)
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--model", default=None, help="Override quick_think_llm for the demo LLM call")
    parser.add_argument(
        "--demo-approval-guidance",
        action="store_true",
        help="Tell the LLM this is fake-money training and it may approve strong scanner setups for measurement.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only show signals; do not call LLM or write paper trades")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    memory_dir = _resolve_safe_memory_dir(args.memory_dir, allow_temp_memory=args.allow_temp_memory)
    config = CRYPTO_TRAIN_CONFIG.copy()
    config.update(
        {
            "crypto_memory_dir": str(memory_dir),
            "crypto_ohlcv_limit": args.limit,
            "scanner_min_strength": args.min_strength,
        }
    )
    if not config.get("google_api_keys"):
        config["google_api_keys"] = os.getenv("GOOGLE_API_KEYS", "")
    if args.model:
        config["quick_think_llm"] = args.model
    set_config(config)

    ledger = PaperTradingLedger(memory_dir)
    if args.reset:
        ledger.reset(args.deposit)
    elif ledger.portfolio()["total_deposits"] <= 0 and args.deposit > 0:
        ledger.deposit(args.deposit, note="realtime paper demo")

    print(f"Memory/UI folder: {memory_dir}")
    print(f"Symbols: {', '.join(args.symbols)}")
    print("Fetching latest Binance candles...")
    frames = {symbol: _fetch_ohlcv(symbol, limit=args.limit) for symbol in args.symbols}
    scanner = FastCryptoScanner(config)
    runner = CryptoTrainRunner(args.symbols, config=config, profile="compact")
    memory = CryptoTrainingMemory(config)

    batches = 0
    skipped_signal_batches = 0
    opened = 0
    skipped = 0
    closed_total = 0
    decisions_seen: List[Dict[str, Any]] = []
    start = 80
    end = max(start, min(len(df) for df in frames.values()) - args.hold - 1)

    for idx in range(start, end):
        signals = []
        for symbol, df in frames.items():
            signal = scanner.scan_dataframe(symbol, df.iloc[: idx + 1].copy())
            if signal and signal.action != "WAIT" and signal.strength >= args.min_strength:
                signals.append(signal)
        if not signals:
            continue

        signal_time = signals[0].timestamp_utc
        print(f"\nSignal batch #{batches + 1} @ {signal_time}: {len(signals)} signal(s)")
        for signal in signals:
            print(f"  SCAN {signal.symbol} {signal.action} entry={signal.entry} sl={signal.stop_loss} tp={signal.take_profit} strength={signal.strength}")
        if skipped_signal_batches < args.skip_batches:
            skipped_signal_batches += 1
            print("  SKIP batch before LLM due to --skip-batches")
            continue
        if args.dry_run:
            batches += 1
            if batches >= args.max_batches:
                break
            continue

        trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        signal_contexts = [runner._signal_context(signal, trade_date, memory) for signal in signals[: args.max_signals_per_batch]]
        prompt = runner._compact_batch_prompt(
            trade_date,
            signal_contexts,
            get_global_crypto_news(trade_date, limit=5),
            get_crypto_fear_greed(days=7),
        )
        if args.demo_approval_guidance:
            prompt += """

=== PAPER TRAINING DEMO MODE ===
Đây là lệnh tiền ảo để đo win-rate và kiểm thử UI, không phải tiền thật.
Nếu signal có strength >= 0.65, RSI oversold rõ, risk/reward hợp lệ và không có tin tức symbol-specific cực xấu,
bạn có thể APPROVE bằng action BUY với confidence vừa phải thay vì tự động WAIT chỉ vì thị trường chung đang Fear.
Vẫn SKIP/WAIT nếu setup yếu hoặc R/R xấu.
"""
        try:
            response = runner._create_compact_llm().invoke(prompt)
        except Exception as exc:
            skipped += len(signals[: args.max_signals_per_batch])
            batches += 1
            print(f"  LLM ERROR: {exc}")
            if batches >= args.max_batches:
                break
            continue
        text = getattr(response, "content", str(response))
        parsed = _json_from_text(text)
        decisions = parsed.get("decisions", []) if isinstance(parsed, dict) else []
        decision_by_symbol = {str(item.get("symbol")): item for item in decisions if isinstance(item, dict)}
        decisions_seen.extend(decisions)

        opened_ids: List[str] = []
        for signal in signals[: args.max_signals_per_batch]:
            decision = decision_by_symbol.get(signal.symbol, {"symbol": signal.symbol, "action": "WAIT", "reasoning": "missing LLM decision"})
            print(f"  LLM  {signal.symbol} action={decision.get('action')} conf={decision.get('confidence')} reason={decision.get('reasoning')}")
            if str(decision.get("action") or "").upper() != signal.action:
                skipped += 1
                continue
            order = ledger.open_position(
                signal.to_dict(),
                decision,
                allocation_pct=args.allocation_pct,
                min_confidence=args.min_confidence,
                opened_at=signal.timestamp_utc,
            )
            if order.get("status") == "opened":
                opened += 1
                opened_ids.append(order["position"]["id"])
                print(f"  OPEN {signal.symbol} notional={_fmt_money(order['position']['notional'])}")
            else:
                skipped += 1
                print(f"  SKIP {signal.symbol}: {order.get('reason')}")

        # Walk forward over the next candles to close by TP/SL if hit.
        for forward in range(1, args.hold + 1):
            candles: Dict[str, Dict[str, Any]] = {}
            timestamp = None
            for symbol, df in frames.items():
                row = df.iloc[idx + forward]
                timestamp = row["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
                candles[symbol] = {"high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])}
            closed = ledger.check_exits(candles, timestamp_utc=timestamp)
            closed_total += len(closed)
            for trade in closed:
                print(f"  CLOSE {trade['symbol']} {trade['result']} pnl={trade['pnl']:.4f}% reason={trade['exit_reason']}")

        # Force-close positions opened in this batch that survived the hold window.
        open_by_id = {position.get("id"): position for position in ledger.load_positions()}
        for position_id in opened_ids:
            position = open_by_id.get(position_id)
            if not position:
                continue
            symbol = position["symbol"]
            row = frames[symbol].iloc[idx + args.hold]
            timestamp = row["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
            trade = ledger.force_close(position_id, float(row["Close"]), reason=f"HOLD_{args.hold}_CANDLES", timestamp_utc=timestamp)
            closed_total += 1
            print(f"  CLOSE {trade['symbol']} {trade['result']} pnl={trade['pnl']:.4f}% reason={trade['exit_reason']}")

        batches += 1
        if batches >= args.max_batches:
            break

    portfolio = ledger.portfolio()
    stats = portfolio["stats"]
    print("\n=== PAPER DEMO RESULT ===")
    print(f"LLM batches: {batches}")
    print(f"Opened: {opened} | Skipped: {skipped} | Closed in demo: {closed_total}")
    print(f"Cash: {_fmt_money(portfolio['cash'])} | Equity: {_fmt_money(portfolio['equity'])}")
    print(f"P&L: {_fmt_money(portfolio['total_pnl'])} ({portfolio['total_pnl_pct']:.2f}%)")
    print(f"Win-rate: {stats['win_rate'] * 100:.1f}% ({stats['wins']} wins / {stats['losses']} losses / {stats['closed_trades']} closed total)")
    print("Refresh the dashboard to see the paper wallet and closed trades.")


if __name__ == "__main__":
    main()
