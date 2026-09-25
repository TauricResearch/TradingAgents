"""Run scanner/analyzer and a deterministic backtest over recent Binance candles.

This validates the scanner before any real trade mode. It does not call an LLM
and does not place orders.
"""

from __future__ import annotations

import argparse
from statistics import mean
from typing import Dict, List

from dotenv import load_dotenv

from tradingagents.analyzer import DeepCryptoAnalyzer
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import _fetch_ohlcv
from tradingagents.default_config import CRYPTO_TRAIN_CONFIG
from tradingagents.memory import CryptoMemoryStore, MemoryProcessor, TradeMemory
from tradingagents.scanner import FastCryptoScanner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest fast crypto scanner on recent Binance candles")
    parser.add_argument("symbols", nargs="*", default=["BTC/USDT"], help="Symbols such as BTC/USDT ETH/USDT")
    parser.add_argument("--limit", type=int, default=320, help="Number of candles to fetch")
    parser.add_argument("--hold", type=int, default=8, help="Holding candles per simulated signal")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Fee per side in basis points; 10 = 0.10%% each side")
    parser.add_argument("--min-strength", type=float, default=0.55, help="Minimum scanner strength")
    parser.add_argument("--memory-dir", default=".tmp_crypto_memory", help="Local memory directory for this run")
    return parser.parse_args()


def simulate_exit(symbol: str, signal, df, index: int, hold: int, fee_bps: float) -> Dict:
    """Conservative candle replay: stop-loss wins if SL and TP hit in the same candle."""
    entry = float(df.iloc[index]["Close"])
    direction = 1 if signal.action == "BUY" else -1
    stop_loss = float(signal.stop_loss)
    take_profit = float(signal.take_profit)
    exit_price = float(df.iloc[index + hold]["Close"])
    exit_reason = f"HOLD_{hold}_CANDLES"
    exit_timestamp = df.iloc[index + hold]["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")

    for forward in range(1, hold + 1):
        row = df.iloc[index + forward]
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
            exit_timestamp = row["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
            break
        if take_hit:
            exit_price = take_profit
            exit_reason = "TAKE_PROFIT"
            exit_timestamp = row["Date"].strftime("%Y-%m-%dT%H:%M:%SZ")
            break

    gross_pnl_pct = direction * (exit_price - entry) / entry * 100
    fees_pct = (float(fee_bps) * 2) / 100.0
    net_pnl_pct = gross_pnl_pct - fees_pct
    return {
        "symbol": symbol,
        "index": index,
        "timestamp_utc": signal.timestamp_utc,
        "closed_at": exit_timestamp,
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
        "pnl": round(net_pnl_pct, 4),
        "result": "WIN" if net_pnl_pct > 0 else "LOSS" if net_pnl_pct < 0 else "FLAT",
        "rsi": signal.rsi,
        "atr": signal.atr,
        "volume_spike": signal.volume_spike,
        "market_regime": signal.market_regime,
        "reason": signal.reason,
    }


def backtest_symbol(symbol: str, config: Dict, hold: int, fee_bps: float, store: CryptoMemoryStore) -> Dict:
    scanner = FastCryptoScanner(config)
    analyzer = DeepCryptoAnalyzer(TradeMemory(store), mode_id="backtest")
    df = _fetch_ohlcv(symbol, limit=int(config.get("crypto_ohlcv_limit", 320)))
    trades: List[Dict] = []

    for i in range(80, max(80, len(df) - hold)):
        signal = scanner.scan_dataframe(symbol, df.iloc[: i + 1])
        if not signal or signal.action not in {"BUY", "SELL"} or signal.strength < scanner.min_strength:
            continue
        trade = simulate_exit(symbol, signal, df, i, hold, fee_bps)
        analyzed = analyzer.analyze(signal, mode="training")
        analyzed.update({**trade, "memory_tier": "raw"})
        store.append_raw(analyzed)
        trades.append(analyzed)

    wins = sum(1 for trade in trades if trade["result"] == "WIN")
    win_rate = wins / len(trades) if trades else 0.0
    return {
        "symbol": symbol,
        "candles": len(df),
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate": round(win_rate, 4),
        "avg_pnl_pct": round(mean([trade["pnl"] for trade in trades]), 4) if trades else 0.0,
        "sample_trades": trades[-3:],
    }


def main() -> None:
    load_dotenv()
    args = parse_args()
    config = CRYPTO_TRAIN_CONFIG.copy()
    config["crypto_ohlcv_limit"] = args.limit
    config["scanner_min_strength"] = args.min_strength
    set_config(config)

    store = CryptoMemoryStore(args.memory_dir)
    summaries = [backtest_symbol(symbol, config, args.hold, args.fee_bps, store) for symbol in args.symbols]
    lessons = MemoryProcessor(store).process()

    print("\nCrypto scanner backtest summary")
    print("=" * 80)
    total_trades = sum(item["trades"] for item in summaries)
    total_wins = sum(item["wins"] for item in summaries)
    for item in summaries:
        print(
            f"{item['symbol']}: candles={item['candles']} trades={item['trades']} "
            f"wins={item['wins']} losses={item['losses']} "
            f"win_rate={item['win_rate']:.1%} avg_pnl={item['avg_pnl_pct']:.4f}%"
        )
    overall = total_wins / total_trades if total_trades else 0.0
    print("-" * 80)
    print(f"OVERALL: trades={total_trades} wins={total_wins} win_rate={overall:.1%}")
    print(f"Draft lessons created: {len(lessons)}")
    print(f"Raw memory: {store.raw_path}")
    print(f"Lesson memory: {store.lesson_path}")
    print(f"Global memory: {store.global_path}")

    for item in summaries:
        if item["sample_trades"]:
            print(f"\nRecent sample trades for {item['symbol']}:")
            for trade in item["sample_trades"]:
                print(
                    f"  {trade['signal']} {trade['strategy']} result={trade['result']} "
                    f"pnl={trade['pnl']}% confidence={trade['confidence']} regime={trade['market_context']['market_regime']}"
                )


if __name__ == "__main__":
    main()