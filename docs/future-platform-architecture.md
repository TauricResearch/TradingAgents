# Future platform architecture

## Executive decision

Build a modular research platform around one canonical flow:

```text
collector -> immutable snapshot -> offline decide -> offline label -> evaluate
```

Keep it a modular monolith until measured load or team boundaries justify
separate services. The only continuously deployed component should be the
collector and its health alerts. Decisions, labels, and evaluations are explicit
offline jobs over immutable artifacts. This is a research system; brokerage and
live capital are future, separately gated capabilities.

The goal is not to preserve every experimental mechanism already built. The goal
is to preserve the useful contracts—time, lineage, portfolio intent, outcomes,
and evaluation—so a new data source, model, simulator, or broker does not require
another architecture rewrite.

## Product boundaries

The platform should support four related workflows:

1. continuously capture broad, point-in-time evidence;
2. replay a frozen research protocol without outcome access;
3. simulate and compare synchronized portfolios under identical assumptions;
4. eventually preview and paper-test orders through official broker adapters.

It should not make live trades, promote a strategy, or expose a historical-alpha
claim automatically. Those are decisions outside the core pipeline.

## Proposed module boundaries

This is a target layout, not a claim about the current directory tree.

```text
tradingagents/
  domain/          immutable evidence, forecast, target, order, outcome types
  collection/      source policies, normalization, receipts, snapshot assembly
  research/        protocols, prompts, model calls, decision artifacts
  portfolio/       allocators, constraints, target-to-order planning
  simulation/      calendars, fills, costs, corporate actions, accounting
  evaluation/      baselines, folds, statistics, reports
  ports/           small interfaces owned by the domain
  adapters/
    evidence/      RSS, X, licensed feeds
    models/        local checkpoints and provider clients
    storage/       SQLite/Postgres/artifact stores
    market_data/   prices, calendars, corporate actions
    brokers/       paper and, much later, approved live integrations
  apps/            thin CLI and collector composition roots
```

Dependencies point inward. Domain objects import no provider SDK, web framework,
database driver, or CLI library. Adapters implement ports; application entry
points select and configure them. A provider-specific payload is normalized once
at the boundary and never leaks through the research or portfolio layers.

Prefer a small protocol plus a conformance test over a universal base class. Add
an abstraction only when two real implementations need it.

## Canonical contracts

The following objects should be versioned, serializable, and content-addressed.

### Evidence and time

- `EvidenceItem`: source identity, source class, author/publisher, publication
  time, first-received time, region/language, and exact content-vintage ID.
- `CollectionReceipt`: one provider attempt, request policy, start/end times,
  status, budget usage, and exact returned lineage.
- `EvidenceSnapshot`: complete eligible item set at one declared decision cutoff,
  plus collector policy and schema versions.

The platform needs both event time and system time. `published_at` answers when
the source says an event occurred; `received_at` answers when this system could
first know it. Corrections create new content vintages and never rewrite the old
one. Empty successful queries remain observable facts.

### Research and portfolio

- `ResearchProtocol`: frozen universe rules, evidence policy, prompt/template,
  model requirement, horizons, ablations, costs, and evaluation plan.
- `DecisionArtifact`: snapshot, protocol, universe, prior state, prompt/input,
  code, model artifact, response, and target hashes.
- `AssetForecast`: horizon, direction or expected-return estimate, confidence,
  abstention state, and evidence references.
- `TargetPortfolio`: currency, as-of cutoff, asset weights, cash, constraints,
  allocator version, and reason codes.

The forecast is not an order. Allocation remains deterministic and testable.
`TargetPortfolio` is the shared handoff to both simulation and future execution.

### Outcomes and evaluation

- `PriceVintage`: vendor, observed time, raw price, adjustment data, and calendar
  identity.
- `OutcomeSet`: committed decision IDs, entry/exit convention, price vintages,
  costs, returns, and missingness reasons.
- `EvaluationReport`: evaluated targets, baselines, folds, statistics, protocol,
  code, and one-time holdout access record.

Every artifact ID should change when a scientifically relevant input changes.
Operational metadata such as retry logs can be linked without changing the
semantic result ID.

## Core ports

Keep each port narrow and typed:

```python
class EvidenceSource(Protocol):
    def collect(self, request: CollectionRequest) -> CollectionBatch: ...

class SnapshotStore(Protocol):
    def commit(self, draft: SnapshotDraft) -> EvidenceSnapshot: ...
    def load(self, snapshot_id: str) -> EvidenceSnapshot: ...

class ForecastModel(Protocol):
    def identity(self) -> FrozenModelIdentity: ...
    def forecast(self, request: ForecastRequest) -> ForecastBundle: ...

class MarketDataSource(Protocol):
    def prices(self, request: PriceRequest) -> PriceVintageSet: ...

class PortfolioAllocator(Protocol):
    def allocate(self, request: AllocationRequest) -> TargetPortfolio: ...

class Broker(Protocol):
    def capabilities(self) -> BrokerCapabilities: ...
    def preview(self, plan: OrderPlan) -> BrokerPreview: ...
    def submit(self, approved: ApprovedOrderPlan) -> SubmissionResult: ...
```

The examples communicate ownership, not a mandate to create interfaces before
they are used. Storage should expose evidence-only reads to the decision job and
outcome reads only to labeling/evaluation jobs. Enforce that boundary in exported
bundles and database roles where practical; do not rely only on prompt text.

## Application flow

### Collector

One idempotent process performs scheduled broad-news and bounded X collection,
stores per-request receipts, commits raw content vintages, records a heartbeat,
and alerts on stale or partial cycles. It may also capture the daily prices and
corporate-action vintages needed for later labels. Combining those schedules in
one app does not combine their logical datasets or permissions.

The collector knows nothing about forecasts, weights, or realized strategy
returns. It must continue collecting when no experiment is active.

### Snapshot

An offline command selects evidence using only declared cutoff information and
commits the exact lineage. Snapshot creation fails closed when required receipts,
timestamps, content vintages, or source-policy identities are missing. It never
reaches back to a live source to fill history silently.

### Decide

An outcome-blind command accepts snapshot and protocol IDs. One structured model
call per arm/session emits forecasts for the complete universe; deterministic
allocation emits target portfolios. The job writes append-only artifacts and can
resume only from already committed inputs. A failed or reserved call remains
visible rather than being replaced until a favorable result appears.

Historical claims require a frozen model artifact with a documented training
cutoff. A mutable hosted alias is acceptable for prospective collection but not
for a strong historical no-leakage claim.

### Label

After the horizon passes, a non-LLM command joins committed targets to captured
market-data vintages. It applies one calendar, corporate-action, entry/exit, and
cost convention to all arms. Missing outcomes produce explicit missingness or
predeclared carry-forward behavior, never an improvised substitute.

### Evaluate

Evaluation constructs walk-forward folds, applies embargoes, runs champion and
control portfolios, and publishes machine-readable plus human-readable reports.
Research parameters are frozen before the final holdout is opened. Report null,
negative, and incomplete results as first-class outcomes.

## Backtest and execution parity

Research and future broker workflows should share these pure transformations:

```text
ForecastBundle
    -> TargetPortfolio
    -> OrderPlan(current positions, prices, constraints)
    -> FillEvents
    -> PortfolioState
```

A vectorized simulator may accelerate screening, but a promotion candidate must
also pass an event-driven simulator using the same order-plan and accounting
semantics as paper execution. Centralize calendars, rounding, fees, slippage,
short availability, dividends, splits, cash, and FX conventions. Differences
between simulated and broker behavior should be explicit adapter capabilities,
not hidden branches in strategy code.

## Configuration and composition

Use one versioned configuration model with layered inputs:

```text
safe defaults < config file < environment/secrets < explicit CLI flags
```

Validate the resolved configuration at startup and persist a redacted semantic
fingerprint with each run. Secret values never enter fingerprints or logs. Each
CLI or daemon is a thin composition root; business logic remains callable from
Python without invoking a CLI process.

## Adapter strategy

### Evidence and models

Preserve raw provider payloads where licensing permits, then normalize into the
canonical evidence contract. Source adapters own pagination, rate limits, retry
classification, and provenance mapping. They do not own research ranking or
portfolio logic.

Model adapters normalize structured output, token/cost usage, provider response
IDs, and artifact identity. Favor locally archived open-weight checkpoints for
historical replay. Hosted models are useful for prospective experiments but
must be labeled mutable unless the provider guarantees an immutable checkpoint.

### Market data

Start with one implementation that can supply documented price and
corporate-action vintages. A convenience API that returns today's revised view
of history is fine for exploration, but not for the final confirmatory label set.

### Brokers

Broker integrations remain optional plugins. Use documented official APIs only;
do not automate consumer websites or depend on reverse-engineered endpoints.
Robinhood and Fidelity can be supported only if an appropriate, stable API and
account entitlement exist at implementation time. Their retail product names do
not by themselves imply a supported trading API.

Choose a first broker based on sandbox quality, API stability, order/status
coverage, and reconciliation—not popularity. A broker adapter is not complete
until it handles capabilities, idempotency keys, partial fills, rejected and
canceled orders, trading hours, asset precision, rate limits, reconnects, and
position/cash reconciliation.

Rollout is always:

```text
read-only account sync -> order preview -> broker sandbox/paper -> shadow mode
-> tightly capped live trial, only after explicit human authorization
```

Live submission requires an independent risk envelope, stale-data checks,
maximum order/notional/loss limits, duplicate-order protection, a kill switch,
an audit trail, and a fresh approval artifact. No strategy result may flip live
trading on automatically.

## Open-source boundary

The public core should include domain contracts, local SQLite storage, synthetic
fixtures, the offline pipeline, deterministic allocators and simulators,
evaluation code, adapter conformance tests, and reproducible example protocols.

Keep secrets, cloud account identifiers, alert endpoints, private operational
runbooks, licensed raw datasets, broker credentials, and any private strategy
configuration out of the repository. Public fixtures must be synthetic or
redistributable. Optional dependencies belong in extras so a local research run
does not install every cloud, feed, or broker SDK.

Before a public release, add a license and governance policy, threat model,
security contact, contribution guide, generated-data provenance rules, secret
scanning, dependency review, and a clean-room quickstart that works without paid
accounts.

## Delivery plan

### Phase 1 — Finish the lean evidence loop

- run one collector with durable receipts, content vintages, heartbeat, and
  alerts;
- stabilize the new content-addressed snapshot and offline research artifacts;
- remove runtime dependencies on retired decision/marker workers; and
- document historical migrations without rewriting them.

### Phase 2 — Make offline replay credible

- extend snapshot, decide, label, and evaluate commands from the current thin
  harness into the full preregistered experiment;
- enforce outcome-blind decision inputs;
- preserve price and correction vintages;
- add a frozen-model artifact contract and training-cutoff verification; and
- provide a small synthetic end-to-end fixture.

### Phase 3 — Establish evidence, not features

- preregister the universe, horizons, baselines, costs, exclusions, power
  analysis, and one-time holdout policy;
- run prospective shadow collection long enough to cover different regimes;
- publish nulls and failure rates alongside efficacy; and
- promote nothing without a statistically and economically meaningful result.

### Phase 4 — Generalize through real adapters

- extract a second storage, evidence, model, or market-data adapter only when it
  is genuinely needed;
- run conformance suites against every implementation; and
- keep provider selection in application composition, outside domain logic.

### Phase 5 — Optional broker and public release work

- implement read-only and paper capabilities with the best-supported official
  API first;
- compare paper fills and reconciliation against the event simulator;
- complete the open-source hardening checklist; and
- consider constrained live capital only through a separate safety review.

## Acceptance test

The architecture is working when a contributor can take a frozen snapshot and
protocol, run an outcome-blind decision with a verifiable model artifact, attach
only later-captured outcomes, reproduce a costed portfolio report, swap one
adapter through configuration, and verify every material input from artifact
IDs—without starting cloud services or editing strategy code.

Until that test passes, add reliability and scientific validity before adding
more workers, dashboards, orchestration layers, or broker integrations.
