# Global-event research contract

## Status

This is a research design, not a validated trading strategy. No completed
experiment in this repository demonstrates alpha, profitability, or readiness
for live capital.

The design asks a narrow question: can a small, point-in-time sample of broad
world news and public reaction improve a synchronized portfolio forecast beyond
simple market and price-only baselines?

## How this differs from upstream TradingAgents

The [upstream TradingAgents paper](https://arxiv.org/abs/2412.20138) calls a
committee of analyst, debate, trader, risk, and portfolio-manager agents for one
named ticker and date. Its main contribution is the multi-agent firm simulation.

This branch adds a separate experiment:

- discovery begins with broad global themes and trends, not tickers, company
  feeds, or investor-relations material;
- the model receives one time-bounded market-wide evidence snapshot and produces
  cross-sectional asset forecasts in one structured call per experimental arm;
- deterministic code, rather than an LLM persona, converts forecasts into a
  constrained portfolio; and
- snapshots, decisions, later outcomes, baselines, costs, and statistical tests
  are linked as reproducible research artifacts.

That combination is meaningfully different from upstream. It is best described
as a point-in-time global-event evaluation harness, not a fundamentally new
forecasting algorithm. Immutable data, content hashes, portfolio constraints,
transaction-cost models, bootstrap tests, and multiple-testing corrections are
established methods. Do not claim that this project invented them or is the
first leakage-aware LLM trading study.

A fair assessment is strong differentiation from upstream, but moderate novelty
against the broader quantitative-research literature. The strongest contribution
is the research and evaluation harness. There is currently zero empirical
evidence that its forecasts contain tradable alpha.

## Lean flow

```text
collector -> immutable snapshot -> offline decide -> offline label -> evaluate
```

### What is implemented now

The collector and the `tradingagents-research` CLI enforce this application
ordering with content-addressed filesystem artifacts. Snapshot creation applies
publication, receipt, exact prior-day X-cycle, selection, and query-coverage
checks. Decision generation imports no outcome provider, validates the exact
selected evidence and grounded bundle independently of the model adapter,
requires declared checkpoint metadata to predate the tested cutoffs, accepts
`global_events` and `without_public_reaction` arms, and carries failed dates
forward visibly. Labeling accepts only a committed decision ID, and evaluation
verifies the exact object, decision, and label references.

This first harness is not the complete experiment described below. Its default
label adapter records the yfinance response obtained at label time, not a market
price vintage captured contemporaneously with the session. Its evaluator reports
a costed strategy path, benchmark path, drawdown, turnover, missingness, and a
Newey-West mean diagnostic for one decision batch. It does not yet orchestrate
all baselines, ablations, walk-forward folds, bootstrap intervals, multiplicity
correction, or one-time holdout access. The checkpoint file is a validated
declaration and returned-model allowlist, not independent proof of model weights
or training data. The current filesystem store also has no durable first-attempt
registry: rerunning a stochastic decision or mutable price request can create a
second artifact, and the CLI does not yet prevent an operator from choosing one.
It is therefore an exploratory harness until attempt selection is preregistered
and enforced. Import separation is not an OS security boundary; run phases with
separate credentials and artifact permissions for stronger isolation.

### 1. Collect broad evidence

The single deployed worker polls general, world, business, and technology news
feeds across several regions. Its frozen topic families cover rates, trade,
politics and geopolitics, companies and the economy, technology, and energy.
Queries never name a portfolio ticker or issuer.

X is a bounded public-reaction channel, not a representative opinion poll. The
daily budget permits at most two trend requests and three searches. Selection
caps repeat authors, discourages automated-looking activity, and excludes
verified business and government accounts. Company-authored material is also
rejected at the forecast boundary.

The editorial-news core is intentionally conservative. The current allowlist is
AP, BBC, France 24, NPR, Reuters, and Sky News. A successful provider response
may contain zero forecast-eligible stories and must retain exact `0`/`[]`
lineage; a raw empty or failed provider response is unhealthy. Either case must
not silently relax the source policy.

### 2. Freeze an immutable snapshot

Every provider attempt gets a receipt. Every retained item records both its
publication time and the time this system first received it. Exact fetched
content is content-addressed, and a snapshot commits the complete eligible
lineage at a declared decision cutoff.

A snapshot is useful only if it can be reconstructed without asking a live
provider what used to be present. Historical provider IDs alone are not enough.
For Google News, each exact RSS rendering is therefore stored under a stable
content-vintage ID while retaining the provider cluster ID for grouping. Snapshot
selection uses the latest database-observed eligible vintage at the cutoff and
keeps superseded revisions in append-only lineage. This protects the collected
news path from provider edits; it does not claim that every external source has a
general-purpose bitemporal API.

### 3. Decide offline and outcome-blind

The decision runner reads only a committed snapshot and frozen protocol inputs.
It extracts global events and produces structured forecasts for the entire
fixed universe. A deterministic allocator then applies gross, position, sector,
cash, and turnover constraints. Within the outcome-blind batch, abstaining
preserves the prior committed target; it does not force liquidation or observe
post-return position drift.

The decision artifact must bind at least:

- snapshot and protocol IDs;
- universe and prior-position IDs;
- exact prompt and input hashes;
- code/build identity;
- model artifact identity and training cutoff; and
- raw structured response plus allocated targets.

A provider model name or mutable API alias is not a frozen checkpoint. LangGraph
checkpoints only resume program state; they do not freeze model weights or erase
facts learned during training. The offline CLI rejects declared checkpoint dates
that overlap the experiment and verifies the model identity returned by the
provider, but it cannot authenticate a hosted model's weights or training data.
A credible historical test therefore requires a locally archived model artifact
whose training cutoff predates the tested period, or equivalent provider evidence
that the exact immutable checkpoint predates it. Until that exists, the harness
can test data-side timing and prospective behavior but cannot make a strong
historical no-leakage claim.

### 4. Attach outcomes later

Labels are computed only after targets are committed. Each strategy should use
the same next-session entry convention, holding horizon, price vintage,
corporate-action treatment, and cost model. Labeling must not invoke the model or
rewrite a decision.

Fetching an old adjusted price from a mutable public endpoint months later is
not equivalent to having captured that vintage; Yahoo's adjusted history can be
revised. The collector should eventually
snapshot the required raw prices, adjustments, and calendars daily, or the
project should use a genuinely versioned market-data provider. The current
yfinance adapter hashes and stores the values it sees at labeling time, which
makes that artifact reproducible but does not make the underlying history
point-in-time safe.

### 5. Evaluate the portfolio

The confirmatory evaluation should be synchronized across the full universe.
The champion should be compared with news-only, public-reaction-only, market or
inverse-volatility, equal-weight, momentum, stale-input, and shuffled-input
controls under the same execution and cost assumptions. Walk-forward folds use
an embargo at least as long as the outcome horizon, and the final holdout is
opened once rather than tuned against.

Report coverage and missing decisions alongside return, drawdown, turnover,
Sharpe, benchmark-relative performance, and cross-sectional diagnostics. Use
HAC uncertainty estimates, block bootstrap intervals, and a declared
multiple-testing correction where their assumptions fit. These tools reduce
overclaiming; they do not rescue a small or biased sample.

## Leakage rules

For a decision cutoff at time `t`:

1. Require `published_at < t` and `received_at < t` for every evidence item.
2. Read a committed content vintage, never the source's current rendering.
3. Keep current fundamentals, revised macro series, prediction markets, adaptive
   decision memory, and realized outcomes out unless point-in-time versions are
   explicitly available.
4. Give the decision process no database role, view, file, or prompt containing
   post-cutoff labels.
5. Commit targets before outcome access, and make retries append-only and visible.
6. Freeze the universe and delisting rules before evaluation; a present-day list
   creates survivorship bias.
7. Freeze the model artifact and its training cutoff; prompt instructions alone
   cannot control parametric memory.
8. Keep research folds and the final holdout separate. Do not revise the protocol
   after seeing holdout efficacy.

## Interpretation limits

- The source mix is English-language and predominantly Western. It observes a
  narrow editorial core and selected X reaction, not global population
  sentiment.
- The fixed universe is twenty large US companies, so results do not automatically
  generalize to smaller firms, non-US markets, or other eras.
- Content hashes prove identity and lineage, not truth. Citation presence is not
  semantic fact-checking.
- Simple clustering and source-diversity heuristics are not mathematical
  information-gain maximization or a formal information-theoretic optimizer.
- Separate stochastic model calls for ablations introduce sampling variance.
  Counterbalancing call order helps but does not replace preregistered replicates
  or sensitivity analysis.
- The current offline evaluator is a boundary and accounting smoke test, not the
  preregistered multi-arm analysis.
- Content addressing makes reruns visible but does not itself choose a canonical
  first attempt; confirmatory use needs an append-only attempt registry.
- The protocol still needs an ex-ante power analysis before a confirmatory run.

The honest success condition is evidence that the full, costed portfolio
outperforms declared controls out of sample and survives leakage audits. Until
then, the output is a research dataset and a falsifiable hypothesis—not a trading
product.
