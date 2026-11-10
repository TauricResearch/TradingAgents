# Changelog

All notable changes to TradingAgents are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Changes that need action when upgrading are listed under "Upgrading from" in their release.

<!--
Istruzioni per l'agente AI:
- Aggiorna la sezione [Unreleased] nella stessa Pull Request che introduce la modifica.
- Aggiungi solo modifiche effettivamente implementate, non le attività pianificate nel contratto.
- Usa le categorie Added, Changed, Deprecated, Removed, Fixed, Security quando pertinenti.
- Descrivi l'effetto per l'utente o il comportamento del sistema, non ogni file toccato.
- Non inventare PR, issue, URL, versioni, date o esiti dei test.
- Non spostare le voci in una versione pubblicata senza autorizzazione esplicita.
- Se una modifica di una PR non viene integrata, non deve apparire nel changelog del branch predefinito (custom).
-->

## [Unreleased]

## [0.8.0] — 2026-11-10

### Added

- **Version badge in the web console.** The page header shows the running
  version (e.g. `v0.8.0`) as a pill, and `/api/health` and `/api/options`
  return it as `version`, so a browser tab can be matched to the build it is
  served by. The start-up line of `python -m webapp` names the same version.
- **Every analysis keeps its own record.** `dataflows/run_record.py` writes one
  file per run under `results_dir/<ticker>/runs/`, addressed by a unique run id
  (UTC timestamp, ticker, random suffix). Each record carries the run id, the
  analysis and creation timestamps, the git commit, a build id, the service
  start time, the Python version, the loaded-validator status, the model
  configuration, the input snapshot and portfolio, the SEC filings known at the
  analysis date, the metric registry, the agents' reports, the decision, the
  risk assessment and the Execution Gate verdict. Records are written
  owner-only, credentials are redacted, long agent reports are truncated with
  the truncation recorded, and an existing record is never replaced.
- **Retention is explicit and bounded.** `run_record_keep` (default `None`,
  keeps everything) prunes oldest-first per instrument and always keeps the
  newest record; `run_record_max_text_chars` (default 20,000) caps each stored
  report.
- **`/api/health` identifies the running code.** The payload now reports
  `build.commit`, `build.build_id`, `build.service_started_at`, the interpreter
  version and a per-component `validators` map stating whether the math engine,
  valuation, technical, registry, extraction, risk engine, execution gate and
  arithmetic guard are loaded and expose their expected callables. No paths,
  environment values or credentials are exposed.
- **End-to-end reliability suite.** A frozen BRK-B fixture
  (`tests/fixtures/brkb_2026_11_09.py`) supplies Q3 2026 SEC figures, prices,
  indicators, an intraday snapshot and a simulated book, alongside expected
  values computed independently of the code. `tests/test_p4_e2e_brkb.py` drives
  the whole pipeline over it, `tests/test_p4_determinism.py` repeats the run five
  times and proves the certified mathematics does not move,
  `tests/test_p4_negative.py` injects ten named defects and asserts each is
  caught and never authorized, and `tests/test_p4_execution_boundary.py` spies
  on the gate and asserts no order is created for an invalid plan.
- **Deployment verification procedure.** `docs/DEPLOYMENT_VERIFICATION.md`
  documents how to compare a deployment's target commit against the running
  process, how to rehearse in an isolated environment, which checks gate the
  restart, and the rollback path. The restart step is marked as requiring
  explicit authorization and no script performs it.
- **A dedicated CI job for the end-to-end suites.** `e2e-reliability` runs the
  P4, P3, P2 and P1 reliability tests offline on one interpreter, so a P0
  failure is legible in the checks list rather than buried in the regression
  job's output.

- **The math engine now runs inside a real analysis.** A finished run reads the
  labelled figures its analysts stated, computes the valuation multiples with
  the deterministic engine, and hands the result to the Execution Gate as a
  certified-metric registry. A multiple quoted in a report is now checked
  against a computation instead of being taken at its word, and a figure the
  model authored is marked `LLM_CLAIMED` — reported, never certified.
- **`dataflows/math/extraction.py`** reads the labelled valuation figures out of
  the finished reports (price-to-book, EPS trailing and forward, book value per
  share, consolidated revenue), keeping the label it matched as provenance and
  applying the modelled scale, so "105,647 million" and "359,5599" are read as
  the numbers they are.
- **Portfolio input accepts an equity figure.** `PortfolioContext` carries
  `equity`, the capital base the exposure caps are a fraction of, distinct from
  the free cash balance. Sizing is computed from the run's own portfolio rather
  than skipped.
- **XBRL concepts keep their meaning.** `dataflows/vendors/concept_resolution.py`
  classifies revenue tags as consolidated, contract, segment or component, and
  `sec_edgar._as_of_with_provenance` records the concept, accession, form, period,
  unit and dimensions with each figure. Candidate tags are ordered by **meaning
  before spelling**, so a filer's consolidated total outranks a component however
  the tags are listed. Asking for consolidated revenue from a filer that reports
  only contract revenue now returns *missing* with the rejected candidate named,
  rather than substituting the subset.
- **Bar finality travels with the price.** `dataflows/vendors/bar_finality.py`
  reports `EOD_CONFIRMED`, `EOD_PENDING_CONFIRMATION`, `INTRADAY_PARTIAL`,
  `STALE` or `UNKNOWN`, with session date, exchange timezone, observation and
  source timestamps, last confirmed close, source and calendar. It uses the
  existing exchange calendar, so holidays and 13:00 closes are honoured. The
  verified market snapshot now states the bar's finality and, when provisional,
  instructs the agent not to quote it as a close or derive an end-of-day signal
  from it.

### Changed

- **A trailing P/E is only certified on a reconciled EPS.** The multiple is
  registered after the EPS reconciliation, so a price-to-earnings built on a
  vendor EPS whose denominator is unknown is `UNSUPPORTED` rather than
  `VERIFIED`. Previously the audit could certify a P/E while marking the EPS
  behind it unverifiable.
- **Sizing is attempted whenever a plan has numbers.** The engine runs with a
  missing budget or missing equity instead of being skipped, so the refusal
  names its own cause (`RISK_BUDGET_MISSING`, `PORTFOLIO_CONTEXT_MISSING`)
  instead of being reported as an unrelated gate reason. The audit's
  `qty_proposed` and `planned_risk` are populated when a size exists.

### Fixed

- **A misspelt portfolio field fails at the edge.** `PortfolioContext` rejects
  unknown keys instead of ignoring them: an earlier revision dropped `equity`
  silently, which left every plan unsized with no visible cause.
- **The metric registry is populated for real runs.** Extraction feeds
  `build_run_registry`, which previously read only state keys no node wrote, so
  every valuation metric came out `NOT_COMPUTABLE` and no figure was ever
  checked.
- **A numeric capture group that can be absent no longer raises.** The forward
  EPS pattern alternates between a plain and a tabular shape; reading a fixed
  group made extraction throw whenever the second shape matched.
- **`359,5599` is read as a decimal, not as 3,595,599.** Four or more digits
  after a comma cannot be a thousands group, and treating it as one inflated a
  per-share value by four orders of magnitude.

- **XBRL concepts keep their meaning.** `dataflows/vendors/concept_resolution.py`
  classifies revenue tags as consolidated, contract, segment or component, and
  `sec_edgar._as_of_with_provenance` records the concept, accession, form, period,
  unit and dimensions with each figure. Candidate tags are ordered by **meaning
  before spelling**, so a filer's consolidated total outranks a component however
  the tags are listed. Asking for consolidated revenue from a filer that reports
  only contract revenue now returns *missing* with the rejected candidate named,
  rather than substituting the subset.
- **Bar finality travels with the price.** `dataflows/vendors/bar_finality.py`
  reports `EOD_CONFIRMED`, `EOD_PENDING_CONFIRMATION`, `INTRADAY_PARTIAL`,
  `STALE` or `UNKNOWN`, with session date, exchange timezone, observation and
  source timestamps, last confirmed close, source and calendar. It uses the
  existing exchange calendar, so holidays and 13:00 closes are honoured. The
  verified market snapshot now states the bar's finality and, when provisional,
  instructs the agent not to quote it as a close or derive an end-of-day signal
  from it.

### Fixed

- Berkshire's Q3 2026 revenue resolved to 74,322 (contract revenue) because the
  tag list put a component before `Revenues`, and the resolver kept the first tag
  that reported a period. The filing states 105,647 as the consolidated total;
  that is what the row now reports, and the YoY growth against 94,972 is 11.24%.
  A component is still identifiable as contract revenue, never renamed as the
  total.
- A daily candle read during the session was presented as a verified close. The
  2026-11-09 reports at 18:37, 19:24 and 21:01 Rome (12:37, 13:24, 15:01 New
  York) all fell inside the session and are now labelled `INTRADAY_PARTIAL`.

- **A metric registry reaches the Execution Gate.** `record_decision` built no
  registry, so the claims validator could verify nothing and every run blocked
  with `NUMERIC_CLAIM_UNVERIFIABLE` — the F6 defect the data lineage audit
  found. `dataflows/math/run_registry.py` now builds a registry per run from the
  engine's own computations and `_evaluate_reliability` supplies it. A run with
  no certified metric blocks with `NO_CERTIFIED_METRIC`.
- **Report generation and execution authorization are separate outcomes.** A
  run whose numbers cannot be certified still produces a report explaining the
  problem (`COMPLETED` / `COMPLETED_WITH_WARNINGS` / `FAILED`) while the order is
  refused (`APPROVED` / `BLOCKED` / `NOT_APPLICABLE`). A `WAIT` is
  `NOT_APPLICABLE`, not a refusal.
- **Build identification in the health endpoint.** `/api/health` reports the
  commit it was built from and the moment the process loaded its modules. A
  process started before a deployment keeps its old code, and start time alone
  could not prove which code was live; the two identifiers together make a stale
  service visible.

### Fixed

- A metric that could not be computed (`NOT_COMPUTABLE`) no longer counts as a
  contradiction. It stays unusable — and a decision resting on no certified
  metric is blocked — but a missing input is a gap to report, not a wrong figure
  to stop on. Treating the two alike is what made every run fail.

- **Deterministic arithmetic validator (P0-B).** New module
  (`tradingagents/dataflows/arithmetic.py`): percentage moves and distances
  from reference levels are computed as
  `(current / reference - 1) * 100`, with intraday open→close and
  close→close kept as distinct metrics. A percentage the report states that
  contradicts the data beyond tolerance is `ARITHMETIC_MISMATCH` and blocks;
  a price and an indicator from different sessions are
  `PRICE_TIMESTAMP_MISMATCH` and block too. The 2026-11-08 report's
  -11.3% / +4.5% / +12.1% figures are rejected against the correct
  -2.63% / +14.70% / +23.03%. Wired into `evaluate_decision` via
  `price_snapshot` + `stated_percentages`, with the verdicts recorded in
  the audit's `data_quality.arithmetic` section.
- **Multi-tranche risk engine (P0-C).** New
  `risk_engine.tranche_risk` prices each leg on its own entry and stop
  (a leg entered lower never inherits the first leg's risk), flags a stop
  tighter than the policy minimum (`STOP_TOO_TIGHT_FOR_POLICY`) and a
  wrong-side stop (`INVALID_STOP_SIDE`). New
  `risk_engine.aggregate_tranche_risk` sizes every leg and enforces the
  aggregate risk and notional budgets *including* open positions and open
  orders; a budget-exhausted alternative leg is skipped rather than
  failing the plan.
- **Structured execution verdict (P0-D).** New module
  (`tradingagents/dataflows/execution_verdict.py`): every run produces a
  machine-readable verdict (`run_id`, `instrument`, `analysis_as_of`,
  `strategic_rating`, `execution_action`, `execution_approved`,
  `authorized_orders`, `blocking_reasons`, `checked_at`,
  `policy_version`). The constructor refuses contradictions — an
  order-bearing action cannot carry blocking reasons, and a blocked or
  waiting verdict cannot carry orders — so no LLM can make an unvalidated
  order look authorized. Written to the audit JSON under
  `execution.verdict`.
- **P0 regression and safety suites.** `tests/test_p0_final_hardening.py`
  (FRESH_01–06, ARITH_01–06, RISK_01–08, EXEC_01–09 plus a four-ticker
  parameterised run) and `tests/test_p0_paper_safety.py` (a mock paper
  broker records zero orders whenever any critical check fails, and one
  order only when every gate passes).

### Changed

- **CI gains a P0 reliability job.** `.github/workflows/ci.yml` runs the
  offline P0 suites (`reliability-regression`) on every pull request; a
  regression there fails the build. The suites need no network, no LLM, no
  SEC credentials and no broker.
- **The data-quality checks run before synthesis, not only at the gate.**
  New `tradingagents/graph/data_quality_node.py` and
  `tradingagents/dataflows/data_gate.py` place the freshness and arithmetic
  verdicts between the analysts and the research debate, so the Research
  Manager and Portfolio Manager are told which figures the data does not
  support instead of debating them as verified. The findings are carried in
  the state as a binding notice; the Execution Gate **reuses** the same
  verdicts rather than recomputing, so what the agents were told and what
  the gate decides cannot diverge. A provider failure yields no filings,
  which the check reports as unavailable — never a silent pass.

- **SEC filing freshness gate (P0.1).** New deterministic module
  (`tradingagents/dataflows/filing_freshness.py`): identifies the most
  recent authoritative filing (company release or SEC filing, with
  `filing_date`, `accepted_at`, `period_end`, `form_type`,
  `accession_number`, source and retrieval timestamp) known at the
  analysis date, and compares it against the period the fundamentals
  analyst actually used. A vendor serving Q2 while the Q3 filing is
  already public yields `STALE_FUNDAMENTALS`; no known filing or an
  undatable report yields `FUNDAMENTALS_UNAVAILABLE` — both block the
  decision's execution vocabulary. No look-ahead: a filing dated after
  the analysis date is invisible, keeping backtests honest. The gate runs
  automatically in `record_decision` (point-in-time extraction from SEC
  EDGAR; the used period is read from the run's own fundamentals report)
  and can be disabled with `fundamentals_freshness_gate: false`.
- **Shared financial fact registry (P0.2).** New deterministic module
  (`tradingagents/dataflows/fact_registry.py`): every agent's material
  financial facts are registered with full scope (metric, value, unit,
  currency, period, segment, definition, source). Same-scope values are
  compared; scope differences (Q2 vs Q3, GAAP vs operating) are never
  conflated into conflicts. Units are normalized to a common base before
  comparison — 9.6 USD_billion and 9,600 USD_million are the same fact
  stated differently, and a unit difference alone is recorded as
  `UNIT_MISMATCH` context on the conflict, never silently ignored. An
  absence never refutes a sourced value. A consensus/estimate EPS
  compared against an actual of another definition is
  `METRIC_DEFINITION_MISMATCH` — no certified "beat". Conflicts resolve
  only via a verified primary source; unresolved ones block. Diagnostic
  codes: `FACT_CONFLICT`, `FACT_CONFLICT_UNRESOLVED`, `PERIOD_MISMATCH`,
  `UNIT_MISMATCH`, `METRIC_DEFINITION_MISMATCH`,
  `UNVERIFIED_FINANCIAL_METRIC`, `PRIMARY_SOURCE_WINS`. The registry
  populates automatically from the run's own reports via
  `dataflows/claim_harvester.py` (labelled metric patterns only, bare
  numbers never guessed; harvested facts are unverified by construction —
  harvesting proves what an agent asserted, not that it is true).
- **Valuation reconciliation (P0.3).** New module
  (`tradingagents/dataflows/valuation.py`): book value per share, market
  cap and P/B computed only after currency and share-class consistency
  pass; a cross-class book value without a conversion ratio is refused,
  never silently converted.
- **Exposure-capped position sizing (P0.5).** New
  `risk_engine.size_with_exposure_cap`: sizing applies the stop-distance
  budget AND the per-symbol notional cap simultaneously and reports which
  bound. The 100k/1%/560/552.07 scenario yields 8 shares (4,480 USD)
  under a 5% cap instead of ~126 shares (~70,600 USD) from the
  stop-distance alone. Missing portfolio context never invents a size
  (`PORTFOLIO_CONTEXT_MISSING`); wrong-side stops block per direction
  (`risk_engine.validate_stop_side`). The sizing runs automatically in
  the real flow: the plan's numbers (entry/stop/ATR/direction) are
  extracted from the Trader's own plan text by
  `dataflows/plan_extraction.py` — labelled patterns only, bare numbers
  in prose never guessed — and the audit's `risk` section records the
  capped quantity, notional and which constraint bound.
- **Final order reconciliation (P0.6).** New module
  (`tradingagents/dataflows/order_reconciliation.py`): the Portfolio
  Manager's decision prevails over the Trader's earlier proposal; any
  revision to quantity/entry/stop/side voids prior authorizations and
  requires full revalidation; a HOLD decision reconciles to a
  zero-quantity, unauthorized candidate — a HOLD never becomes a BUY or
  SELL.
- **P0 gates wired into the decision point.**
  `gate_integration.evaluate_decision` accepts the freshness inputs, a
  fact registry report and the position direction; stale fundamentals, an
  unresolved material conflict or a wrong-side stop each BLOCK with
  stable reason codes, and the audit JSON carries the verdicts under
  `data_quality`.

- **Download button for the markdown report.** The web console's run and
  archive panels gain a **⤓ Download markdown** button that saves the
  consolidated markdown report as a file (`<TICKER>_<DATE>_report.md`)
  instead of opening it in a browser tab: the markdown endpoints
  (`/api/runs/{id}/report.md`, `/api/archive/{id}/report.md`) accept
  `?download=1` and serve a `Content-Disposition: attachment` header with
  the report's filename. The existing "Open HTML report" and "Markdown"
  links are unchanged (inline by default), so both opening and saving the
  report remain available.

- **Instrument Profiler.** A vendor-data-driven instrument classifier
  (`tradingagents/dataflows/instrument_profiler.py`) so the reliability
  layers behave uniformly for any instrument — US mega-caps, dual-class
  shares, Milan-listed utilities, London minor-unit quotes, crypto pairs,
  indices and forex — with no per-ticker tables. It derives the instrument
  kind from the vendor's `quoteType` (with structural fallbacks: `=X`
  forex, `^` index, known crypto bases), the quote and financial
  currencies (`currency` / `financialCurrency`, with a conversion factor
  for minor-unit quotes like GBp→GBP), and the share class structurally
  from the ticker's explicit suffix (`BRK-B` → root `BRK`, class `B`;
  `NVDA` is never read as `NVD` class `A`). A data-quality label
  (`COMPLETE`/`PARTIAL`/`UNKNOWN`) is the caller's fail-closed signal.

### Changed

- **Ticker-identity and currency checks are profile-driven.**
  `validator.check_ticker_identity` accepts an `InstrumentProfile`: a
  sibling-class symbol served by the vendor (asked BRK-B, served BRK-A) is
  an error via structural detection instead of a hardcoded sibling table;
  without a profile, a bare string mismatch stays a normalization warning.
  New `validator.validate_currency_consistency` checks a price's currency
  against a metric's: a minor-unit quote (GBp) against main-unit
  financials (GBP) passes with the profiler's conversion factor, a real
  mismatch (USD price vs EUR financials on ENI.MI) is an error, and
  unknown currencies are `UNVERIFIED` rather than errors.

### Added

- **Execution Gate wired into the run flow.** Every finished run is now
  evaluated through the Execution Gate and audited
  (`tradingagents/dataflows/gate_integration.py`, called from
  `TradingAgentsGraph.record_decision`): the gate's verdict is attached to
  the run state (`execution_action`, `execution_reason_codes`) and the
  audit JSON is written beside the state log under
  `results_dir/<ticker>/reliability_audit/`. The decision itself is still
  recorded and reported exactly as before — the gate governs the execution
  vocabulary, not reporting — and a reliability-layer failure is logged
  and skipped rather than losing the run's reports or memory entry. An
  unreadable rating blocks rather than being guessed (#1170); plan numbers
  absent from the decision skip the risk check instead of being invented.

### Added

- **Walk-forward validation (Phase 7).** A pure fold-and-score module
  (`tradingagents/dataflows/walk_forward.py`) for historical out-of-sample
  validation without look-ahead: folds cut a historical range so each
  train window ends strictly before its test window, and the memory log's
  `as_of` guard (lessons resolved by `train_end`) is the enforcement point
  for what a test-window decision may learn from. Scoring is honest by
  construction: pending cells are counted and excluded from averages,
  never folded in as zero; a rating with fewer than 5 settled samples is
  labelled `insufficient` instead of reporting a noisy hit rate; `Hold`
  claims no direction so nothing about alpha proves it right or wrong;
  alpha is measured from the first close *after* each analysis date over a
  declared holding window against a declared benchmark, and the summary
  states that basis with the caveat that one model sampling per cell is
  indicative rather than repeatable.

### Added

- **Structured audit trail (Phase 6).** An audit record
  (`tradingagents/dataflows/audit.py`) assembles the earlier phases' typed
  verdicts — provenance, causal guard, stop validation, sizing, portfolio
  risk, execution gate, strategic decision, fact check — into the
  contract's machine-readable schema (`schema_version` 1.0), produced
  alongside the human report. Fields the run did not produce stay `None`,
  never invented; the run id is derived deterministically from ticker,
  analysis date and snapshot id so re-auditing is idempotent; model and
  provider names are recorded, key material never is. A few-second human
  summary separates the opinion (`OVERWEIGHT`) from the execution action
  (`WAIT`/`BLOCK`) and names the blocking refuted claims, so a reader can
  tell an opinion from a plan from an order at a glance.

### Added

- **Independent Fact Checker and bounded debate (Phase 5).** A claim-level
  checker (`tradingagents/dataflows/fact_checker.py`) classifies every
  material claim (`FACT`, `DERIVED_CALCULATION`, `CAUSAL_INFERENCE`,
  `HYPOTHESIS`, `FORECAST`, `UNSUPPORTED`) and checks it against the run's
  verified facts: a causal claim like "the market has already absorbed the
  Q3" is refuted with `EVENT_AFTER_LAST_MARKET_SESSION` when no post-event
  session exists; a fact presented without supporting fact ids is refuted;
  support resting on unverified or quarantined facts downgrades the claim.
  A refuted *blocking* claim stops the decision. A debate controller
  (`tradingagents/dataflows/debate.py`) ends rounds that add no new
  evidence, no verifiable rebuttal and no concrete plan change (the
  repeating-the-opening-claim failure), keeps the round cap configurable,
  and separates rating disagreement (opinions may differ) from trigger
  disagreement (must resolve or the decision blocks). A refuted claim is
  checkably barred from returning as fact.

### Added

- **Separated portfolio decision (Phase 4).** A typed decision model
  (`tradingagents/dataflows/portfolio_decision.py`) keeps the contract's
  three levels distinct: strategic rating (`UNDERWEIGHT/NEUTRAL/OVERWEIGHT`
  over a declared horizon), investment intent
  (`AVOID/MONITOR/ACCUMULATE_CONDITIONALLY/MAINTAIN/REDUCE`), and execution
  action (`WAIT/BLOCK/PROPOSE_PAPER_ORDER/SUBMIT_PAPER_ORDER`, filled only
  by the Execution Gate). Legacy 5-tier labels (`Buy`/`Hold`/…) map
  explicitly with the original label preserved on the decision — `Buy`
  becomes `OVERWEIGHT` + `ACCUMULATE_CONDITIONALLY`, never a market order —
  and unknown labels are refused for review rather than guessed. An
  `OVERWEIGHT` rating now visibly coexists with a `WAIT` action in the
  rendered decision, ending the report practice of treating `HOLD`, `BUY`
  and `Overweight` as equivalent actions.

### Added

- **Execution Gate (Phase 3).** A deterministic gate
  (`tradingagents/dataflows/execution_gate.py`) sits between a proposed plan
  and any paper order. It consumes only the typed verdicts of the earlier
  phases — never LLM prose — and emits `WAIT` (no trigger yet),
  `BLOCK` (invalid plan or missing mandatory data) or
  `PROPOSE_PAPER_ORDER`. `WAIT` and `BLOCK` create zero orders, pending
  conditional ones included. A strategic `OVERWEIGHT` rating with an
  unmet entry trigger now ends in `WAIT` with explicit reason codes
  (`ENTRY_TRIGGER_NOT_MET`, `POST_EARNINGS_REACTION_UNOBSERVABLE`,
  `MARKET_CLOSED`); the same plan with the trigger met while the post-event
  reaction is still unobservable hard-`BLOCK`s. Submission is a separate,
  revalidated, idempotent step: a stale signal or a non-proposal decision
  is refused, and a retry with the same plan key returns the original
  order (`DUPLICATE_ORDER`) instead of creating a second one.

### Added

- **Deterministic risk engine (Phase 2).** A pure, typed risk engine
  (`tradingagents/dataflows/risk_engine.py`) computes position sizing, stop
  validation and gap/slippage stress in code, never in LLM prose. Stop
  validation requires an entry-to-stop buffer of at least 0.5 ATR
  (parametric): the BRK-B plan of 543.70/543.50 with ATR 9.408 (~0.021 ATR)
  now fails deterministically with `STOP_BUFFER_TOO_TIGHT`. Sizing uses the
  *stressed* exit price — stop less a gap allowance and slippage — so
  `qty = floor(risk_budget / stressed_risk_per_share)`; a missing budget
  yields zero size (`RISK_BUDGET_MISSING`), never a guess. Portfolio-level
  checks keep `max_portfolio_loss_fraction` as `None` when equity is
  unknown: a loss quoted against a standard allocation is never converted
  to a fraction of total wealth without the real base.

### Added

- **Data validation layer (Phase 1).** A provenance registry
  (`tradingagents/dataflows/provenance.py`) records where each material fact
  came from, its publication and retrieval times, and its verification
  status: facts without a verified publication time are `UNVERIFIED` and
  cannot feed a decision; contested ones are `QUARANTINED`. An event-to-price
  causal guard (`tradingagents/dataflows/causal_guard.py`) answers
  deterministically whether post-event prices exist — `NOT_YET_OBSERVABLE`,
  `OBSERVABLE` or `INSUFFICIENT_DATA` — so a claim like "the stock absorbed
  the earnings" is checkable against the market calendar instead of asserted.
  A deterministic validator (`tradingagents/dataflows/validator.py`) checks
  OHLC consistency, reconciles vendor metrics across units with a
  materiality threshold, and blocks cross-share-class comparisons (e.g. a
  BRK-B price against BRK-A book value) until converted. The news analyst
  gains a `check_event_pricing` tool and is instructed to call it before
  attributing any price move to a published event.

### Added

- **Reliability baseline (Phase 0).** Frozen BRK-B regression fixture for the
  2026-11-08 report case (`tests/fixtures/brk_b_2026_11_08.py`) and a
  deterministic regression suite (`tests/test_reliability_baseline.py`, 14
  tests) pinning the temporal facts the reliability contract requires: the Q3
  release postdates the last completed session, no post-event price exists at
  report time, the Friday close-to-close move is ~-0.25% (not -0.01%), the
  543.70/543.50 tranche-stop plan sits at ~0.021 ATR (far below the 0.5 ATR
  minimum buffer), and strategic ratings share no vocabulary with execution
  actions. A safety audit test verifies the codebase holds no broker SDK or
  order-submission symbol and that the shared HTTP helper is read-only
  (GET/HEAD only).

- The web console runs backtests: a **Backtest** tab drives the CLI's `backtest`
  command over a grid of tickers and dates, shows each cell as it runs and the
  per-rating score once settled. One sweep at a time, into its own memory log
  under `results_dir/backtest/`, so the live log real runs read back stays clean.
- The web console shows the decision log: a **Decision log** tab lists every
  recorded decision with its outcome and reflection, and **Settle pending**
  runs the same settlement pass a run performs at its start, so decisions whose
  holding window has traded get their outcome without waiting for the next run.
- The web console keeps several analyses side by side: the History tab lists
  every run this process has started, and picking one shows it while the others
  keep going, instead of one run replacing the next.
- The web console's report panel draws the ticker's daily closes around the
  analysis date as a small chart, fetched through the same point-in-time vendor
  path the agents use, so a historical run never sees a later bar.
- The web console's archive gains **Re-run**, which pre-fills the form from the
  open report's header (ticker, date, analysts, depth, models), and
  **Compare**, which reads two reports of the same ticker side by side, agent
  by agent.
- The web console remembers the form's answers in the browser, so a reload
  keeps the provider, models, depth and language that were chosen.
- The web console's report panel renders the agents' markdown as formatted text
  — headings, tables, lists, quotes and code — instead of showing it raw. The
  rendering reuses the safe `markdown-it` configuration of the saved HTML report
  (raw HTML escaped, images off), so nothing a model wrote can inject markup.
- Italian is offered in the output-language menu, in the CLI and the web console
  alike. Both now read one shared list (`cli.prompts.OUTPUT_LANGUAGES`), so a
  language added there appears in both and they cannot drift apart.
- A local web console (`python -m webapp`, or `pip install ".[web]"` and
  `tradingagents-web`) offering the CLI's analysis in a browser: the same
  ticker, date, analyst, depth, language, provider and model choices, a live
  agent/message view, and the same saved reports. It imports the CLI's checks,
  live state and report writer without changing them, binds to loopback only,
  and reuses the same `results_dir` artifacts a CLI run produces.

### Added

- **Mathematical tools for the analysts.** Eighteen typed tools
  (`tradingagents/agents/math_tools.py`) let an agent *ask for* a number
  instead of computing one: percentage changes, CAGR, P/B, book value per
  share, P/E and earnings yield, EPS on weighted-average shares, technical
  indicators, price distances, stop distances, ATR-implied stops, risk/reward,
  unit conversion, and validators for stated multiples, stated percentages,
  market bars, market series and trade proposals. Each returns structured
  JSON with `value`, `formula_id`, `operands` and a calculation status, never
  a bare number a model could restate. The market analyst receives the
  measurement tools and the fundamentals analyst the valuation tools, so a
  distance from a moving average or a price-to-book is certified rather than
  estimated in prose.
- **Market session status.** `tradingagents/dataflows/math/session.py`
  distinguishes a final end-of-day close from a bar that is still forming, and
  reports `market_session_status`, `bar_timestamp`, `is_complete`, `is_final`
  and `last_completed_session`. A date-only bar is judged as its whole session
  rather than as midnight, so a past daily bar is complete while the running
  session's is not. `assess_series` reports `includes_partial_bar` so an
  indicator can declare that it was computed over a price still moving.
- **Certified metric lookup.** `get_certified_metric` reads a value from the
  run's registry, and answers `UNSUPPORTED` for a metric the engine never
  computed — so a report cannot quote a number nobody verified.
- **Metric definition reconciliation.** `tradingagents/dataflows/math/definitions.py`
  decides whether two figures may be combined, refusing a segment total
  against a consolidated one, GAAP against adjusted, a quarter against a TTM
  figure, differing currencies or unit scales, and a per-share figure built on
  end-of-period instead of weighted-average shares. This is the one check
  arithmetic cannot provide: dividing 105,647 by 74,322 is flawless and
  meaningless, so the block must come from comparing what the figures mean.
  Differing *quarters* remain compatible — a year-over-year comparison is the
  purpose of having period labels; a quarter against a trailing year is not.
- **Analyst report validation.** `dataflows/math/report_validation.py` reads
  each analyst's finished report, extracts the figures that carry a label and
  checks them against the run's certified metrics, so the constraint on agent
  arithmetic lives in code rather than in a prompt asking the model not to
  calculate. A figure the engine computed and the report got wrong blocks the
  decision. A figure with no certified counterpart does not block by itself
  and is reported as `is_validated: false`: before any metric is registered
  every labelled number would be unverifiable, and blocking on those would
  fail every run including the valid path.

### Fixed

- A LONG stop above its entry, or a SHORT stop below it, is refused rather than
  measured: the distance from such a pair looks plausible while the plan
  protects nothing.
- `check_claim` compared a `Decimal` against a claimed `float`, raising
  `TypeError` whenever a claim was built from a tool argument rather than
  parsed from prose. Both sides are converted once, so the comparison is
  always exact.

### Added

- **Financial Math Engine.** A dedicated package (`tradingagents/dataflows/math/`)
  that owns every financial calculation the application performs, so no
  quantity, multiple, percentage or risk figure is produced by a language
  model. Monetary math uses `Decimal` with explicit rounding and carried
  units; each derived metric is a record with its formula, operands, period
  and a verified/refused status, so the audit can reproduce it. Refusals are
  kept rather than dropped, letting a report show the rejected figure next to
  the computed one. Covers arithmetic and unit conversion, valuation metrics
  (market cap, EPS GAAP/adjusted, P/E trailing/forward, P/B, D/E, ROE, ROA,
  dual-class book value), technical indicators (SMA, EMA, VWMA, ATR, RSI,
  MACD, Bollinger/%B), numeric-claim validation and cross-report consistency
  checking. See `docs/financial-math-engine.md`.
- **Mathematical execution gate.** A contradicted or unverifiable figure now
  blocks a paper order with the specific hazard named
  (`INVALID_PRICE_TO_BOOK`, `INVALID_STOP_ATR_DISTANCE`,
  `NUMERIC_CLAIM_CONTRADICTED`, `NUMERIC_CLAIM_UNVERIFIABLE`), and these
  reasons cannot be downgraded to a WAIT: a wrong number does not become
  right later. Verified by an end-to-end test in which reports carrying the
  2026-11-08 figures (P/B 1.35x, "2.5 ATR" stop, -11.3% from the high) send
  **zero** orders to a mock paper broker, while the same plan with sound
  arithmetic sends exactly one.

### Fixed

- A price-to-book a report states is checked against price and book value
  instead of being trusted: 570.89 / 385.70 = 1.4801, so the reported 1.35x
  is now refused and both figures are recorded in the audit.
- A stop's stated ATR distance is checked against its own entry, stop and
  ATR: entry 557.00, stop 547.40 and ATR 9.408 give 1.02 ATR, so a reported
  2.5 ATR is refused. Wrong-side stops are reported as contradictions for
  both directions.
- A valuation built on a stale accounting period (Q2 book value applied to a
  Q3 analysis) is refused rather than presented as current.
- Percentages an agent states are compared against the engine's own
  computation, and a disagreement is recorded as a refused claim rather than
  silently corrected.
- The test and lint CI jobs pass again, so they can gate merges. The test job
  installed only the `dev` extra while two suites import `fastapi`, which
  lives in `web`: collection aborted on every Python version before running a
  single test. The lint job reported 27 findings that pre-date this work —
  mechanical ones (unused imports, import ordering, a missing trailing
  newline) plus an unused local, an ambiguous `l` renamed to `low`, three
  `try/except/pass` blocks written with `contextlib.suppress`, and two
  `dict()` calls written as literals. Behaviour is unchanged.
- A push to `custom`, the integration branch, now runs CI. Previously only
  `main` and version tags were covered, so a merge into `custom` landed
  unvalidated.

### Added

- **Trade actions, separate from ratings.** `dataflows/math/trade_actions.py`
  introduces OPEN_LONG, REDUCE_LONG, CLOSE_LONG, OPEN_SHORT, REDUCE_SHORT,
  CLOSE_SHORT and WAIT, and the rules that make each checkable. A strategic
  rating permits candidate actions but never implies one: a bare SELL or BUY
  names a direction, not a book operation, so it maps to no action — which is
  what stops a SELL becoming an OPEN_SHORT. A reduction applies its fraction
  to the held quantity, so 40% of 10 shares is 4 and never 40% of an unknown
  base; a reduction on a flat book or with an unknown portfolio blocks rather
  than yielding a zero that looks like a decision.
- **Code-generated technical audit section.** The audit JSON now carries a
  `technical_audit` block listing the last confirmed EOD bar, the intraday bar
  status, the fundamentals period used and its reconciliation, the count of
  mathematical findings, the invalidated metrics, the numeric claims checked
  and blocking, the risk verdict, the execution action and the blocking
  reasons. Every field derives from a verdict the run produced; a missing one
  stays null rather than being reported as passed.

### Fixed

- A percentage claim can now say which denominator it used. Measuring a price
  against a level and a level against a price give +4.87% and -4.64% for the
  same two numbers, because a percentage change is not symmetric; the engine
  previously had one convention, so it would have rejected the correct
  Bollinger figure. `distance_from_level` and `level_distance_from_price` are
  now distinct, and the tool takes the denominator as an argument.
- Bollinger bands expose two widths under different names with their
  denominators stated: `bandwidth_pct` against the middle (12.31% on the
  19:24 figures) and `width_over_price_pct` against the price (11.73%).
- The numeric claim extractor recognizes EPS and VIX change phrasings
  ("EPS contracts 37%", "VIX rose 58%"). Before this, such a claim produced
  nothing, so a mismatch could not have been caught.
- `NUMERIC_CLAIM_MISMATCH` is a distinct gate reason for a claimed rate the
  engine disproves, and the finding records the claiming agent alongside the
  stated and computed values.

## [0.7.1] — 2026-10-27

Decisions are scored only on final closes and settle across long market holidays, a model's unpadded date no longer reads filings made after the run date, and fixes to portfolios, prices, SEC statements, reports, Azure and Claude settings.

### Upgrading from 0.7.0

- Docker images no longer include `.env.enterprise`. For Azure OpenAI in Docker, put its keys in `.env`.

### Fixed

- A date a model passes without zero padding, such as `2024-7-5`, is read as that date. It could compare as later than a filing made after the run date, and SEC EDGAR then served that filing. (#1488)
- A decision is no longer scored on the bar of a session still trading, and one made before a market closure longer than a week, such as a national holiday, settles once trading resumes instead of staying pending. (#1548, #1539)
- A backtest reports the failures of its last settlement pass, and two started in the same second no longer share one run. (#1557, #1549)
- A holding listed under a broker's spelling (`BTCUSDT`, `700.HK`) is matched to the instrument analyzed, and a portfolio number that is not finite is refused when the file loads. (#1556, #1509)
- Prices keep their significant digits: a sub-cent close no longer prints as 0.00, and a currency pair keeps its pips. (#1567)
- SEC EDGAR statements list one row per period, so a model no longer reads a figure against the wrong quarter across a long history, and a figure under one million no longer prints as 0. (#1517, #1589)
- Saving a report to a folder used before removes the earlier run's sections. (#1566)
- A date window that ends before it starts is sent back to the model instead of returning no data. (#1595)
- A statement frequency other than annual or quarterly is sent back to the model instead of being served annual figures under that word. (#1593)
- The memory's most recent lessons, and the entries rotation keeps, follow decision dates, so a backfill of older dates no longer displaces them. (#1603)
- Prediction-market odds near 0% or 100% show their distance from it to two significant digits. (#1598)
- Azure OpenAI receives `max_tokens` and a configured endpoint. (#1584, #1600)
- Claude's effort setting is decided correctly for dated model IDs such as `claude-sonnet-4-20250514`. (#1585)
- The CLI checks a ticker with the same rule as the run, so `XAUUSD+` is accepted and `..` is refused at the prompt. (#1604)
- Docker images no longer include `.env` files from any folder.
- Tests that failed on Windows and macOS for platform reasons are fixed. (#1506, #1485, #1541)

### Contributors

[@alanfate3](https://github.com/alanfate3), [@aranlucas](https://github.com/aranlucas), [@BichengWang](https://github.com/BichengWang), [@Bortlesboat](https://github.com/Bortlesboat), [@hoffman988](https://github.com/hoffman988), [@jhill-cmd](https://github.com/jhill-cmd), [@muhib-karim](https://github.com/muhib-karim), [@pei711](https://github.com/pei711), [@peiji1981](https://github.com/peiji1981), [@rudycelekli](https://github.com/rudycelekli), [@Shubham-Padkonde](https://github.com/Shubham-Padkonde), [@stevexyz2003](https://github.com/stevexyz2003), [@SuperMarioYL](https://github.com/SuperMarioYL), [@sytfly](https://github.com/sytfly), [@yuv009](https://github.com/yuv009).

## [0.7.0] — 2026-10-16

Runs on your ChatGPT plan, backtests scored from the first close after each decision, a note at start-up when a newer release is out, and a wheel attached to each GitHub release.

### Added

- **Your ChatGPT plan.** The `chatgpt` provider runs TradingAgents on a ChatGPT Plus or Pro plan instead of an API key, through OpenAI's sign-in for open-source apps. Choose "Subscription" in the CLI's provider menu; for unattended runs, Docker and Python (`llm_provider="chatgpt"`), sign in once with `tradingagents login chatgpt`. `tradingagents logout chatgpt` revokes the sign-in. The CLI lists the plan's models, and reasoning effort applies as it does for OpenAI. (#1194, #1475)
- **What's new at start-up.** The interactive CLI mentions a newer release, with the command that upgrades this install when it can tell how TradingAgents was installed, and notices from Tauric Research for the running version. It checks at most once a day in the background, so a run never waits on it; runs without a terminal never check, and `TRADINGAGENTS_NO_UPDATE_CHECK=1` turns it off.
- **Release downloads.** Each GitHub release carries the source archive and a wheel, so a version installs with `pip install` from its release page without cloning.

### Upgrading from 0.6.0

- `cryptography` 42 and `packaging` 24 or later are installed.
- Decisions are now scored from the first close after their date. Outcomes already settled in a memory log keep the earlier entry, the close of the decision date, so a backtest resumed with `run_id` mixes the two; start a new run to compare like with like.

### Fixed

- A decision is no longer scored against news it could not have traded on: a run dated *d* reads news published after the close on *d*, so the memory log and backtests enter it at the first close after *d*, not the close of *d*. (#1518)
- A run without a terminal, such as a scheduled job or CI, no longer contacts the announcements server before it starts.
- A model tier on another provider keeps its configured reasoning effort, thinking level or Claude effort when the main provider has none. (#1440)

### Contributors

[@LeonWTW](https://github.com/LeonWTW), [@OleksanderSS](https://github.com/OleksanderSS), [@sovorn-c](https://github.com/sovorn-c).

## [0.6.0] — 2026-10-03

HTML reports, a provider per model tier, past decisions settled for every ticker while the analysts work, and company news read while Yahoo's news feed is down.

### Added

- **HTML report.** A saved report also includes `complete_report.html`, the report as one page with its sections listed beside the text, that reads well in a browser, on a phone and in print. Answering the save question at the prompt also asks about the page and can open it in your browser; `--no-html` or `save_reports(..., html=False)` skips it. The page is self-contained: it loads nothing and runs nothing. (#1419)
- **A provider per model tier.** The quick and deep models can run on different providers, for example the managers on Claude while the analysts run on OpenAI: set `deep_think_provider` or `quick_think_provider` (`TRADINGAGENTS_DEEP_THINK_PROVIDER`, `TRADINGAGENTS_QUICK_THINK_PROVIDER`) with the tier's model. The report header names each tier's provider. (#1440)
- **Past decisions settle alongside the analysts.** While a run's analysts work, every logged decision whose holding period has passed is settled, for any ticker, not only the one being analyzed. If settling fails, the run goes on and the report header says so. (#1428, #1445)
- **Crypto on Reddit.** For a crypto ticker the Sentiment Analyst reads r/CryptoCurrency and r/CryptoMarkets, plus r/Bitcoin, r/ethereum or r/solana for those coins, instead of the stock subreddits. (#1461)
- `settle_all_pending()` settles every due decision without running an analysis, for a scheduled job; it and `settle_pending()` return the decisions settled and any that could not be. (#1445)
- The report header names the run's rating.
- Euro-area macro series by name: `ecb_deposit_rate`, `ecb_main_refi_rate`, `euro_hicp`, `euro_core_hicp`, `euro_real_gdp`, `germany_10y`, `france_10y` and `eur_usd`. (#1465)

### Models

- A Gemini call times out after 600 seconds, as OpenAI and Anthropic calls do, so a stalled call no longer hangs the run. (#1417)

### Upgrading from 0.5.2

- markdown-it-py 4.0 or later is installed.
- A saved report also writes `complete_report.html`; pass `--no-html`, or `html=False` to `save_reports()`, to keep only the Markdown.
- A run no longer settles its ticker's decisions before it starts; the Memory Log step settles every ticker's during the run.
- `settle_pending()` returns a `Settlement` with `settled` and `failed` (was `None`).
- Checkpoints from 0.5.2 are not resumed.

### Fixed

- Company news is read from Yahoo search while Yahoo's news feed returns nothing. When Yahoo has no article about the symbol, its news is reported unavailable, not absent, and a configured next news vendor is tried. (#1467, #1469)
- A rating quoted from someone else, such as "Consensus rating: Buy", no longer replaces the Portfolio Manager's own. (#1466)
- A Yahoo news article with a null field no longer loses the ticker's news. (#1458)
- A start date a model writes with stray characters is sent back to it to correct, instead of failing the news or price request. (#1476)
- A request Alpha Vantage rejects is reported as unavailable, not served as data; the API key is kept out of every Alpha Vantage error. (#1442)
- Yahoo fundamentals print each money figure in its own currency: London prices in GBp, market cap and per-share figures in GBP, and an ADR's income figures in its reporting currency, such as TWD for TSMC. (#1456)
- Jev screening uses the endpoint `TYPESAFE_BASE_URL` names, so it can run through OpenRouter. (#1416)
- Runs sharing a memory log settle each decision once, and an interrupted settlement keeps the outcomes it finished.
- The report header names the sentiment analyst `sentiment`, as the CLI does.
- `requirements.txt` says the dependencies are declared in `pyproject.toml`.

### Contributors

[@amitbhansali](https://github.com/amitbhansali), [@AyushJain-601](https://github.com/AyushJain-601), [@BichengWang](https://github.com/BichengWang), [@byte7m](https://github.com/byte7m), [@Dangerboi](https://github.com/Dangerboi), [@davidalmeida90](https://github.com/davidalmeida90), [@Jackzigen](https://github.com/Jackzigen), [@jhill-cmd](https://github.com/jhill-cmd), [@Recnelis0](https://github.com/Recnelis0), [@seaaxe](https://github.com/seaaxe), [@vaegev](https://github.com/vaegev).

## [0.5.2] — 2026-09-29

Parallel analysts, unattended CLI runs, reports that record what produced them,
and past runs served only what was known on their date.

### Added

- **Parallel analysts.** The selected analysts run at the same time, so the analyst phase takes about as long as the slowest one; the CLI shows each analyst's progress and time as it finishes, and the debate starts when all reports are in. (#1255, #433)
- **Unattended CLI runs.** Flags answer the per-run questions, and `TRADINGAGENTS_*` variables the rest, so a scheduled job or script asks nothing: `tradingagents --ticker NVDA --date 2026-09-26 --analysts market,news --save --no-show`. Without a terminal, a missing answer stops the run before it starts and names what to set. (#1127, #1133)
- **Reports record what produced them.** Each report opens with the analysis date, version, provider, models, analysts, rounds and data vendors; the state log keeps them as `run_settings`. (#752, #1197)
- **Docker data folder.** `TRADINGAGENTS_DATA_DIR` keeps results, reports and the memory log in a host folder. (#865)
- **A cap on an analyst's tool calls.** After `max_tool_rounds` rounds (default 20, `TRADINGAGENTS_MAX_TOOL_ROUNDS`) the analyst writes its report from what it has. (#1420)
- `tradingagents backtest` shows each cell as it starts and the `--run-id` to continue; `--analysts` accepts `sentiment`.
- Benchmarks for Taiwan, Korea, Singapore and the main European exchanges. (#1392)
- Python 3.14 support; the Docker image runs Python 3.13.

### Models

- `deepseek-flash` is treated as a thinking model, so structured output works. (#1388)

### Upgrading from 0.5.1

- Python 3.11 or later is required; pandas 3 is installed.
- Minimum versions: yfinance 1.7.0, langchain-core 1.6.5, langchain-openai 1.6.6, langchain-anthropic 1.7.4, langchain-google-genai 4.4.0, langgraph 1.2.12, langgraph-checkpoint-sqlite 3.1.1, langchain-aws 1.7.9 (`bedrock` extra).
- Statements default to SEC EDGAR, then Yahoo (`fundamental_data = "sec_edgar,yfinance"`).
- A past-dated run gets no Yahoo or Alpha Vantage statements or insider trades, which carry no filing date, and only the company's current name, marked as such.
- The memory log is the `tradingagents.memory` package (was `tradingagents.decision_log`); settlement and reflection moved there from `tradingagents.graph`, and `Reflector` is no longer exported from `tradingagents.graph`.
- `process_signal` is removed; the rating is `propagate()`'s second value or `final_state["final_rating"]`.
- A rating is read only from its `Rating:` label; a free-text decision without one is `REVIEW`.
- Data-layer functions take `as_of_date=` (was `curr_date=`); `build_instrument_context` and `resolve_instrument_context` take `trade_date=`.
- `VendorRateLimitError` is `VendorUnavailableError`.
- Data tools take the instrument from the run's state; tool calls no longer carry `symbol` or `ticker`.
- State log: `trader_investment_plan` (was `trader_investment_decision`), `judge_decision` removed, `final_rating` and `run_settings` added.
- Checkpoints from 0.5.1, or saved under different settings, are not resumed.

### Fixed

- Data tools serve the run's instrument, even when the model passes another symbol.
- A failed vendor request is reported as unavailable, not as a missing or delisted symbol; one vendor's "no data" no longer speaks for a chain in which another failed. (#1386)
- The rating is the Portfolio Manager's own, not one its thesis quotes (#1383); its line keeps an English label in other output languages (#1435).
- Backtest cells given twice run once (#1415), and settlement compares a decision with its benchmark over the same dates.
- A snapshot for a symbol with no prices no longer ends the run.
- Concurrent runs no longer drop memory log entries.
- SEC EDGAR quarterly figures filed only year to date are served, labelled with their span.
- Yahoo dividend yield and debt-to-equity print as percentages. (#1414)
- The FRED change line names the dates it spans. (#1397)
- `stream_run` serves the graph's own config to its tools.
- The test suite stays off the network and out of the user's files, and passes in any order; integration tests run with `-m integration`. (#1395)

### Contributors

[@1Wizzy](https://github.com/1Wizzy), [@BichengWang](https://github.com/BichengWang), [@Chaoqi31](https://github.com/Chaoqi31), [@davidalmeida90](https://github.com/davidalmeida90), [@djconnexion77](https://github.com/djconnexion77), [@fuzing](https://github.com/fuzing), [@hailampy123](https://github.com/hailampy123), [@hesam-shams](https://github.com/hesam-shams), [@HEYALT](https://github.com/HEYALT), [@Jackzigen](https://github.com/Jackzigen), [@kagura-agent](https://github.com/kagura-agent), [@loulanyue](https://github.com/loulanyue), [@mannubaveja007](https://github.com/mannubaveja007), [@olivergpt](https://github.com/olivergpt), [@rita112025-cpu](https://github.com/rita112025-cpu), [@shuyan-code](https://github.com/shuyan-code), [@SingTheCode](https://github.com/SingTheCode), [@sjq597](https://github.com/sjq597), [@xiaodu55](https://github.com/xiaodu55), [@Youholdme](https://github.com/Youholdme).

## [0.5.1] — 2026-09-24

A package layout organised by what each module holds, social posts screened by
TypeSafe's Jev when a key is set, GPT-6 Sol and Luna as the default models, and
fixes to run isolation, SEC EDGAR statements and historical runs.

### Upgrading from 0.5.0

Some modules moved, and the old import paths are gone. Update imports as follows:

- `tradingagents.dataflows.interface` is `tradingagents.dataflows.router`, and `dataflows.symbol_utils` is `dataflows.symbols`. `dataflows.utils` is gone: `get_current_date` is in `dataflows.date_window`, `safe_ticker_component` in `dataflows.symbols`, and `get_scrubbed` and `vendor_reachable` in `dataflows.net`.
- Vendor modules live under `tradingagents.dataflows.vendors`: `yahoo` (`ohlcv`, `market`, `fundamentals`, `news`, `snapshot`, from the former `stockstats_utils`, `y_finance`, `yfinance_news` and `market_data_validator`), `alpha_vantage` (a package, from the `alpha_vantage_*` modules), and `sec_edgar`, `fred`, `polymarket`, `reddit`, `stocktwits`.
- `tradingagents.agents.utils` is gone: the agent tools are in `agents.tools`, and `agent_utils`, `agent_states`, `rating` and `structured` are `agents.context`, `agents.state`, `agents.rating` and `agents.structured`.
- The decision log is `tradingagents.decision_log` (was `agents.utils.memory`), and `cli.utils` is `cli.prompts`.
- `backtest.summarize` takes a `run_backtest` result or the path of a decision log, in place of a `TradingMemoryLog`.
- Removed: `SignalProcessor` (the rating is parsed by `process_signal`), the `create_social_media_analyst` alias (use `create_sentiment_analyst`), `symbol_utils.is_yahoo_safe`, the unused `project_dir` config key, and the graph attributes `curr_state`, `ticker` and `log_states_dict`, which held the previous run's state.

### Added

- **Jev post screening.** With `TYPESAFE_API_KEY` set, TypeSafe's Jev reads each StockTwits and Reddit post the Sentiment Analyst fetches: posts that are not about the company are dropped, and each source opens with a count of the rest by stance. Without the key nothing changes. (#1376)
- B3 tickers (`.SA`) are benchmarked against the Ibovespa. (#1366)

### Models

- GPT-6 Sol and GPT-6 Luna are the default deep and quick models, and Claude Opus 5.5 replaces Opus 5 in the picker. Opus 5 and GPT-5.4 Mini remain valid model IDs.

### Fixed

- Several graphs in one process each read their own data vendors. (#1369)
- SEC EDGAR cash flow statements find capital expenditure for filers that moved it to purchases of productive assets (NVIDIA since fiscal 2022, Amazon since 2016), whose recent periods read as empty. (#1370)
- SEC EDGAR annual statements list fiscal years only.
- A historical run is no longer told today's date, or a date after the run, in coverage notices and the instrument context.
- The Fundamentals Analyst can call the insider transactions tool.
- An unreachable Yahoo on insider transactions is reported as unavailable, not as a symbol without data.
- A graph reused across runs, as in a backtest, no longer keeps every run's full state.
- A checkpointed CLI run says whether it resumed or started fresh.
- A blank path variable (`TRADINGAGENTS_RESULTS_DIR` and the like) keeps the default path.
- StockTwits messages reach the prompt as plain text rather than HTML-escaped.
- The test suite is independent of the developer's `.env`, time zone and network. (#1368, #1372)

### Contributors

Thanks to everyone who reported these or sent a fix:

[@codify88](https://github.com/codify88), [@davidalmeida90](https://github.com/davidalmeida90), [@duongylinh](https://github.com/duongylinh), [@jccl2](https://github.com/jccl2), [@yuina368](https://github.com/yuina368).

## [0.5.0] — 2026-09-18

Point-in-time integrity across every dated path, decisions that are recorded as
they were made, backtesting over a grid of tickers and dates, the caller's
portfolio as run input, and SEC EDGAR fundamentals served as filed.

### Highlights

- **Fundamentals as filed.** SEC EDGAR serves US company statements as they stood on the run's date: a period that has ended but has not been filed is not served, and a figure restated later still reads as first reported. Keyless, opt-in via the vendor chain.
- **Backtesting.** `run_backtest` runs the pipeline over a ticker and date grid into its own decision log, and `summarize` scores the settled cells; `tradingagents backtest` does the same from the CLI.
- **Portfolio context.** `propagate(..., portfolio=...)` and `--portfolio` let the trader, risk and portfolio agents size against real holdings. A run without one is never treated as a flat book.
- **Decisions are recorded as made.** An unreadable decision is flagged for review everywhere instead of becoming a tradeable Hold, and a rating argued against is no longer read as the call.

### Point-in-time and honest attribution

- Dated tools take the run's date from graph state, so an omitted or later date cannot reach a vendor. (#1331, #1319, #1118)
- Insider filings and prediction-market odds are bounded by the run date; insider rows state that a trade becomes public when its Form 4 is filed.
- A feed that never observed a window reports it as unavailable rather than as an absence, across news, Reddit and StockTwits.
- The resolved company identity says when it describes today rather than the run date.
- The verification snapshot quotes the prices the vendor reported, never a gap-filled value.
- A vendor failure is a vendor failure: yfinance raises instead of returning its errors as text, an outage is not reported as a company with no data, and a chain where every vendor is unavailable says so instead of ending the run.
- The macro vintage pin is clamped to the vendor's own clock, so a run dated today cannot ask for a vintage it does not have.
- A historical run is not served a present-day company profile by either fundamentals vendor. (#1300)

### Decisions and evaluation

- The labelled rating decides, whatever separates it, and prose naming several ratings is reviewed rather than guessed.
- Decision prompts state the shape of their answer, so a provider without structured output still returns a readable decision.
- A report that was not produced says so, instead of appearing as an empty section.
- Backtest scoring reads the direction each rating claimed: a Sell that fell is a hit, and Hold reports no hit rate.
- The outcome window is configurable (`holding_period_days`), and reflection states the window it judges.
- A settled decision is not logged twice, and a failed reflection no longer stops the next run. (#645)
- The trader states entry and stop levels as prices, so a percentage no longer fails the whole proposal. (#1288)

### CLI

- `tradingagents backtest`, with `--run-id` to continue an interrupted sweep. (#1234)
- The previous run's selections come back as prompt defaults. (#1236, #920)
- A run with no readable rating says so; the live view no longer scrolls; messages that read like Python values are shown. (#649, #784)
- The state log keeps non-ASCII readable. (#1081)

### Data sources

- SEC EDGAR fundamentals vendor (US filers, keyless).
- Hong Kong and Shanghai tickers resolve to the symbols Yahoo serves. (#1342, #957, #1260)
- Reddit is fetched as one combined request per run. (#1286)
- One OHLCV cache file per symbol. (#1330)

### Models

- Current lineups for every provider: GPT-6 Astra and the GPT-5.6 family, Gemini 3.8 Flash, Claude Opus 5 and Fable 5.1, Grok 4.6, DeepSeek Flash, Qwen 3.8, GLM-5.3, MiniMax M3, Kimi K3 and the current Mistral snapshots.
- Every provider accepts a model ID the picker does not list.
- GLM traffic goes to the platform its key belongs to, and Ollama structured output no longer sends a tool_choice it rejects. (#1062)

### Changed

- The memory log records `REVIEW` for a decision with no readable rating, where it previously recorded `Hold`.
- Optional fields the model did not provide are named as such rather than omitted.
- Removed dependencies nothing imports: backtrader, redis, setuptools, langchain-experimental, parsel, tqdm. (#1353, #1070)

### Contributors

Thanks to everyone who reported these or sent a fix:

[@akashkpfreelancer](https://github.com/akashkpfreelancer), [@angziii](https://github.com/angziii), [@anupamme](https://github.com/anupamme), [@AyushKar2005](https://github.com/AyushKar2005), [@bulkypanda](https://github.com/bulkypanda), [@CadeYu](https://github.com/CadeYu), [@chiang21fcb](https://github.com/chiang21fcb), [@dajiaohuang](https://github.com/dajiaohuang), [@dewrama](https://github.com/dewrama), [@DogInfantry](https://github.com/DogInfantry), [@emitov](https://github.com/emitov), [@farukerdem34](https://github.com/farukerdem34), [@flydragon2018](https://github.com/flydragon2018), [@fusshell](https://github.com/fusshell), [@Ganesh1729-ui](https://github.com/Ganesh1729-ui), [@gyx09212214-prog](https://github.com/gyx09212214-prog), [@hamzabudeir](https://github.com/hamzabudeir), [@ihsieh31](https://github.com/ihsieh31), [@jaylew20250206](https://github.com/jaylew20250206), [@kaushik-yadav](https://github.com/kaushik-yadav), [@kbnnf](https://github.com/kbnnf), [@kevinkda](https://github.com/kevinkda), [@LudwigJMarx](https://github.com/LudwigJMarx), [@lx7720](https://github.com/lx7720), [@malandrindev](https://github.com/malandrindev), [@mhd325ic-hash](https://github.com/mhd325ic-hash), [@minhdn90](https://github.com/minhdn90), [@miznan](https://github.com/miznan), [@mmssix](https://github.com/mmssix), [@mrbob-git](https://github.com/mrbob-git), [@newnewself](https://github.com/newnewself), [@prithvirajrh](https://github.com/prithvirajrh), [@PyriteResearch](https://github.com/PyriteResearch), [@Rajatendu1](https://github.com/Rajatendu1), [@Recnelis0](https://github.com/Recnelis0), [@Rodvask](https://github.com/Rodvask), [@samhoooo](https://github.com/samhoooo), [@sheiun-xu](https://github.com/sheiun-xu), [@shivsin25](https://github.com/shivsin25), [@SmileShaun](https://github.com/SmileShaun), [@SonnyRajagopalan](https://github.com/SonnyRajagopalan), [@taro0915](https://github.com/taro0915), [@wupengbo125](https://github.com/wupengbo125), [@wxggzz](https://github.com/wxggzz), [@Yixiang-Wu](https://github.com/Yixiang-Wu), [@ZahirBodrike](https://github.com/ZahirBodrike), [@ZHUYAWEI](https://github.com/ZHUYAWEI), [@zkwang616](https://github.com/zkwang616).

## [0.4.0] — 2026-08-31

Look-ahead and point-in-time fixes across the data and memory layers, clearer
decision signals, working CLI checkpoint resume, and the GPT-5.6 / GLM-5.3 models.

### Fixed

- **FRED macro look-ahead.** Historical macro requests were served from today's
  data vintage, leaking later revisions into a backtest; both the observations
  and metadata requests now pin the vintage to the as-of date. (#1275)
- **Social sentiment look-ahead.** StockTwits and Reddit were fetched with no
  date, so a historical run showed today's chatter as if it were from the as-of
  date; the social path is now trimmed to the analysis window, via one shared
  UTC half-open window rule (`dataflows/date_window`) used by news too. (#1220)
- **Memory point-in-time guard.** `get_past_context` returned every resolved
  lesson regardless of the run date; each resolved entry now records the date
  its outcome became known, and a historical run only sees lessons resolved by
  the trade date. (#1251)
- **Premature reflection.** A decision was settled on a partial return if a rerun
  happened before its holding window fully traded; resolution now waits for the
  full window. (#1169)
- **Latest OHLCV bar dropped.** The newest bar with a NaN close was silently
  dropped before the date cutoff, making the previous trading day look like the
  latest; dates are normalized per element (DST- and non-US-market safe) and a
  missing latest close raises rather than falling back. (#1201)
- **Debate opening fabrication.** The first speaker in each debate round rebutted
  an empty opponent response, fabricating the other side; all five debators now
  open with their own case when no opponent has spoken. (#1176)
- **Silent Hold.** An unparseable Portfolio Manager rating (including a fullwidth
  colon) was coerced to a tradeable Hold; it now surfaces a `REVIEW` sentinel,
  with `parse_rating` keeping its silent default for compatibility callers. (#1170)
- **`--checkpoint` was a no-op on the CLI.** Checkpoint setup lived only in
  `propagate()`; the CLI streamed the checkpointer-less graph. The lifecycle is
  now shared, and a resume feeds `None` so LangGraph continues the interrupted
  run instead of duplicating messages. (#1249)
- **DeepSeek via OpenRouter.** `deepseek/<id>` fell through to default
  capabilities and had object-form `tool_choice` forced on it; the official
  namespace is stripped so it reuses the native DeepSeek quirks. (#1199)
- **Trader price grounding.** The Trader saw only the digested plan; it now also
  receives the technical market report so entry/stop levels anchor to real price
  structure. (#1167)

### Added

- **Configurable output-token cap.** `max_tokens` / `TRADINGAGENTS_MAX_TOKENS`,
  forwarded to every provider (Gemini as `max_output_tokens`), so a model that
  emits unbounded reasoning can be bounded instead of hanging. (#1204)
- **Latest models.** Added the GPT-5.6 family (`gpt-5.6` / `gpt-5.6-terra` /
  `gpt-5.6-luna`) and GLM-5.3 (`glm-5.3`, `glm-5.3-flash`). The default models
  are now `gpt-5.6` (deep) and `gpt-5.6-luna` (quick).

### Contributors

Thanks to everyone who reported these or sent a fix:

[@PyriteResearch](https://github.com/PyriteResearch), [@yiran1268](https://github.com/yiran1268), [@fabiolenine](https://github.com/fabiolenine), [@lx7720](https://github.com/lx7720), [@taro0915](https://github.com/taro0915), [@Jaswanth-Sriram-Veturi](https://github.com/Jaswanth-Sriram-Veturi), [@ariesy](https://github.com/ariesy), [@liangzj1999](https://github.com/liangzj1999), [@zkwang616](https://github.com/zkwang616), [@aniketshukla1](https://github.com/aniketshukla1), [@loulanyue](https://github.com/loulanyue), [@hudsonwa](https://github.com/hudsonwa), [@daleselaji-dev](https://github.com/daleselaji-dev), [@wolfoswald777-crypto](https://github.com/wolfoswald777-crypto).

## [0.3.1] — 2026-07-05

Correctness and stability patch: data look-ahead, graph-router crash-safety,
checkpoint identity, crypto sentiment sources, and configurable resilience.

### Fixed

- **Alpha Vantage look-ahead filter now runs.** The fundamentals payload is a
  JSON string, so the dict-only guard skipped filtering and future-dated reports
  leaked into historical runs; parse before filtering. (#1115, @zachthebird)
- **News analyst prompt matches the tool.** The prompt advertised
  `get_news(query, ...)` but the tool takes a ticker; aligned to stop
  hallucinated free-text query calls. (#1116, @shcheuk)
- **Shared debate/risk routers can't crash mid-run.** Both routers return more
  targets than any one edge mapped; every edge now shares the complete path map,
  so a fall-through under prompt/i18n/refactor drift stays routable.
  (#1088, @Fr3ya, @sa7an7, @Sushanth012)
- **Checkpoint resume respects graph shape.** The thread id folds in selected
  analysts, debate/risk depth, and asset mode, so a resume under different
  choices no longer continues the wrong graph. (#1089, @bossjoker1, @Ghraven)
- **Crypto sentiment sources resolve.** StockTwits lists crypto as `<BASE>.X`
  (Yahoo's `BTC-USD` 404s) and Reddit needs the base symbol to match; the social
  path now maps crypto correctly for both. (#1113, @suremadoreai)

### Added

- **Configurable LLM retry budget.** `llm_max_retries` /
  `TRADINGAGENTS_LLM_MAX_RETRIES` is forwarded to every provider, so a transient
  429 burst no longer aborts a run. (#1091, @yanggaome)
- **Bedrock API-key auth.** `AWS_BEARER_TOKEN_BEDROCK` authenticates Amazon
  Bedrock without AWS access keys and takes precedence over an ambient
  `AWS_PROFILE`. (#1103, @praxstack)
- **Latest Claude models.** Added Claude Sonnet 5 (`claude-sonnet-5`) and
  Fable 5 (`claude-fable-5`); effort control now covers the Claude 5 line.

## [0.3.0] — 2026-06-22

Stabilization and extensibility release: a CI gate, a unified verified
data-access contract, a provider and data-vendor registry, and a maintenance
sweep that hardened config precedence, the model catalog, data resilience, and
structured output.

### Added

- **CI gate.** GitHub Actions runs the pytest suite across Python 3.10-3.13,
  strict `ruff`, and a clean-install smoke that imports the package and CLI to
  catch undeclared dependencies. (#994, #197)
- **Provider registry.** OpenAI-compatible providers register as a single spec,
  and a generic `openai_compatible` endpoint covers vLLM, LM Studio, and relays.
  Adds NVIDIA NIM, Kimi, Groq, Mistral, and a native Amazon Bedrock client.
- **Macro and prediction-market vendors.** FRED macro indicators and Polymarket
  event probabilities, surfaced to the news and macro analysts.
- **Programmatic report output.** `TradingAgentsGraph.save_reports()` writes the
  same report tree the CLI produces, for headless and API runs. (#1037)
- **Env-configurable reasoning depth** via `TRADINGAGENTS_OPENAI_REASONING_EFFORT`,
  `TRADINGAGENTS_GOOGLE_THINKING_LEVEL`, and `TRADINGAGENTS_ANTHROPIC_EFFORT`,
  each gated to the models that accept it.

### Changed

- **Verified data-access contract.** Symbol normalization on every vendor path
  (identity, returns, CLI, news); the configured vendor list is the exact
  resolution chain with no silent fallback to unselected vendors; a typed
  `VendorError` taxonomy; look-ahead-safe news windows; stale-OHLCV rejection;
  inclusive yfinance date ranges.
- **Config precedence.** An explicit `TRADINGAGENTS_*` value or CLI flag now wins
  over interactive defaults for debate and risk round counts,
  `--checkpoint / --no-checkpoint`, and the Docker provider profile; invalid
  boolean env values fail loudly. (#975, #976, #977)
- **Current-generation model catalog.** Refreshed provider lineups; retired
  `gpt-4.1`, Claude Sonnet 4.5, and the Gemini 2.5 line.
- **Optional vendors degrade** instead of aborting a run: a failed macro or
  prediction-market lookup returns a no-data sentinel.
- **Analyst prompts lead with the current date** so tool-call date ranges anchor
  to the run date rather than the model's training cutoff. (#836)

### Fixed

- **Instrument identity.** Deterministic ticker-to-company resolution prevents
  wrong-company hallucination, and a verified market-data snapshot grounds price
  and indicator claims. (#814, #830)
- **Social and market data sources.** Reddit RSS-first with 429 backoff,
  StockTwits transport hardening, and Alpha Vantage timeout plus
  key-versus-rate-limit handling.
- **Structured output.** Local OpenAI-compatible servers no longer reject
  object-form `tool_choice`; a thinking model that returns no parsed result falls
  back to free text; null-ish strings in optional price fields coerce to `None`.
  (#1038, #1051, #1057)

### Removed

- The no-op `analyst_concurrency_limit` config knob; parallel analyst execution
  is planned for a later release. (#979)
- The unused committed `uv.lock`. (#1030)

### Contributors

Thanks to everyone who shaped this release through code, design, and reports:

[@CadeYu](https://github.com/CadeYu), [@Zavianx](https://github.com/Zavianx), [@weijianz-opc](https://github.com/weijianz-opc), [@naltun](https://github.com/naltun), [@brahmasky](https://github.com/brahmasky), [@nik2208](https://github.com/nik2208), [@thieucong98](https://github.com/thieucong98), [@Derekko-web](https://github.com/Derekko-web), [@LukiPrince](https://github.com/LukiPrince), [@Eddieargenal](https://github.com/Eddieargenal), [@Ghraven](https://github.com/Ghraven), [@ms32035](https://github.com/ms32035), [@yting27](https://github.com/yting27), [@nyxst4ck](https://github.com/nyxst4ck), [@KenCheung-AIxFinance](https://github.com/KenCheung-AIxFinance), [@yangyusheng2n](https://github.com/yangyusheng2n), [@fareloj](https://github.com/fareloj), [@haosenwang1018](https://github.com/haosenwang1018), [@octo-patch](https://github.com/octo-patch), [@seifenk](https://github.com/seifenk), [@CaoYuhaoCarl](https://github.com/CaoYuhaoCarl), [@mihailnica10](https://github.com/mihailnica10), [@Dado-hash](https://github.com/Dado-hash), [@Handsomemikezzz](https://github.com/Handsomemikezzz), [@ydhawesome](https://github.com/ydhawesome), [@macd2](https://github.com/macd2), [@AyushKar2005](https://github.com/AyushKar2005), [@wildhuman](https://github.com/wildhuman), [@robert23kim](https://github.com/robert23kim), [@bngness](https://github.com/bngness), [@tedix-rodrigo](https://github.com/tedix-rodrigo), [@malaccan](https://github.com/malaccan), [@rfalken78](https://github.com/rfalken78), [@dengli1971-droid](https://github.com/dengli1971-droid), [@proofconcept39](https://github.com/proofconcept39), [@prasta1](https://github.com/prasta1), [@liximin](https://github.com/liximin), [@jeffhuen](https://github.com/jeffhuen), [@mazar](https://github.com/mazar), [@soyangelromero](https://github.com/soyangelromero), [@CNQQC](https://github.com/CNQQC), [@dovetaill](https://github.com/dovetaill), [@fperdigon](https://github.com/fperdigon), [@gyx09212214-prog](https://github.com/gyx09212214-prog), [@RSXLX](https://github.com/RSXLX).

## [0.2.5] — 2026-05-11

### Added

- **Grounded Sentiment Analyst.** The renamed `sentiment_analyst` now reads
  real Yahoo News, StockTwits, and Reddit data before generating its report,
  replacing the prior flow that could fabricate social posts under prompt
  pressure. (#557, #607)
- **MiniMax provider** with the full M2.x catalog (M2.7 / M2.5 / M2.1 / M2
  plus highspeed variants, 204K context). Dual-region: Global
  (`MINIMAX_API_KEY`) and China (`MINIMAX_CN_API_KEY`).
- **Dual-region Qwen and GLM** with separate keys per region — international
  (`DASHSCOPE_API_KEY`, `ZHIPU_API_KEY`) and China (`DASHSCOPE_CN_API_KEY`,
  `ZHIPU_CN_API_KEY`), selectable via a secondary region prompt. (#758)
- **`TRADINGAGENTS_*` env-var configurability for `DEFAULT_CONFIG`.** Override
  `llm_provider`, deep/quick model IDs, `backend_url`, `output_language`,
  debate-round counts, checkpoint flag, and benchmark ticker via `.env` with
  type-aware coercion (string / int / bool). (#602)
- **Interactive API-key detection in the CLI.** When the selected provider's
  key is missing, the CLI prompts for it and persists the value to `.env`
  so the analysis run continues without restart.
- **Remote Ollama support.** `OLLAMA_BASE_URL` points the CLI and the
  programmatic client at a remote `ollama-serve`. The CLI surfaces the
  resolved endpoint and warns on common malformed inputs. Adds a
  `"Custom model ID"` option for models pulled via `ollama pull`. (#648, #768)
- **Configurable news-fetch parameters** in `DEFAULT_CONFIG` — per-ticker
  article limit, macro headline limit, lookback window, and macro search
  queries. (#606, #683)
- **Configurable alpha benchmark** for non-US tickers. Replaces hardcoded
  SPY with regional indices for `.NS` (^NSEI), `.T` (^N225), `.HK` (^HSI),
  `.L` (^FTSE), `.TO` (^GSPTSE), `.AX` (^AXJO), `.BO` (^BSESN); explicit
  `benchmark_ticker` override available. Eliminates FX drift dominating
  alpha for non-USD listings. (#628, #684)
- **Multi-language output covers every user-facing agent** — researchers,
  risk debators, research manager, and trader, ending the previous
  partial-localization reports. (#575)
- **Model catalog refresh.** OpenAI GPT-5.5 frontier, Anthropic Claude Opus
  4.7, Gemini 3.1 Flash-Lite GA, xAI Grok 4.20, Qwen 3.6 line. Versioned IDs
  only; auto-shifting aliases moved to the `"Custom model ID"` option.

### Changed

- **Sentiment Analyst** is now consistently named across the CLI dropdown,
  status panel, and final reports (previously the backend was renamed but
  the CLI still said "Social Analyst"). The `AnalystType.SOCIAL = "social"`
  wire value is kept for saved-config back-compat.

### Fixed

- **Structured output works on DeepSeek V4 / reasoner and MiniMax M2.x.**
  Those providers reject `tool_choice` per their tool-calling docs; the
  binding flow now skips it automatically via a capability table.
- **`pip install .` installations pick up the project `.env`** when running
  the CLI as a console script. (#747)
- **Reports save end-to-end** — streamed chunks were previously dropped from
  `complete_report.md`. (#719, #736)
- **Ticker prompt preserves exchange suffixes** (`.SH`, `.SZ`, `.SS`, `.HK`,
  `.T`, etc.) for A-share, HK, Tokyo, and other non-US flows. (#770)
- **Docker permission errors** no longer block first-run write to
  `~/.tradingagents/`. (#519, #627, #672, #771)
- **Config state no longer leaks between runs** when sub-dicts are mutated;
  `set_config` partial updates preserve sibling defaults. (#788)
- **`max_recur_limit` config actually applies** — previously read but not
  forwarded to the propagator. (#764)
- **Missing-API-key error** names the exact env var to set. (#680)
- **Quieter startup** — suppressed the noisy upstream
  `LangChainPendingDeprecationWarning` from langgraph-checkpoint; will be
  removed once that package ships its fix.

### Security

- **Ticker path-traversal validation** at every filesystem-path site (cache,
  checkpoint database, results) so a malicious ticker cannot escape its
  intended directory. (#618)

## [0.2.4] — 2026-04-25

### Added

- **Structured-output decision agents.** Research Manager, Trader, and Portfolio
  Manager now use `llm.with_structured_output(Schema)` on their primary call
  and return typed Pydantic instances. Each provider's native structured-output
  mode is used (`json_schema` for OpenAI / xAI, `response_schema` for Gemini,
  tool-use for Anthropic, function-calling for OpenAI-compatible providers).
  Render helpers preserve the existing markdown shape so memory log, CLI
  display, and saved reports keep working unchanged. (#434)
- **LangGraph checkpoint resume** — opt-in via `--checkpoint`. State is saved
  after each node so crashed or interrupted runs resume from the last
  successful step. Per-ticker SQLite databases under
  `~/.tradingagents/cache/checkpoints/`. `--clear-checkpoints` resets them. (#594)
- **Persistent decision log** replacing the per-agent BM25 memory. Decisions
  are stored automatically at the end of `propagate()`; the next same-ticker
  run resolves prior pending entries with realised return, alpha vs SPY, and
  a one-paragraph reflection. Override path with `TRADINGAGENTS_MEMORY_LOG_PATH`.
  Optional `memory_log_max_entries` config caps resolved entries; pending
  entries are never pruned. (#578, #563, #564, #579)
- **DeepSeek, Qwen (Alibaba DashScope), GLM (Zhipu), and Azure OpenAI**
  providers, plus dynamic OpenRouter model selection.
- **Docker support** — multi-stage build with separate dev and runtime images.
- **`scripts/smoke_structured_output.py`** — diagnostic that exercises the
  three structured-output agents against any provider so contributors can
  verify their setup with one command.
- **5-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell) used
  consistently by Research Manager, Portfolio Manager, signal processor, and
  the memory log; Trader keeps 3-tier (Buy / Hold / Sell) since transaction
  direction is naturally ternary.
- **Pytest fixtures** — lazy LLM client imports plus placeholder API keys so
  the test suite runs cleanly without credentials. (#588)

### Changed

- **`backend_url` default is now `None`** rather than the OpenAI URL. Each
  provider client falls back to its native default. The previous default
  leaked the OpenAI URL into non-OpenAI clients (e.g. Gemini), producing
  malformed request URLs for Python users who switched providers without
  overriding `backend_url`. The CLI flow is unaffected.
- All file I/O passes explicit `encoding="utf-8"` so Windows users no longer
  hit `UnicodeEncodeError` with the cp1252 default. (#543, #550, #576)
- Cache and log directories moved to `~/.tradingagents/` to resolve Docker
  permission issues. (#519)
- `SignalProcessor` reads the rating from the Portfolio Manager's rendered
  markdown via a deterministic heuristic — no extra LLM call.
- OpenAI structured-output calls default to `method="function_calling"` to
  avoid noisy `PydanticSerializationUnexpectedValue` warnings emitted by
  langchain-openai's Responses-API parse path. Same typed result, no warnings.

### Fixed

- Empty memory no longer triggers fabricated past-lessons in agent prompts;
  the memory-log redesign makes this structurally impossible since only the
  Portfolio Manager consults memory and only when entries exist. (#572)
- Tool-call logging processes every chunk message, not just the last one, and
  memory score normalization handles empty score arrays. (#534, #531)

### Removed

- `FinancialSituationMemory` (the per-agent BM25 system) and the dead
  `reflect_and_remember()` plumbing; subsumed by the persistent decision log.
- Hardcoded Google endpoint that caused 404 when `langchain-google-genai`
  changed its API path. (#493, #496)

### Contributors

Thanks to everyone who shaped this release through code, design, and reports:

- [@claytonbrown](https://github.com/claytonbrown) — checkpoint resume (#594), test fixtures (#588), design feedback on cost tracking (#582) and structured validation (#583)
- [@Bcardo](https://github.com/Bcardo) — memory-log redesign (#579), empty-memory hallucination report (#572), encoding fix proposal (#570)
- [@voidborne-d](https://github.com/voidborne-d) — memory persistence design (#564), portfolio manager state fix (#503)
- [@mannubaveja007](https://github.com/mannubaveja007) — structured-output feature request (#434)
- [@kelder66](https://github.com/kelder66) — RAM-only memory issue (#563)
- [@Gujiassh](https://github.com/Gujiassh) — tool-call logging fix (#534), test stub PR (#533)
- [@iuyup](https://github.com/iuyup) — memory score normalization fix (#531)
- [@kaihg](https://github.com/kaihg) — Google base_url fix (#496)
- [@32ryh98yfe](https://github.com/32ryh98yfe) — Gemini 404 report (#493)
- [@uppb](https://github.com/uppb) — OpenRouter dynamic model selection (#482)
- [@guoz14](https://github.com/guoz14) — OpenRouter limited-model report (#337)
- [@samchenku](https://github.com/samchenku) — indicator name normalization (#490)
- [@JasonOA888](https://github.com/JasonOA888) — y_finance pandas import fix (#488)
- [@tiffanychum](https://github.com/tiffanychum) — stale import cleanup (#499)
- [@zaizou](https://github.com/zaizou) — Docker permission issue (#519)
- [@Stosman123](https://github.com/Stosman123), [@mauropuga](https://github.com/mauropuga), [@hotwind2015](https://github.com/hotwind2015) — Windows encoding bug reports (#543, #550, #576)
- [@nnishad](https://github.com/nnishad), [@atharvajoshi01](https://github.com/atharvajoshi01) — encoding fix proposals (#568, #549)

## [0.2.3] — 2026-03-29

### Added

- **Multi-language output** for analyst reports and final decisions, with a
  CLI selector. Internal agent debate stays in English for reasoning quality. (#472)
- **GPT-5.4 family models** in the default catalog, with deep/quick model split.
- **Unified model catalog** as a single source of truth for CLI options and
  provider validation.

### Changed

- `base_url` is forwarded to Google and Anthropic clients so corporate proxies
  work consistently across providers. (#427)
- Standardised the Google `api_key` parameter to the unified `api_key` form.

### Fixed

- Backtesting fetchers no longer leak look-ahead data when `curr_date` is in
  the middle of a fetched window. (#475)
- Invalid indicator names from the LLM are caught at the tool boundary instead
  of crashing the run. (#429)
- yfinance news fetchers respect the same exponential-backoff retry as price
  fetchers. (#445)

### Contributors

- [@ahmedk20](https://github.com/ahmedk20) — multi-language output (#472)
- [@CadeYu](https://github.com/CadeYu) — model catalog typing (#464)
- [@javierdejesusda](https://github.com/javierdejesusda) — unified Google API key parameter (#453)
- [@voidborne-d](https://github.com/voidborne-d) — yfinance news retry (#445)
- [@kostakost2](https://github.com/kostakost2) — look-ahead bias report (#475)
- [@lu-zhengda](https://github.com/lu-zhengda) — proxy/base_url support request (#427)
- [@VamsiKrishna2021](https://github.com/VamsiKrishna2021) — invalid indicator crash report (#429)

## [0.2.2] — 2026-03-22

### Added

- **Five-tier rating scale** (Buy / Overweight / Hold / Underweight / Sell)
  introduced for the Portfolio Manager.
- **Anthropic effort level** support for Claude models.
- **OpenAI Responses API** path for native OpenAI models.

### Changed

- `risk_manager` renamed to `portfolio_manager` to match the role description
  shown in the CLI display.
- Exchange-qualified tickers (e.g. `7203.T`, `BRK.B`) preserved across all
  agent prompts and tool calls.
- Process-level UTF-8 default attempted for cross-platform consistency
  (note: this approach did not actually take effect; replaced in v0.2.4 with
  explicit per-call `encoding="utf-8"` arguments).

### Fixed

- yfinance rate-limit errors are retried with exponential backoff. (#426)
- HTTP client SSL customisation is supported for environments that need
  custom certificate bundles. (#379)
- Report-section writes handle list-of-string content gracefully.

### Contributors

- [@CadeYu](https://github.com/CadeYu) — exchange-qualified ticker preservation (#413)
- [@yang1002378395-cmyk](https://github.com/yang1002378395-cmyk) — HTTP client SSL customisation (#379)

## [0.2.1] — 2026-03-15

### Security

- Patched `langchain-core` vulnerability (LangGrinch). (#335)
- Removed `chainlit` dependency affected by CVE-2026-22218.

### Added

- `pyproject.toml` build-system configuration; the project now installs via
  modern packaging tooling.

### Removed

- `setup.py` — dependencies consolidated to `pyproject.toml`.

### Fixed

- Risk manager reads the correct fundamental report source. (#341)
- All `open()` calls receive an explicit UTF-8 encoding (initial pass).
- `get_indicators` tool handles comma-separated indicator names from the LLM. (#368)
- `Propagation` initialises every debate-state field so risk debaters never
  see missing keys.
- Stock data parsing tolerates malformed CSVs and NaN values.
- Conditional debate logic respects the configured round count. (#361)

### Contributors

- [@RinZ27](https://github.com/RinZ27) — `langchain-core` security patch (#335)
- [@Ljx-007](https://github.com/Ljx-007) — risk manager fundamental-report fix (#341)
- [@makk9](https://github.com/makk9) — debate-rounds config issue (#361)

## [0.2.0] — 2026-02-04

This is the largest release since the initial public version. The framework
moved from single-provider to a multi-provider architecture and grew several
production-ready surfaces.

### Added

- **Multi-provider LLM support** (OpenAI, Google, Anthropic, xAI, OpenRouter,
  Ollama) via a factory pattern, with provider-specific thinking configurations.
- **Alpha Vantage** integration as a configurable primary data provider, with
  yfinance as a community-stability fallback.
- **Footer statistics** in the CLI: real-time tracking of LLM calls, tool
  calls, and token usage via LangChain callbacks.
- **Post-analysis report saving** — the framework writes per-section markdown
  files (analyst reports, debate transcripts, final decision) when a run
  completes.
- **Announcements panel** — fetches updates from `api.tauric.ai/v1/announcements`
  for the CLI welcome screen.
- **Tool fallbacks** so a single vendor outage does not stop the pipeline.

### Changed

- Risky / Safe risk debaters renamed to **Aggressive / Conservative** for
  consistency with the displayed agent labels.
- Default data vendor switched to balance reliability and quota across
  community deployments.
- Ollama and OpenRouter model lists updated; default endpoints clarified.

### Fixed

- Analyst status tracking and message deduplication in the live display.
- Infinite-loop guard in the agent loop; reflection and logging hardened.
- Various data-vendor implementation bugs and tool-signature mismatches.

### Contributors

This release is the first with substantial outside contributions; many community
PRs from late 2025 also landed here.

- [@luohy15](https://github.com/luohy15) — Alpha Vantage data-vendor integration (#235)
- [@EdwardoSunny](https://github.com/EdwardoSunny) — yfinance fetching optimisations (#245)
- [@Mirza-Samad-Ahmed-Baig](https://github.com/Mirza-Samad-Ahmed-Baig) — infinite-loop guard, reflection, and logging fixes (#89)
- [@ZeroAct](https://github.com/ZeroAct) — saved results path support (#29)
- [@Zhongyi-Lu](https://github.com/Zhongyi-Lu) — `.env` gitignore (#49)
- [@csoboy](https://github.com/csoboy) — local Ollama setup (#53)
- [@chauhang](https://github.com/chauhang) — initial Docker support attempt (#47, later reverted; the merged Docker support shipped in v0.2.4)

## [0.1.1] — 2025-06-07

### Removed

- Static site assets that had been bundled with v0.1.0; the public site now
  lives separately.

## [0.1.0] — 2025-06-05

### Added

- **Initial public release** of the TradingAgents multi-agent trading
  framework: market / sentiment / news / fundamentals analysts; bull and bear
  researchers; trader; aggressive, conservative, and neutral risk debaters;
  portfolio manager. LangGraph orchestration, yfinance data, per-agent
  BM25 memory, single-provider OpenAI integration, interactive CLI.

[0.2.4]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TauricResearch/TradingAgents/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/TauricResearch/TradingAgents/releases/tag/v0.1.0
