# Backtesting engine & strategy library — as-built guide

This is the user/developer guide to the backtester that the research program
([docs/research/](research/README.md)) designed and that now ships in
`tradingagents/pro/backtest` + the dashboard. It documents what exists and how
to use it. For *why* each piece looks the way it does, see the HLD/LLD
([06_hld.md](research/06_hld.md), [07_lld.md](research/07_lld.md)) and the
validation methodology ([12_validation_methodology.md](research/12_validation_methodology.md)).

## Design principles (the non-negotiables)

1. **Determinism.** Same inputs → byte-identical outputs. No wall-clock, no
   RNG except seeded (`run_optimization(..., seed=)`). Parallel optimization
   reassembles trials in submission order so results never depend on which
   worker finished first.
2. **Look-ahead safety, structurally.** A decision on bar `i` sees only bars
   `≤ i`; entries fill at bar `i+1`'s open; a position is never managed against
   the bar that produced its own decision. Higher-timeframe context exposes
   only *closed* HTF bars. Indicators warm up honestly (no value inside the
   warm-up window).
3. **Honesty-first metrics.** The optimizer never reports a "best" without its
   overfitting guards (deflated Sharpe, PBO) and a plain-language verdict.
   Costs are modelled, not wished away. `null`/`—` where a number is undefined,
   never a fabricated one.
4. **Full-fidelity artifacts.** Every decision and every trade is persisted;
   charts read the artifacts, never a downsampled copy.

## Running a backtest

`POST /api/backtest/run` starts a background job (202 + `job_id`); progress
streams over `/api/stream` and the record lands in the run history.

Request (see `BacktestRunRequest` in `dashboard/backtest_job.py`):

| field | meaning |
|---|---|
| `symbol` | `BTC-USD`, `ETH-USD`, `SOL-USD`, `XAUUSD` |
| `timeframe` | `5m` `15m` `1h` `4h` `1d` (per the asset's support) |
| `duration` | `1D` `7D` `30D` `1Y` |
| `strategy_id` | a registered strategy (see the library below) |
| `strategy_params` | dict validated against the strategy's `ParamSpace` |
| `initial_equity`, `risk_per_trade_pct`, `max_position_pct` | sizing |
| `use_llm` / `confirm_cost` | real-LLM pipeline path (costs money, cost-gated) |

What happens: fetch the window (paged, retried) → build a look-ahead-safe
`BarReplay` → for each bar, fill orders resting from prior bars, manage open
positions, then (throttled) decide → persist equity/trades/decisions(/orders)
artifacts. The run **view** carries the report metrics, provenance
(`strategy_id`, `indicator_mode`, sizing), the `costs` profile used, the
`window`, and `schema_version`.

Cancel with `POST /api/backtest/cancel` — the partial is saved, labelled
`cancelled`. An instance restart mid-run recovers the partial as `interrupted`.

## The strategy library

All strategies are **registry-driven**: registering one makes it appear
automatically in the run picker, the optimizer, and portfolio baskets. Six are
native (order-book) strategies; each is long & short and computed only from the
look-ahead-safe snapshot window.

| id | archetype | entry | exit |
|---|---|---|---|
| `trend_following_v1` | Channel breakout | Donchian break of the N-bar high/low | ATR stop + % trailing |
| `mean_reversion_v1` | Fade | close beyond `entry_std`·σ from the SMA | target = the SMA (mean); ATR stop |
| `momentum_v1` | Rate-of-change | \|ROC\| over `roc_period` > `roc_threshold`% | fixed-R: ATR stop + ATR target |
| `ma_crossover_v1` | MA cross | fast SMA crosses slow SMA (golden/death) | ATR stop + % trailing |
| `htf_momentum_v1` | HTF-confirmed momentum | ROC entry **only with** the higher-timeframe trend | fixed-R ATR stop/target |
| `volatility_breakout_v1` | Volatility regime | band-width squeeze then break out of the band | ATR stop + % trailing |

Plus two pipeline strategies: `rules_v1` (the deterministic indicator-rules
pipeline; bit-for-bit the legacy path) and `pipeline_llm` (the real-LLM
operator bundle; job-built, costs money).

Every native strategy exposes an `allow_short` toggle and `risk_pct`; the rest
of its params are its genuine knobs (declared in `*_PARAMS`). `GET
/api/backtest/strategies` returns each strategy's id, description, and param
schema — that's what the UI renders dynamically.

## Writing a new strategy (the SDK)

A native strategy is any object implementing the `Strategy` protocol
(`backtest/strategy.py`): `on_start(ctx)`, `on_bar(ctx) -> list[OrderIntent]`,
`on_fill(fill)`, `on_stop(ctx)`. `ctx` (a `StrategyContext`) gives the
look-ahead-safe `snapshot` (bars + indicators), `equity`, `params`, open
`positions`, `account`, and — when configured — `htf` (completed
higher-timeframe snapshots).

An `OrderIntent` carries a `kind` (`market`/`limit`/`stop_entry`/`stop_limit`),
`side`, sizing (`risk_pct` **or** explicit `quantity`), and a `BracketIntent`
(`stop_loss`, `take_profits`, optional `trailing`). Declare tunables with a
`ParamSpace` of `Param`s and register:

```python
@register("my_strategy_v1", MY_PARAMS, description="…")
def _build(params): return MyStrategy(params)
```

That is the entire integration — no engine/endpoint/UI changes. To consult a
higher timeframe, set a class attribute `htf_timeframes = (Timeframe.D1, …)`;
the dashboard job aggregates whichever are strictly coarser than the run's
timeframe and populates `ctx.htf` (look-ahead-safe). See `htf_momentum_v1` for
a worked example, and `10_strategy_sdk.md` for the design.

## Optimization + overfitting guards

`POST /api/backtest/optimize` grid-searches a strategy's params (each trial a
child backtest on the same window) and — crucially — attaches the guards to the
selected best:

- **Deflated Sharpe** — the winner's Sharpe deflated for the number of trials
  tried (winning a big search is not the same as having an edge).
- **PBO** (probability of backtest overfitting, via CSCV) — how often the
  in-sample best fails out-of-sample.
- **verdict** — plain language: a red "no evidence of out-of-sample edge — do
  not deploy" when PBO is high or the deflated Sharpe is below ~0.6.

Trials run on a process pool where cores allow (deterministic regardless).
`run_walk_forward_optimization` fits on train / scores on an embargoed test
slice for a true out-of-sample read. This anti-overfitting posture is the
platform's core differentiator — see [12_validation_methodology.md](research/12_validation_methodology.md).

## Portfolio & multi-timeframe

`POST /api/backtest/portfolio` runs one native strategy over a 2–6 symbol
basket on a shared broker (`PortfolioReplay` merges the per-symbol series on one
master clock; each symbol decides from its own look-ahead-safe bars). The
broker's position and gross-exposure caps bind **across** the basket
(portfolio heat); an **equal-weight capital allocator** caps each symbol's
share, and an optional **correlation guard** vetoes a fresh entry too
correlated with the open book. Result is a normal run record (`is_portfolio`),
so it renders in the existing history/result views.

Multi-timeframe: a strategy that declares `htf_timeframes` receives completed
higher-timeframe `MarketSnapshot`s in `ctx.htf` (`htf_momentum_v1` uses this to
trade only with the bigger trend).

## Cost realism

Fills carry per-asset execution costs (`cost_profile_for`): a fixed slippage +
half-spread + **square-root market impact** (`impact_bps · √participation`, so
a larger share of a bar's volume costs more) + a venue commission. The run view
discloses the exact `costs` used. Perpetual **funding** is available opt-in
(`FundingModel`) for perp backtests.

> The default cost profiles are **conservative modelling assumptions, not
> measured venue data** — calibrate them to your own broker/exchange before
> trusting absolute net returns.

## Performance & risk metrics

Every run's report carries: total/annualized return, Sharpe, Sortino,
**MAR** (annualized return ÷ max drawdown), **Omega**, **Ulcer index** (RMS
drawdown), max drawdown, profit factor, win rate (ex-scratch), expectancy in R,
and **edge stability** (share of 30-bar rolling windows with Sharpe > 0 — a
fast "did the edge hold up over time?" read). R-multiples come from the risk
unit (`qty · |entry − initial stop|`).

## Determinism & look-ahead — the guarantees, restated

- The single-symbol path is **byte-identical** to before any given upgrade
  when that upgrade's knobs are off (locked by
  `tests/test_pro_strategy_equivalence.py`).
- Costs default to bps-only behaviour when spread/impact are 0; funding and the
  correlation guard are off by default; `htf` is empty unless configured.
- Optimization is deterministic and order-independent whether serial or pooled.

## Where things live

```
tradingagents/pro/backtest/
  strategy.py        Strategy protocol, StrategyContext, OrderIntent, ParamSpace
  registry.py        register / build_strategy / list_strategies
  strategies.py      the 6 native strategies + rules_v1 (pipeline)
  data.py            BarReplay (look-ahead-safe snapshots) + HistoricalCorpus
  broker.py          SimBroker: order book, brackets, trailing, R accounting
  engine.py          BacktestEngine loop (single-symbol)
  portfolio.py       PortfolioReplay (k-way merge)
  portfolio_engine.py PortfolioEngine (shared-broker, multi-symbol)
  allocator.py       EqualWeight / Weighted capital allocators
  correlation.py     CorrelationGuard
  multitf.py         HTF aggregation + MultiTimeframeReplay
  costs.py           Slippage(+impact/spread) / Commission / Liquidity / Funding / cost_profile_for
  optimize.py        grid/random search + guards + verdict + process pool
  walkforward.py     walk-forward fitting (embargo)
  validation.py      deflated Sharpe, PBO, PSR
  metrics.py         performance report + extended analytics
tradingagents/pro/dashboard/
  backtest_job.py    run / optimize / portfolio jobs + request models
  app.py             the /api/backtest/* endpoints
frontend/src/features/backtest/  the Backtest page (run / portfolio / optimize)
```

Tests: `python -m pytest tests/ -k pro_` (backtest suites are `test_pro_*`).
Frontend: `npm --prefix frontend test` + `npm --prefix frontend run build`.
