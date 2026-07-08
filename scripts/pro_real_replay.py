"""TRADE-01: replay the full pipeline over REAL historical market data.

    python scripts/pro_real_replay.py --symbol XAUUSD --bars 250 --provider env
    python scripts/pro_real_replay.py --symbol BTC-USD --provider fake

Real daily bars come from the same yfinance loader the live ingestion uses
(GC=F for gold, BTC-USD for bitcoin). ``--provider fake`` exercises the
whole deterministic path (indicators, risk, gates, SimBroker) with the
scripted LLM; ``--provider env`` builds real models from
TRADINGAGENTS_LLM_PROVIDER / _QUICK_THINK_LLM / _DEEP_THINK_LLM (.env is
loaded) and tracks spend. A JSON artifact lands in docs/verification/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # test fakes for --provider fake

from tradingagents.contracts import (  # noqa: E402
    AssetClass,
    ModelRouting,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import BacktestEngine, BarReplay, SimBroker  # noqa: E402
from tradingagents.pro.ingestion.gold_feeds import YFinanceDailyBarsFeed  # noqa: E402
from tradingagents.pro.memory import ProMemory  # noqa: E402
from tradingagents.pro.models import bundle_from_config  # noqa: E402
from tradingagents.pro.observability import CostTrackingLLM, price_for  # noqa: E402

TICKERS = {"XAUUSD": ("GC=F", AssetClass.GOLD),
           "BTC-USD": ("BTC-USD", AssetClass.BITCOIN)}


def build_llm(provider_mode: str, config: ProConfig):
    if provider_mode == "fake":
        from tests.test_pro_pipeline_graph import FakePipelineLLM

        return FakePipelineLLM(), None
    bundle = bundle_from_config(config, temperature=0.2)
    price = price_for(config.models.llm_provider)
    bundle.quick = CostTrackingLLM(bundle.quick, price=price)
    deep_tracker = CostTrackingLLM(bundle.deep, price=price)
    bundle.deep = deep_tracker if bundle.deep is not bundle.quick else bundle.quick
    return bundle, (bundle.quick, bundle.deep)


def main() -> int:
    parser = argparse.ArgumentParser(prog="pro_real_replay")
    parser.add_argument("--symbol", choices=sorted(TICKERS), default="XAUUSD")
    parser.add_argument("--bars", type=int, default=250,
                        help="daily bars to fetch (default 250 ≈ 1 trading year)")
    parser.add_argument("--min-history", type=int, default=100)
    parser.add_argument("--decide-every", type=int, default=12,
                        help="run the pipeline every N bars (default 12)")
    parser.add_argument("--provider", choices=("fake", "env"), default="fake")
    parser.add_argument("--equity", type=float, default=100_000.0)
    args = parser.parse_args()

    ticker, asset = TICKERS[args.symbol]
    print(f"fetching {args.bars} real daily bars for {args.symbol} ({ticker})…")
    bars = YFinanceDailyBarsFeed().get_bars(ticker, Timeframe.D1, limit=args.bars)
    print(f"  got {len(bars)} bars: {bars[0].start.date()} → {bars[-1].start.date()}, "
          f"last close {bars[-1].close:.2f}")

    routing = ModelRouting(
        llm_provider=os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "openai"),
        quick_think_llm=os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.4-mini"),
        deep_think_llm=os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-5.5"),
    )
    if args.provider == "env":
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        from tradingagents.llm_clients.api_key_env import get_api_key_env

        key_env = get_api_key_env(routing.llm_provider)
        if key_env and not os.environ.get(key_env):
            print(f"{key_env} not set (env or .env); aborting", file=sys.stderr)
            return 2

    config = ProConfig(asset=asset, mode=TradingMode.BACKTEST,
                       max_debate_rounds=1, models=routing)
    llm, trackers = build_llm(args.provider, config)

    n_decisions = max(0, (len(bars) - args.min_history) // args.decide_every)
    print(f"replaying with pipeline decisions every {args.decide_every} bars "
          f"(~{n_decisions} decisions, provider={args.provider})…\n")

    result = BacktestEngine(
        llm, config,
        BarReplay(args.symbol, asset, bars, window=args.min_history),
        broker=SimBroker(initial_equity=args.equity),
        memory=ProMemory(),
        min_history=args.min_history,
        decide_every=args.decide_every,
    ).run()

    report = result.report.as_dict()
    print(f"decisions {result.decisions} · executed {result.executed} "
          f"· rejections {dict(result.rejections)}")
    print(f"final equity {result.final_equity:,.2f} · trades {len(result.trades)}")
    for key, value in report.items():
        print(f"  {key}: {value}")
    cost = None
    if trackers:
        cost = sum(t.report.est_cost_usd for t in set(trackers))
        calls = sum(t.report.calls for t in set(trackers))
        print(f"LLM calls {calls}, est cost ${cost:.2f}")

    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "ticker": ticker,
        "bars": len(bars),
        "window": [bars[0].start.date().isoformat(),
                   bars[-1].start.date().isoformat()],
        "provider": args.provider,
        "models": (routing.model_dump(mode="json")
                   if args.provider == "env" else "FakePipelineLLM"),
        "decide_every": args.decide_every,
        "decisions": result.decisions,
        "executed": result.executed,
        "rejections": dict(result.rejections),
        "final_equity": result.final_equity,
        "n_trades": len(result.trades),
        "report": report,
        "est_cost_usd": cost,
        "trades": [
            {"side": t.side, "entry": t.entry_price, "exit": t.exit_price,
             "pnl": round(t.pnl, 2), "reason": t.reason,
             "opened": t.opened_at.date().isoformat(),
             "closed": t.closed_at.date().isoformat()}
            for t in result.trades
        ],
    }
    out_dir = REPO_ROOT / "docs" / "verification"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"replay_{args.symbol}_{args.provider}_{stamp}.json"
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nartifact: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
