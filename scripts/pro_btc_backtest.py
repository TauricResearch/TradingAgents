"""Institutional 1-year BTC backtest of the TradingAgents Pro pipeline.

Runs the REAL LangGraph pipeline over ~365 daily BTC bars (look-ahead-safe:
decide on close i, fill open i+1), captures every decision's full state, and
emits the institutional report bundle:

    python scripts/pro_btc_backtest.py --provider fake            # free dry-run
    python scripts/pro_btc_backtest.py --provider env --bars 365  # real LLM ($)

``--provider env`` builds real models from TRADINGAGENTS_LLM_PROVIDER /
_QUICK_THINK_LLM / _DEEP_THINK_LLM, tracks spend, and caches responses
(record/replay) so re-runs are free. Artifacts land in
docs/backtests/btc_1y_<ts>/: trades.csv/.json, metrics.json, equity.csv,
drawdown.csv, charts/*.png, REPORT.md.

Honest scope (see REPORT.md): daily bars only; with no historical corpus the
macro/sentiment/on-chain agents abstain, so this measures the technicals +
quant/risk subsystem. ``--provider fake`` validates the harness/mechanics only
(scripted model) and cannot measure edge.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tradingagents.contracts import (  # noqa: E402
    AssetClass,
    ModelRouting,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import BacktestEngine, BarReplay, SimBroker  # noqa: E402
from tradingagents.pro.backtest.agent_attribution import agent_attribution  # noqa: E402
from tradingagents.pro.backtest.llm_cache import CachingLLM  # noqa: E402
from tradingagents.pro.backtest.montecarlo import monte_carlo_summary  # noqa: E402
from tradingagents.pro.backtest.regime_breakdown import regime_breakdown  # noqa: E402
from tradingagents.pro.backtest.report import extended_report  # noqa: E402
from tradingagents.pro.backtest.trade_log import (  # noqa: E402
    enrich_trades,
    write_csv,
    write_json,
)
from tradingagents.pro.ingestion.gold_feeds import YFinanceDailyBarsFeed  # noqa: E402
from tradingagents.pro.memory import ProMemory  # noqa: E402
from tradingagents.pro.models import bundle_from_config  # noqa: E402
from tradingagents.pro.observability import CostTrackingLLM, price_for  # noqa: E402

# bars per year by timeframe (BTC trades 24/7) — annualizes Sharpe/Sortino/CAGR
_PERIODS_PER_YEAR = {
    Timeframe.M15: 365 * 96,
    Timeframe.H1: 365 * 24,
    Timeframe.H4: 365 * 6,
    Timeframe.D1: 365,
}


def _rel(p: Path) -> str:
    """Repo-relative path when possible, else absolute (for custom outdirs)."""
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


_DECISION_COLS = ["index", "time", "outcome", "action", "confidence", "regime",
                  "var_95", "cvar_95", "reasons"]


def write_decisions_csv(path: Path, rows: list[dict]) -> None:
    """Per-decision funnel → flat CSV (reused by the checkpoint + final write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        ",".join(_DECISION_COLS) + "\n" + "\n".join(
            ",".join(f'"{d[c]}"' if c == "reasons" else str(d[c] if d[c] is not None else "")
                     for c in _DECISION_COLS)
            for d in rows
        ) + "\n", encoding="utf-8")


class _CapturingEngine(BacktestEngine):
    """BacktestEngine that records each decision's pipeline state (keyed by
    recommendation id — the join key for the enriched trade log) AND a
    per-decision funnel row (executed vs rejected@stage, reasons, VaR/CVaR,
    regime) so a run is diagnosable. Optionally checkpoints the funnel +
    progress every N decisions so a long run is never lost on interruption.
    Zero behavioural change (captures, then delegates)."""

    def __init__(self, *args, checkpoint_dir: Path | None = None,
                 checkpoint_every: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.captured: dict[str, dict] = {}
        self.decisions_log: list[dict] = []
        self._checkpoint_dir = checkpoint_dir
        self._checkpoint_every = checkpoint_every

    def _checkpoint(self) -> None:
        if not self._checkpoint_dir:
            return
        write_decisions_csv(self._checkpoint_dir / "decisions.csv", self.decisions_log)
        executed = sum(1 for d in self.decisions_log if d["outcome"] == "executed")
        (self._checkpoint_dir / "progress.json").write_text(json.dumps({
            "decisions": len(self.decisions_log),
            "executed": executed,
            "open_count": self.broker.open_count,
            "closed_trades": len(self.broker.closed),
            "last_time": self.decisions_log[-1]["time"] if self.decisions_log else None,
        }, indent=2), encoding="utf-8")

    def _apply_decision(self, state: dict, i: int):
        rec = state.get("recommendation")
        if rec is not None:
            self.captured[rec.id] = state
        outcome = super()._apply_decision(state, i)
        rejection = state.get("rejection") or {}
        rm = state.get("risk_metrics") or {}

        def _val(name):
            m = rm.get(name)
            return getattr(m, "value", None) if m is not None else None

        regime = state.get("regime")
        self.decisions_log.append({
            "index": i,
            "time": self.replay.bars[i].start.isoformat(),
            "outcome": "executed" if outcome == "executed"
            else (f"rejected:{rejection.get('stage')}" if rejection
                  else (outcome or "hold")),
            "reasons": "; ".join(rejection.get("reasons", []) or []),
            "var_95": _val("VAR_95"),
            "cvar_95": _val("CVAR_95"),
            "regime": getattr(regime, "value", regime),
            "action": getattr(getattr(rec, "action", None), "value", None),
            "confidence": getattr(rec, "confidence", None),
        })
        if self._checkpoint_every and len(self.decisions_log) % self._checkpoint_every == 0:
            self._checkpoint()
        return outcome


def build_llm(provider_mode: str, config: ProConfig, cache_dir: Path):
    if provider_mode == "fake":
        from tests.test_pro_pipeline_graph import FakePipelineLLM

        return FakePipelineLLM(), ()
    bundle = bundle_from_config(config, temperature=0.2)
    price = price_for(config.models.llm_provider)
    quick_ct = CostTrackingLLM(bundle.quick, price=price)
    deep_ct = quick_ct if bundle.deep is bundle.quick else CostTrackingLLM(bundle.deep, price=price)
    bundle.quick = CachingLLM(quick_ct, mode="auto", path=cache_dir / "quick.jsonl")
    bundle.deep = (
        bundle.quick if deep_ct is quick_ct
        else CachingLLM(deep_ct, mode="auto", path=cache_dir / "deep.jsonl")
    )
    return bundle, ({quick_ct, deep_ct})


def _verdict(report, ext, mc, n_trades: int, provider: str) -> tuple[str, str, list[str]]:
    """Honest classification from the recorded metrics. Fake runs can never
    claim an edge (scripted model)."""
    if provider == "fake":
        return ("🔴", "No demonstrable statistical edge (NOT measured)",
                ["Deterministic/scripted model — mechanics only; model skill was "
                 "not exercised. Re-run with --provider env to measure edge."])
    reasons: list[str] = []
    prob_loss = mc.prob_loss if mc else 1.0
    beats_bh = report.total_return > ext.benchmark_total_return
    reasons.append(f"Sharpe {report.sharpe:.2f}, profit factor {report.profit_factor:.2f}, "
                   f"expectancy {report.expectancy:,.0f}/trade, n={n_trades}.")
    reasons.append(f"Monte-Carlo prob(loss) {prob_loss:.0%}; "
                   f"{'beats' if beats_bh else 'trails'} buy-&-hold "
                   f"({report.total_return:+.1%} vs {ext.benchmark_total_return:+.1%}); "
                   f"alpha {ext.alpha:+.2f}.")
    if n_trades < 20:
        reasons.append("Sample < 20 trades: any verdict is low-confidence.")
    if report.expectancy <= 0 or report.profit_factor < 1.0:
        return ("🔴", "No demonstrable statistical edge", reasons)
    if report.sharpe >= 1.0 and report.profit_factor >= 1.5 and prob_loss < 0.3 \
            and n_trades >= 20 and beats_bh:
        return ("✅", "Ready for paper trading", reasons)
    if report.sharpe >= 0.5 and prob_loss < 0.4:
        return ("🟡", "Promising but requires optimization", reasons)
    return ("🟠", "Significant improvements required", reasons)


def _md_table(headers: Sequence[str], rows: Sequence[Sequence]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def write_report_md(path: Path, ctx: dict) -> None:
    r, ext, mc = ctx["report"], ctx["ext"], ctx["mc"]
    trades = ctx["enriched"]
    agents = ctx["agents"]
    regimes = ctx["regimes"]
    emoji, label, reasons = ctx["verdict"]
    wins = [t for t in trades if t.outcome == "Win"]
    losses = [t for t in trades if t.outcome == "Loss"]

    def top(ts, key, n=20, rev=True):
        return sorted(ts, key=key, reverse=rev)[:n]

    lines: list[str] = []
    A = lines.append
    A("# BTC/USD 1-Year Backtest — TradingAgents Pro\n")
    A(f"_Generated {ctx['generated_at']} · window {ctx['window'][0]} → {ctx['window'][1]} "
      f"({ctx['bars']} daily bars) · provider `{ctx['provider']}`_\n")

    A(f"## Final Verdict: {emoji} {label}\n")
    for reason in reasons:
        A(f"- {reason}")
    A("")

    A("## 1. Executive Summary\n")
    A(f"- Decisions run: **{ctx['decisions']}** · executed: **{ctx['executed']}** · "
      f"rejections: {json.dumps(ctx['rejections'])}")
    A(f"- Closed trades: **{r.n_trades}** · win rate **{r.win_rate:.1%}** · "
      f"profit factor **{r.profit_factor:.2f}** · expectancy **{r.expectancy:,.2f}/trade**")
    A(f"- Total return **{r.total_return:+.2%}** (buy-&-hold **{ext.benchmark_total_return:+.2%}**) · "
      f"CAGR **{ext.cagr:+.2%}** · max drawdown **{r.max_drawdown:.2%}**")
    A(f"- Sharpe **{r.sharpe:.2f}** · Sortino **{r.sortino:.2f}** · Calmar **{ext.calmar:.2f}** · "
      f"alpha **{ext.alpha:+.2f}** / beta **{ext.beta:.2f}**")
    if mc:
        A(f"- Monte-Carlo (1000 paths): prob(loss) **{mc.prob_loss:.0%}**, "
          f"median final equity **{mc.final_equity_p50:,.0f}**, risk of ruin (−50%) "
          f"**{ext.risk_of_ruin:.0%}**")
    if ctx.get("est_cost_usd") is not None:
        A(f"- LLM: {ctx['llm_calls']} calls, est cost **${ctx['est_cost_usd']:.2f}**")
    A("")

    # Decision funnel — why decisions did/didn't become trades
    A("## 1a. Decision Funnel (why trades did/didn't fire)\n")
    dlog = ctx.get("decisions_log") or []
    rr = ctx.get("rejection_reasons") or {}
    stage_counts: dict[str, int] = {}
    reg_counts: dict[str, int] = {}
    for d in dlog:
        stage_counts[d["outcome"]] = stage_counts.get(d["outcome"], 0) + 1
        reg = d.get("regime") or "unknown"
        reg_counts[reg] = reg_counts.get(reg, 0) + 1
    A(_md_table(["Decision outcome", "Count"],
                sorted(stage_counts.items(), key=lambda kv: -kv[1])))
    A("")
    if rr:
        A("**Rejection reasons (most common first):**")
        A(_md_table(["Reason", "Count"], list(rr.items())))
        A("")
    A("**Regime distribution of all decisions:**")
    A(_md_table(["Regime", "Decisions"],
                sorted(reg_counts.items(), key=lambda kv: -kv[1])))
    A("\nFull per-decision funnel in `decisions.csv`.\n")

    A("## 2. Performance Metrics\n")
    A(_md_table(["Metric", "Value"], [
        ("Total return", f"{r.total_return:+.2%}"),
        ("CAGR", f"{ext.cagr:+.2%}"),
        ("Buy-&-hold return", f"{ext.benchmark_total_return:+.2%}"),
        ("Max drawdown", f"{r.max_drawdown:.2%}"),
        ("Sharpe", f"{r.sharpe:.2f}"),
        ("Sortino", f"{r.sortino:.2f}"),
        ("Calmar", f"{ext.calmar:.2f}"),
        ("Recovery factor", f"{ext.recovery_factor:.2f}"),
        ("Profit factor", f"{r.profit_factor:.2f}"),
        ("Win rate", f"{r.win_rate:.1%}"),
        ("Expectancy / trade", f"{r.expectancy:,.2f}"),
        ("Avg win / avg loss", f"{ext.avg_win:,.2f} / {ext.avg_loss:,.2f}"),
        ("Largest win / loss", f"{ext.largest_win:,.2f} / {ext.largest_loss:,.2f}"),
        ("Max consec wins / losses", f"{ext.max_consecutive_wins} / {ext.max_consecutive_losses}"),
        ("Alpha (ann.) / Beta", f"{ext.alpha:+.2f} / {ext.beta:.2f}"),
        ("Risk of ruin (−50%)", f"{ext.risk_of_ruin:.0%}"),
        ("Trades", f"{r.n_trades}"),
    ]))
    A("")

    A("## 3–6. Equity, Drawdown, Monthly Returns, Strategy\n")
    A("See `charts/equity_curve.png`, `charts/drawdown.png`, "
      "`charts/monthly_heatmap.png`, `equity.csv`, `drawdown.csv`.\n")
    A("The system runs one **regime-adaptive** multi-agent strategy (no discrete "
      "strategy switching), so strategy analysis is presented as the per-regime "
      "breakdown below.\n")

    A("## 7. Agent Performance\n")
    if agents:
        A(_md_table(
            ["Agent", "Votes", "Aligned", "Opposed", "Hit rate", "Avg conf", "Attributed P&L"],
            [(a.agent_id, a.votes, a.aligned, a.opposed, f"{a.hit_rate:.0%}",
              f"{a.avg_confidence:.0f}", f"{a.attributed_pnl:,.0f}") for a in agents]))
        A("\n_Attribution is vote-level (aligned/opposed × win/loss), not a "
          "counterfactual re-run without the agent._")
    else:
        A("_No executed trades with votes to attribute._")
    A("")

    A("## 8. Risk Analysis\n")
    A(_md_table(["Item", "Value"], [
        ("Largest winning trade", f"{ext.largest_win:,.2f}"),
        ("Largest losing trade", f"{ext.largest_loss:,.2f}"),
        ("Max drawdown", f"{r.max_drawdown:.2%}"),
        ("Risk of ruin (−50% capital)", f"{ext.risk_of_ruin:.0%}"),
        ("Stop exits", sum(1 for t in trades if t.exit_reason == "stop")),
        ("Take-profit exits", sum(1 for t in trades if t.exit_reason == "take_profit")),
        ("End-of-data exits", sum(1 for t in trades if t.exit_reason == "end_of_data")),
    ]))
    A("")

    A("## 9. Market Regime Analysis\n")
    if regimes:
        A(_md_table(
            ["Regime", "Trades", "Win rate", "Net P&L", "Profit factor", "Best", "Worst"],
            [(g.regime, g.n_trades, f"{g.win_rate:.0%}", f"{g.total_net_pnl:,.0f}",
              f"{g.profit_factor:.2f}", f"{g.best_trade:,.0f}", f"{g.worst_trade:,.0f}")
             for g in regimes]))
    else:
        A("_No executed trades to break down by regime._")
    A("")

    A("## 10. Statistical Validation\n")
    A("- **No look-ahead**: decisions use a snapshot of bars ≤ i; entries fill at "
      "bar i+1's open (`BacktestEngine.run`), so a decision never sees its own "
      "fill bar.")
    A("- **No data leakage**: an isolated `ProMemory` per run; the live book is "
      "untouched.")
    A("- **Costs modeled**: 2 bps slippage, 1 bps commission per fill, 10% "
      "volume participation cap (`backtest/costs.py`).")
    A("- **Time alignment**: equity curve is indexed by bar close time; calendar "
      "returns bucket on those timestamps.")
    A("- **Reproducible**: real-LLM responses are cached (record/replay); the "
      "scripted-model path is fully deterministic.")
    A("")

    A("## 11. Visual Dashboard\n")
    A("`charts/`: equity_curve, drawdown, monthly_heatmap, trade_distribution, "
      "win_loss_distribution, pnl_histogram, holding_time, trade_timeline, "
      "performance_by_regime, agent_leaderboard, strategy_comparison.\n")

    A("## 12. Top Winning Trades\n")
    A(_md_table(["#", "Dir", "Opened", "Net P&L", "R:R", "Regime", "Exit"],
                [(t.trade_id, t.direction, t.opened_at[:10], f"{t.net_pnl:,.0f}",
                  t.risk_reward, t.market_regime, t.exit_reason)
                 for t in top(wins, lambda x: x.net_pnl)]) if wins else "_None._")
    A("")
    A("## 13. Top Losing Trades\n")
    A(_md_table(["#", "Dir", "Opened", "Net P&L", "R:R", "Regime", "Exit"],
                [(t.trade_id, t.direction, t.opened_at[:10], f"{t.net_pnl:,.0f}",
                  t.risk_reward, t.market_regime, t.exit_reason)
                 for t in top(losses, lambda x: x.net_pnl, rev=False)]) if losses else "_None._")
    A("")

    A("## 14. Improvement Roadmap (future work)\n")
    A("- Build a point-in-time `HistoricalCorpus` so macro/sentiment/on-chain "
      "agents fire in backtest (they abstain today).")
    A("- Integrate absent feeds: liquidations, ETF flows, whale flows, SOPR; wire "
      "funding/OI/on-chain into agent specs (ingested but unread today).")
    A("- Trailing/breakeven stops and multi-position portfolio simulation in the "
      "sim broker.")
    A("- Intraday/tick replay for higher decision density.")
    A("")

    A("## 15. Production Readiness Assessment\n")
    A(f"**{emoji} {label}.** This measured the **technicals + quant/risk subsystem** "
      f"on BTC `{ctx.get('timeframe', '1d')}` bars; macro/sentiment/on-chain were "
      "inactive (no historical corpus). Treat the verdict as scoped to that "
      "subsystem and this one market/period.\n")

    A("---\n### Scope & limitations (read before citing any number)\n")
    A("- Daily bars only; one position at a time; fixed (non-trailing) stops.")
    A("- Macro/sentiment/on-chain agents abstained (no as-of corpus).")
    A("- Absent feeds: liquidations, ETF flows, whale flows, SOPR, exchange reserves.")
    A(f"- Timeframe: `{ctx.get('timeframe', '1d')}`, one position at a time, fixed "
      f"(non-trailing) stops. Costs: 2bps slippage / 1bps commission / 10% "
      f"participation. Annualization: {ctx.get('periods_per_year', 365)}/yr (24/7).")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(prog="pro_btc_backtest")
    parser.add_argument("--bars", type=int, default=365)
    parser.add_argument("--timeframe", choices=("15m", "1h", "4h", "1d"), default="1d")
    parser.add_argument("--min-history", type=int, default=100)
    parser.add_argument("--decide-every", type=int, default=1)
    parser.add_argument("--provider", choices=("fake", "env"), default="fake")
    parser.add_argument("--equity", type=float, default=100_000.0)
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--cache-dir", default=None,
                        help="reuse a prior run's llm_cache dir (free replay)")
    parser.add_argument("--checkpoint-every", type=int, default=10,
                        help="flush decisions.csv + progress.json every N decisions (0=off)")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else REPO_ROOT / "docs" / "backtests" / f"btc_1y_{stamp}"
    outdir.mkdir(parents=True, exist_ok=True)
    # reuse a prior run's LLM cache to replay evidence/debate for free
    cache_dir = Path(args.cache_dir) if args.cache_dir else outdir / "llm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    ticker, asset = "BTC-USD", AssetClass.BITCOIN
    tf = Timeframe(args.timeframe)
    periods_per_year = _PERIODS_PER_YEAR.get(tf, 365)
    print(f"fetching {args.bars} {tf.value} BTC bars…")
    if tf is Timeframe.D1:
        bars = YFinanceDailyBarsFeed().get_bars(ticker, Timeframe.D1, limit=args.bars)
    else:
        # intraday: keyless Binance spot klines (vendor symbol BTCUSDT)
        from tradingagents.pro.ingestion.binance import BinanceSpotFeed

        bars = BinanceSpotFeed().get_bars("BTCUSDT", tf, limit=args.bars)
    if len(bars) < args.min_history + 5:
        print(f"only {len(bars)} bars (need > {args.min_history + 5})", file=sys.stderr)
        return 2
    print(f"  {len(bars)} bars: {bars[0].start} → {bars[-1].start}")

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
    llm, trackers = build_llm(args.provider, config, cache_dir)

    print(f"running pipeline every {args.decide_every} bar(s), provider={args.provider}…")
    engine = _CapturingEngine(
        llm, config,
        BarReplay(ticker, asset, bars, window=args.min_history),
        broker=SimBroker(
            initial_equity=args.equity,
            max_open_positions=config.risk.max_open_positions,
            max_gross_exposure_pct=(
                config.risk.max_open_positions * config.risk.max_position_pct_equity
            ),
            max_same_direction=config.risk.max_same_direction_positions,
        ),
        memory=ProMemory(),
        min_history=args.min_history,
        decide_every=args.decide_every,
        periods_per_year=periods_per_year,
        checkpoint_dir=outdir,
        checkpoint_every=args.checkpoint_every,
    )
    result = engine.run()

    # align timestamps + benchmark closes 1:1 with the equity curve
    tail = bars[args.min_history:]
    timestamps = [b.start for b in tail][: len(result.equity_curve)]
    benchmark_closes = [b.close for b in tail][: len(result.equity_curve)]
    years = max((bars[-1].start - bars[args.min_history].start).days / 365.25, 1e-9)

    ext = extended_report(result.equity_curve, result.trades, timestamps,
                          benchmark_closes, args.equity, years, periods_per_year)
    enriched = enrich_trades(result.trades, engine.captured, args.equity)
    agents = agent_attribution(enriched)
    regimes = regime_breakdown(enriched)
    mc = monte_carlo_summary([t.pnl for t in result.trades], args.equity) \
        if len(result.trades) >= 2 else None

    est_cost = llm_calls = None
    if trackers:
        est_cost = sum(t.report.est_cost_usd for t in trackers)
        llm_calls = sum(t.report.calls for t in trackers)

    # decision funnel: aggregate rejection reasons (first clause of each) so
    # the report can explain WHY decisions died
    from collections import Counter

    reason_counts: Counter[str] = Counter()
    for d in engine.decisions_log:
        if d["outcome"].startswith("rejected") and d["reasons"]:
            reason_counts[d["reasons"].split(";")[0].strip()] += 1
    rejection_reasons = dict(reason_counts.most_common())

    # ── artifacts ──────────────────────────────────────────────────────────
    write_csv(outdir / "trades.csv", enriched)
    write_json(outdir / "trades.json", enriched)
    write_decisions_csv(outdir / "decisions.csv", engine.decisions_log)
    (outdir / "equity.csv").write_text(
        "timestamp,equity\n" + "\n".join(
            f"{t.isoformat()},{e}" for t, e in zip(timestamps, result.equity_curve, strict=False)
        ) + "\n", encoding="utf-8")
    (outdir / "drawdown.csv").write_text(
        "timestamp,drawdown\n" + "\n".join(
            f"{t.isoformat()},{d}" for t, d in zip(timestamps, ext.drawdown_curve, strict=False)
        ) + "\n", encoding="utf-8")
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider, "bars": len(bars),
        "window": [bars[0].start.date().isoformat(), bars[-1].start.date().isoformat()],
        "decisions": result.decisions, "executed": result.executed,
        "rejections": dict(result.rejections),
        "rejection_reasons": rejection_reasons,
        "base": result.report.as_dict(), "extended": ext.scalar_dict(),
        "monte_carlo": mc.__dict__ if mc else None,
        "est_cost_usd": est_cost, "llm_calls": llm_calls,
    }
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    try:
        from tradingagents.pro.backtest import charts

        cdir = outdir / "charts"
        bench_curve = [args.equity * (c / benchmark_closes[0]) for c in benchmark_closes] \
            if benchmark_closes and benchmark_closes[0] > 0 else None
        charts.equity_curve(cdir / "equity_curve.png", timestamps, result.equity_curve, bench_curve)
        charts.drawdown(cdir / "drawdown.png", timestamps, ext.drawdown_curve)
        charts.monthly_heatmap(cdir / "monthly_heatmap.png", ext.monthly_returns)
        charts.trade_distribution(cdir / "trade_distribution.png", enriched)
        charts.win_loss_distribution(cdir / "win_loss_distribution.png", enriched)
        charts.pnl_histogram(cdir / "pnl_histogram.png", enriched)
        charts.holding_time(cdir / "holding_time.png", enriched)
        charts.trade_timeline(cdir / "trade_timeline.png", enriched)
        charts.performance_by_regime(cdir / "performance_by_regime.png", regimes)
        charts.agent_leaderboard(cdir / "agent_leaderboard.png", agents)
        charts.strategy_comparison(cdir / "strategy_comparison.png", regimes)
        print(f"  charts → {_rel(cdir)}")
    except ImportError:
        print("  matplotlib not installed — skipping charts "
              "(pip install 'tradingagents[backtest-report]')")

    verdict = _verdict(result.report, ext, mc, result.report.n_trades, args.provider)
    write_report_md(outdir / "REPORT.md", {
        "generated_at": metrics["generated_at"], "window": metrics["window"],
        "bars": len(bars), "provider": args.provider,
        "decisions": result.decisions, "executed": result.executed,
        "rejections": dict(result.rejections),
        "report": result.report, "ext": ext, "mc": mc,
        "enriched": enriched, "agents": agents, "regimes": regimes,
        "verdict": verdict, "est_cost_usd": est_cost, "llm_calls": llm_calls,
        "rejection_reasons": rejection_reasons, "decisions_log": engine.decisions_log,
        "timeframe": tf.value, "periods_per_year": periods_per_year,
    })

    print(f"\n{verdict[0]} {verdict[1]}")
    print(f"trades {result.report.n_trades} · win {result.report.win_rate:.0%} · "
          f"PF {result.report.profit_factor:.2f} · Sharpe {result.report.sharpe:.2f} · "
          f"return {result.report.total_return:+.1%} (BH {ext.benchmark_total_return:+.1%})")
    if est_cost is not None:
        print(f"LLM calls {llm_calls} · est cost ${est_cost:.2f}")
    print(f"\nreport → {_rel(outdir / 'REPORT.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
