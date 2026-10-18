# Prospective signal evaluation

A model used on a historical date can already know what happened next, even
when every tool respects that date. Restricting tool data does not remove that
knowledge from its weights. This is the model-level limitation tracked in
[#805](https://github.com/TauricResearch/TradingAgents/issues/805).

Forward evaluation changes the experiment: record the signal before its outcome
exists, then fetch the outcome later. It does not repair a historical backtest
or certify a model's training cutoff. The ledger provides mechanical checks
under a trusted local clock, exchange calendar and price source.

## Register, record, score

`ForwardEvaluation` is optional and separate from the graph and memory log.
It uses only the Python standard library and never places orders. Register a
fixed universe, model declarations, run settings and rule before any decisions:

```python
from tradingagents.evaluation.forward import (
    EvaluationConfig, ForwardEvaluation, ModelDeclaration, PriceBar,
)

# config is the graph's JSON-compatible configuration, including any custom
# prompt/version settings. Only its SHA-256 fingerprint is persisted.
experiment = ForwardEvaluation.create(
    "forward.sqlite",
    EvaluationConfig(tickers=("NVDA", "AAPL")),
    [
        ModelDeclaration(config["deep_think_llm"],
                         config.get("deep_think_provider") or config["llm_provider"],
                         knowledge_cutoff=None),
        ModelDeclaration(config["quick_think_llm"],
                         config.get("quick_think_provider") or config["llm_provider"],
                         knowledge_cutoff=None),
    ],
    run_config=config,
)
```

Declare published cutoffs as `YYYY-MM-DD`, or `None` when unknown; they are
metadata, not evidence that the model is uncontaminated. Include every model
used by the experiment (including optional screening models). Pin model versions
where possible. Changing models, prompts, settings or the rule means starting
a separate ledger and reporting that additional experiment.

Run after the analysis session's close, before its next open. Supply that
**scheduled** next open from an exchange calendar, in the exchange timezone;
do not calculate it by finding the first open after the current wall clock:

```python
# load_bars(ticker) returns a complete, chronological daily session series of
# PriceBar(open_at=<actual timezone-aware open>, open=<price>,
#          close_at=<actual timezone-aware close>, close=<price>).
# next_open is the calendar's next session open after analysis_date.
for ticker in experiment.config.tickers:
    state, rating = ta.propagate(ticker, analysis_date)
    experiment.record(
        ticker, analysis_date, rating, next_open,
        prices=load_bars, run_config=config,
    )

# Later, when subsequent session opens have actually traded:
experiment = ForwardEvaluation("forward.sqlite")
result = experiment.score(load_bars)
print(result["verdict"], result["metrics"])
```

The clock is stamped after fetching history and acquiring the write lock.
Recording at or after the scheduled entry open marks the decision
`retrospective`; it cannot enter the verdict. Each ticker/date can be recorded
only once. A resumed historical graph run is not a prospective decision merely
because it was saved today. The scorer checks the scheduled entry against the
first available session after the analysis date and never shifts a missing
entry to a later bar.

## Price adapter contract

Price fetching is injected as `load_bars(ticker) -> Iterable[PriceBar]`. Tests
use synthetic prices offline. The adapter must provide complete session history,
including at least 22 completed closes at recording for the momentum reference,
and every session from the entry through the eventual exit. No close beyond
the recording clock is used; no open beyond the scoring clock is filled.
The first priced leg is persisted even while the exit remains pending, and
neither leg is repriced on later runs. Provider errors propagate; they must not
silently become zero returns.

Daily Yahoo-style timestamps often label a date at midnight. They are **not**
the actual open/close instants required here: convert them using the exchange
calendar, including holidays, early closes and daylight saving time. Keep price
adjustments consistent across legs. Missing intermediate sessions cannot be
detected without a calendar in the adapter and must not be omitted. For
delistings or unavailable data, disclose pending observations, rather than
dropping them to select a better sample.

## Declared measurement conventions

- Entry is the scheduled next session's open; exit is the open
  `horizon_sessions` sessions later (default 1). Fills are signal-scoring
  reference prices, not a claim of executable liquidity.
- Buy/Overweight mean +1, Sell/Underweight -1, Hold 0. `REVIEW` is unscored,
  never converted to Hold. Optional size/confidence are recorded as metadata;
  they do not change the unit-direction test.
- Equal weights cover the entire registered universe, including idle Hold
  slices. Long and momentum references use exactly the same tickers/days/fills.
  Momentum is the sign of the last completed close divided by the close 21
  sessions earlier minus one, frozen at recording. Zero momentum stays flat.
- A position's net return is `direction * (exit / entry - 1)` minus twice
  `cost_bps_per_side / 10000`. Flat slices pay no cost. These are simple,
  unlevered directional returns, not a cash ledger.
- A session is one analysis date with every registered ticker recorded and
  filled. Partial sessions stay pending. A missing momentum history or REVIEW
  makes the whole session unscored, including its baseline observations.
- Metrics expose per-session net returns, mean return, sample-standard-deviation
  Sharpe, and gross directional hit rate over non-flat positions. Annualization
  is `sqrt(sessions_per_year / horizon_sessions)`, default `sqrt(252)`.
  Zero variance produces an undefined Sharpe (`null`), not an infinite score.
- The default rule needs 40 completed, non-overlapping sessions, net Sharpe
  at least 1.0, and strictly higher Sharpe than both references. An undefined
  Sharpe cannot count as a win. Until the sample is reached the verdict is
  `insufficient`; then it is `passed` or `failed`.
- The verdict uses the first required sample and is persisted by scoring;
  later metrics keep updating but cannot turn a failed fixed-sample verdict
  into a pass. `verdict_sharpes` reports the fixed sample separately from the
  ongoing `metrics`. Earlier pending sessions block the verdict. For horizons above
  one, schedule non-overlapping windows; overlapping windows remain descriptive
  and return `insufficient`.

This is not a significance test or proof of investable alpha. Costs do not
model borrow, funding, market impact, spreads or corporate-action execution.
Keep all attempted experiments and disclose failed runs and unscored sessions.
Point-in-time inputs, archived prompts and externally timestamped ledger backups
remain the operator's responsibility. SQLite rejects updates/deletes through
ordinary SQL, but someone controlling the file or local clock can still tamper
with it; this is not a cryptographic timestamp service.

## Thin CLI

No graph or vendor is launched by the CLI:

```bash
python -m tradingagents.evaluation.forward init forward.sqlite --protocol protocol.json
python -m tradingagents.evaluation.forward record forward.sqlite --decision decision.json --prices prices.json
python -m tradingagents.evaluation.forward score forward.sqlite --prices prices.json
python -m tradingagents.evaluation.forward summary forward.sqlite
```

`protocol.json` contains `evaluation` (the `EvaluationConfig` fields), `models`
(objects with `model_id`, `provider`, `knowledge_cutoff`) and `run_config`.
`decision.json` contains `ticker`, `decision_date`, `action`, `next_open`
(ISO timestamp with exchange offset), `run_config`, and optional `size` and
`confidence`. Both configurations must fingerprint identically.
`prices.json` maps each ticker to objects with `open_at`, `open`, and optional
paired `close_at`/`close`; timestamps include offsets. Supply newly available
prices on later scoring invocations. Treat configuration input files as private
if they contain credentials; the ledger stores only their fingerprint.
