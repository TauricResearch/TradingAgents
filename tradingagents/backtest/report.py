"""Score a stored backtest and write its report.

This is the cheap half of a backtest: everything here reads the decision store
and a price frame, so a finished run can be re-scored under a different weight
map or cost model without another LLM call.

The markdown scorecard is written to be pasted straight into an issue or a PR,
which is why the baselines sit next to the headline number rather than in an
appendix — a return figure with no reference point is not a result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tradingagents.backtest.metrics import (
    TRADING_DAYS_PER_YEAR,
    buy_and_hold,
    compute_metrics,
    cost_per_alpha_point,
    hit_rate,
    random_rating_baseline,
)
from tradingagents.backtest.portfolio import PortfolioConfig, simulate_multi
from tradingagents.backtest.store import DecisionStore

# Shown verbatim at the top of every scorecard. The framework is a research
# tool and its own README disclaims investment advice; a document full of
# return figures is exactly where that needs restating.
DISCLAIMER = (
    "Research output from a simulated backtest, not investment advice. "
    "Simulated results come from an LLM-driven pipeline whose decisions vary "
    "between runs, and they do not account for market impact, borrow costs, "
    "taxes, or the survivorship of the tickers chosen."
)


def score(
    store: DecisionStore,
    prices_by_ticker: dict[str, pd.DataFrame],
    signature: str | None = None,
    benchmark: str | None = None,
    benchmark_prices: pd.DataFrame | None = None,
    config: PortfolioConfig | None = None,
    n_baseline_trials: int = 200,
) -> dict:
    """Turn stored decisions into a full scorecard payload."""
    config = config or PortfolioConfig()
    records = store.decisions(signature)
    failures = store.failures(signature)

    decisions_by_ticker: dict[str, list[tuple[str, str | None]]] = {}
    for record in records:
        decisions_by_ticker.setdefault(record.ticker, []).append(
            (record.date, record.rating)
        )

    combined, per_ticker = simulate_multi(decisions_by_ticker, prices_by_ticker, config)
    metrics = compute_metrics(combined.equity)

    benchmark_curve = (
        buy_and_hold(benchmark_prices, config.initial_cash)
        if benchmark_prices is not None and not benchmark_prices.empty
        else None
    )
    benchmark_metrics = (
        compute_metrics(benchmark_curve) if benchmark_curve is not None else None
    )
    alpha = (
        metrics.total_return - benchmark_metrics.total_return
        if benchmark_metrics is not None
        else None
    )

    # Buy-and-hold of the traded names, sized the same way the sleeves are.
    hold_curves = [
        buy_and_hold(prices_by_ticker[t], config.initial_cash / max(len(per_ticker), 1))
        for t in per_ticker
        if t in prices_by_ticker
    ]
    hold_metrics = _combine_and_measure(hold_curves)

    ratings = [r.rating for r in records]
    tokens_in = sum(r.tokens_in for r in records)
    tokens_out = sum(r.tokens_out for r in records)
    priced = [r.cost_usd for r in records if r.cost_usd is not None]
    total_cost = sum(priced) if priced else None

    hits, scored = _aggregate_hit_rate(decisions_by_ticker, prices_by_ticker)
    baseline = _single_ticker_baseline(
        decisions_by_ticker, prices_by_ticker, per_ticker,
        metrics.total_return, config, n_baseline_trials,
    )

    return {
        "disclaimer": DISCLAIMER,
        "signature": signature,
        "execution": {
            "hold_policy": config.hold_policy,
            "allow_short": config.allow_short,
            "commission_bps": config.commission_bps,
            "slippage_bps": config.slippage_bps,
            "initial_cash": config.initial_cash,
            "fill_rule": "next bar's open after the decision date",
        },
        "coverage": {
            "n_decisions": len(records),
            "n_failed": len(failures),
            "n_review": sum(1 for r in ratings if r == "REVIEW"),
            "tickers": sorted(decisions_by_ticker),
            "rating_mix": _rating_mix(ratings),
            # min/max, not records[0]: decisions() sorts by (ticker, date), so
            # the first record is the alphabetically-first ticker's start, not
            # the earliest decision in the run.
            "first_decision": min((r.date for r in records), default=None),
            "last_decision": max((r.date for r in records), default=None),
        },
        "performance": metrics.as_dict(),
        "alpha": alpha,
        "benchmark": {
            "ticker": benchmark,
            "total_return": benchmark_metrics.total_return if benchmark_metrics else None,
        },
        "buy_and_hold": hold_metrics,
        "random_baseline": baseline.as_dict() if baseline else None,
        "trading": {
            "n_trades": len(combined.trades),
            "turnover": combined.turnover,
            "total_costs": combined.total_costs,
            "hit_rate": hits,
            "hit_rate_n": scored,
        },
        "cost": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "llm_calls": sum(r.llm_calls for r in records),
            "tool_calls": sum(r.tool_calls for r in records),
            "wall_seconds": sum(r.wall_seconds for r in records),
            "total_usd": total_cost,
            "unpriced_decisions": len(records) - len(priced),
            "cost_per_alpha_point": (
                cost_per_alpha_point(alpha, total_cost) if alpha is not None else None
            ),
        },
        "per_ticker": {
            ticker: compute_metrics(result.equity).as_dict()
            for ticker, result in per_ticker.items()
        },
        "_equity": combined.equity,
        "_benchmark_equity": benchmark_curve,
    }


def _combine_and_measure(curves: list[pd.Series]) -> dict | None:
    """Sum aligned equity curves and measure the result."""
    curves = [c for c in curves if len(c)]
    if not curves:
        return None
    index = curves[0].index
    for curve in curves[1:]:
        index = index.union(curve.index)
    total = sum(c.reindex(index).ffill().bfill() for c in curves)
    return compute_metrics(total).as_dict()


def _rating_mix(ratings: list[str | None]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for rating in ratings:
        key = rating or "unknown"
        mix[key] = mix.get(key, 0) + 1
    return dict(sorted(mix.items(), key=lambda kv: -kv[1]))


def _aggregate_hit_rate(decisions_by_ticker, prices_by_ticker) -> tuple[float, int]:
    """Pool directional calls across tickers into one hit rate."""
    total_hits = 0.0
    total_scored = 0
    for ticker, decisions in decisions_by_ticker.items():
        if ticker not in prices_by_ticker:
            continue
        rate, scored = hit_rate(decisions, prices_by_ticker[ticker])
        total_hits += rate * scored
        total_scored += scored
    return (total_hits / total_scored if total_scored else 0.0), total_scored


def _single_ticker_baseline(
    decisions_by_ticker, prices_by_ticker, per_ticker, agent_return, config, n_trials
):
    """Random-rating baseline, for a single-ticker run.

    Shuffling ratings across a multi-sleeve portfolio would need each sleeve's
    mix permuted and recombined, which is a different and heavier computation.
    Rather than report a baseline that does not mean what it appears to, it is
    reported only where it is exactly right — the single-ticker case — and
    omitted otherwise.
    """
    if len(per_ticker) != 1:
        return None
    ticker = next(iter(per_ticker))
    if ticker not in prices_by_ticker:
        return None
    return random_rating_baseline(
        decisions_by_ticker[ticker], prices_by_ticker[ticker],
        agent_return, config, n_trials=n_trials,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_report(payload: dict, out_dir: str | Path) -> Path:
    """Write ``scorecard.md``, ``scorecard.json`` and ``equity.csv``.

    Returns the path of the markdown scorecard.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    equity = payload.get("_equity")
    benchmark_equity = payload.get("_benchmark_equity")
    if equity is not None and len(equity):
        frame = pd.DataFrame({"equity": equity})
        if benchmark_equity is not None and len(benchmark_equity):
            frame["benchmark"] = benchmark_equity.reindex(frame.index).ffill()
        frame.to_csv(out_dir / "equity.csv")

    serializable = {k: v for k, v in payload.items() if not k.startswith("_")}
    (out_dir / "scorecard.json").write_text(
        json.dumps(serializable, indent=2, default=str), encoding="utf-8"
    )

    path = out_dir / "scorecard.md"
    path.write_text(render_markdown(payload), encoding="utf-8")
    return path


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:+.2%}"


def _num(value, places=2) -> str:
    return "n/a" if value is None else f"{value:,.{places}f}"


def render_markdown(payload: dict) -> str:
    """Render the scorecard as markdown suitable for pasting into an issue."""
    coverage = payload["coverage"]
    performance = payload["performance"]
    trading = payload["trading"]
    cost = payload["cost"]
    execution = payload["execution"]

    lines = [
        "# Backtest scorecard",
        "",
        f"> {payload['disclaimer']}",
        "",
        "## Result",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total return | {_pct(performance['total_return'])} |",
        f"| Annualized | {_pct(performance['annualized_return'])} |",
        f"| Alpha vs {payload['benchmark']['ticker'] or 'benchmark'} | {_pct(payload['alpha'])} |",
        f"| Sharpe | {_num(performance['sharpe'])} |",
        f"| Sortino | {_num(performance['sortino'])} |",
        f"| Max drawdown | {_pct(performance['max_drawdown'])} |",
        f"| Volatility (ann.) | {_pct(performance['volatility'])} |",
    ]

    # Annualising a short window multiplies up whatever the market happened to
    # do over a handful of weeks. The figure is still shown — it is the
    # conventional one — but a run this short should not be read as a rate.
    if 0 < performance["n_days"] < TRADING_DAYS_PER_YEAR:
        lines += [
            "",
            f"_Annualized and Sharpe figures extrapolate from "
            f"{performance['n_days']} trading days. Treat them as descriptive "
            f"of this window, not as an expected rate._",
        ]

    lines += [
        "",
        "## Against the baselines",
        "",
        "A return figure without a reference point is not a result.",
        "",
        "| Reference | Total return |",
        "| --- | --- |",
        f"| **The agents** | {_pct(performance['total_return'])} |",
    ]

    if payload["benchmark"]["total_return"] is not None:
        label = payload["benchmark"]["ticker"] or "benchmark"
        lines.append(
            f"| Buy and hold {label} | {_pct(payload['benchmark']['total_return'])} |"
        )
    if payload["buy_and_hold"]:
        lines.append(
            f"| Buy and hold the traded names | "
            f"{_pct(payload['buy_and_hold']['total_return'])} |"
        )

    baseline = payload["random_baseline"]
    if baseline:
        lines += [
            f"| Random ratings, median of {baseline['n_trials']} | "
            f"{_pct(baseline['median_return'])} |",
            f"| Random ratings, 5th-95th pct | "
            f"{_pct(baseline['p05_return'])} to {_pct(baseline['p95_return'])} |",
            "",
            f"The agents beat **{baseline['agent_percentile']:.0%}** of random "
            "sequences drawn from their own rating mix. A value near 50% means "
            "the ratings carried no timing information beyond their directional "
            "bias.",
        ]
    else:
        lines += [
            "",
            "_The random-rating baseline is reported for single-ticker runs, "
            "where shuffling the agent's own rating mix is an exact comparison._",
        ]

    lines += [
        "",
        "## Trading",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Decisions | {coverage['n_decisions']} |",
        f"| Trades | {trading['n_trades']} |",
        "| Hit rate | "
        + (
            f"{trading['hit_rate']:.1%} of {trading['hit_rate_n']} directional calls |"
            if trading["hit_rate_n"]
            else "n/a (no directional call had a full forward window) |"
        ),
        f"| Turnover | {_num(trading['turnover'])}x average equity |",
        f"| Costs paid | {_num(trading['total_costs'])} |",
        f"| Rating mix | {_format_mix(coverage['rating_mix'])} |",
        f"| REVIEW (unparseable) | {coverage['n_review']} |",
        f"| Failed decisions | {coverage['n_failed']} |",
        "",
        "## What it cost to produce",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| LLM calls | {cost['llm_calls']:,} |",
        f"| Tool calls | {cost['tool_calls']:,} |",
        f"| Tokens in / out | {cost['tokens_in']:,} / {cost['tokens_out']:,} |",
        f"| Wall time | {cost['wall_seconds'] / 60:,.1f} min |",
    ]

    if cost["total_usd"] is not None:
        lines.append(f"| Spend (upper bound) | ${_num(cost['total_usd'])} |")
        if cost["cost_per_alpha_point"] is not None:
            lines.append(
                f"| **Cost per point of alpha** | "
                f"${_num(cost['cost_per_alpha_point'])} |"
            )
    else:
        lines.append("| Spend | unpriced |")

    if cost["unpriced_decisions"]:
        lines += [
            "",
            f"_{cost['unpriced_decisions']} decision(s) had no price for their "
            "model, so spend is not reported for them. Supply rates via "
            "`config['llm_prices']` or `TRADINGAGENTS_LLM_PRICES` to enable cost "
            "reporting. Where spend is shown it applies the more expensive of "
            "the two configured models to all tokens, making it an upper bound._",
        ]

    lines += [
        "",
        "## How it was run",
        "",
        f"- Fills: {execution['fill_rule']}",
        f"- Hold policy: `{execution['hold_policy']}`",
        f"- Shorting: {'enabled' if execution['allow_short'] else 'disabled (long only)'}",
        f"- Costs: {execution['commission_bps']}bp commission + "
        f"{execution['slippage_bps']}bp slippage per side",
        f"- Starting capital: {_num(execution['initial_cash'])}, split evenly "
        f"across {len(coverage['tickers'])} ticker(s)",
        f"- Tickers: {', '.join(coverage['tickers']) or 'none'}",
        f"- Window: {coverage['first_decision']} to {coverage['last_decision']}",
    ]
    if payload.get("signature"):
        lines.append(f"- Run signature: `{payload['signature']}`")

    if payload["per_ticker"] and len(payload["per_ticker"]) > 1:
        lines += ["", "## Per ticker", "", "| Ticker | Total return | Sharpe | Max DD |",
                  "| --- | --- | --- | --- |"]
        for ticker, stats in sorted(payload["per_ticker"].items()):
            lines.append(
                f"| {ticker} | {_pct(stats['total_return'])} | "
                f"{_num(stats['sharpe'])} | {_pct(stats['max_drawdown'])} |"
            )

    return "\n".join(lines) + "\n"


def _format_mix(mix: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in mix.items()) or "none"
