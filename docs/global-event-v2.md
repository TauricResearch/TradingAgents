# Global-event V2 research contract

The authoritative, machine-readable contract is
`tradingagents/research_protocol.py`. Its canonical content hash is the
`protocol_id`; deployments and reliability changes have a separate `build_id`.

## Flow

1. The collector discovers broad world, business, and technology stories without
   a ticker or company watchlist. Company-authored releases are rejected.
2. Every provider/query attempt receives an independent database receipt. Older
   stories first discovered today are retained and stamped with their actual
   receipt time. Each broad-news receipt records its sorted, unique exact
   eligible lineage as `(evidence_id, raw_content_id)` pairs, the matching
   evidence-ID projection and count, plus the exact protocol and
   collector-semantic identities that created it. The stable evidence ID names
   the provider item; the raw-content ID binds the exact fetched provider
   snapshot while deliberately excluding receipt time and storage-derived
   labels.
3. A decision is allowed only after every configured broad-news query has a
   successful receipt in the cutoff-cycle window and every selected news item
   binds by both evidence and raw-content ID to its single assigned receipt.
   Missing identities, legacy scalar/ID-only lineage, or a receipt from
   different collector semantics causes the decision to fail closed.
4. Distinct paid forecast stages are ordered before invocation by the frozen
   outcome-blind XNYS-session counterbalance: a six-session cycle traverses all
   six permutations of champion, without-public-reaction, and
   public-reaction-only, then filters out stages whose input does not require a
   call. Across 252 contiguous XNYS sessions each three-stage ordinal is occupied
   84 times (and either ordinal of a constant two-stage subset 126 times).
   Formal evidence is source-stratified so X cannot crowd out broad news, and
   company-authored material is filtered again at this boundary. `trendnews`
   is collector-only topic-discovery provenance: it is never retrieved into the
   formal candidate history and never enters a prompt.
5. A deterministic allocator sees current positions and applies turnover,
   position, sector, gross, and cash constraints. A no-edge or abstain forecast
   preserves the current position; it does not mean liquidation.
6. Champion, ablation, baseline, stale-input, and shuffled-input targets are
   frozen synchronously. The without-public-reaction ablation excludes only X
   rows; because `trendnews` is not forecast evidence, the causal difference is
   exactly the selected public-reaction channel. Every prompt, input, model
   response identifier, token usage record, event, forecast, and target is
   stored append-only. Each successful result receipt also binds a
   `forecast_bundle_id` content ID to the exact persisted payload for its stage.
7. All strategies enter at the next official XNYS open and use the same captured
   price vintage and cost model. The worker wakes 15 minutes after the open to
   capture raw and adjusted opening-price, dividend, and split receipts.

## Editorial evidence and observed absence

Formal news uses a frozen strict editorial core. Publisher and host must match
an exact allowlisted pair; syndicated aggregators, company-authored material,
and unknown or incomplete provenance do not qualify. A successful query may
therefore record exact empty lineage and evidence-ID lists with count zero
(`[]`/`[]`/`0`). That is valid per-slot observed absence and never causes the
allowlist, query mapping, or slot coverage rule to relax. All exact query
receipts are still required, while the champion selection must contain at least
one eligible `globalnews` item overall.

## Failure and retry semantics

Every complete formal operation is serialized by a run-scoped database lock;
overlapping workers cannot interleave decision, mark, or review lifecycle
writes. Every model call atomically increments its durable decision/day counters
and inserts its immutable reservation artifact in one database transaction
before the provider is invoked. The provider call itself is outside that
transaction. Before any reservation, a transient operational failure may use
the bounded worker retry envelope. After the first reservation for a decision,
that decision is never retried by the process, a deployment, or a restart. If
the reserved call does not produce a valid completed decision, the interval
remains in the intent-to-treat ledger and carries forward the previous
portfolio. The carry-forward is the research outcome for that missing decision,
not permission for a replacement model call.

## Interpretation gates

The worker materializes each preregistered gate automatically from append-only
state. Outcome-bearing gates commit an access receipt before reading outcomes,
and routine status surfaces continue to hide formal weights, NAV, and returns.

- 20 assigned holding intervals: operations only, with no read of forecasts,
  weights, NAV, returns, or other outcomes.
- 60 intervals: fixed forecast-calibration and source/signal-quality diagnostics
  after an outcome-access receipt; no strategy comparison or protocol action.
- 126 intervals: a blinded operational-integrity report containing aggregate
  path, interval, mark, assignment, and bundle counts only. It reads no
  outcomes, writes no outcome-access receipt, and withholds strategy identities
  and every efficacy statistic.
- Exactly 252 intervals: the sole confirmatory report and frozen decision rule.
  The earlier automated reports are leakage-bounded diagnostics, not additional
  confirmatory looks.

Before any final outcome table is read, the publication guard requires the set
of successful decision-bundle dates to equal the target-applied assignment
dates exactly. In assignment order, it replays every member with the independent
offline verifier, requires all eight strategies and `external_calls=0`, and
persists the sole content-addressed `formal_final_verification_manifest`. Only
then may the final outcome-access receipt be committed and the readout built.
The outcome bundle, report artifact, and final run label all bind both the
manifest ID and its artifact ID. A missing, duplicate, incomplete, reordered,
or tampered manifest—or any evidence of an unauthorized earlier efficacy
look—blocks publication.

Live capital is never enabled automatically.

## Production activation invariant

Migrations 003 through 013 are applied in numeric order by the Fly MPG schema
administrator while the collector, legacy combined paper worker, decision
worker, and marker worker are all paused; runtime identities never migrate
schema. The migrations make source receipts and collection cycles append-only,
register one immutable primary confirmatory run, govern formal artifacts and
model-call budgets, require explicit release authorization, and force the
decision and marker identities through distinct outcome-blind RLS policies.
Each migration fails closed on ambiguous in-flight or pre-existing formal
state.

The exact receipt, lineage, artifact, price-capture, authorization, and role
split function hashes, fixed `search_path`, trigger/catalog shapes, ownership,
ACLs, and RLS policies are authenticated during preflight. The final collector
image must then create a complete qualifying one-shot collection-cycle
manifest. A backup containing that cycle is restored into an isolated
disposable cluster. The repository authenticates the migration-013 role
contract, exact restored cycle, and zero preauthorization formal-activity rows.
Decision and marker image/configuration semantics are independently bound by
their paused in-image preflights and PostgreSQL/deterministic replay CI
contracts; stored marker replay is available only after real intervals exist.

Release authorization binds that fresh restore evidence, all three paused
in-image configuration/preflight documents, all three Fly image digests, all
three alert-delivery receipts, and durable retirement of the legacy combined
credential. Activation requires successful post-authorization preflight for
the collector, decision worker, and marker worker. Enable the marker first and
the decision worker last. Any mismatch, stale evidence, missing heartbeat,
unresolved failure, failed delivery, or replay error keeps the relevant action
switch disabled.
