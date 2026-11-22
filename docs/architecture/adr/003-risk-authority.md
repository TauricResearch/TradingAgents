# ADR-003 — Deterministic Risk Authority for the Paper Ledger

- **Status:** PROPOSED — PENDING HUMAN APPROVAL
- **Owner:** D (risk_gate)
- **Related requirements:** FR-04, NFR-04, NFR-05, NFR-09, INV-01, INV-04, INV-06, INV-07
- **Related governance:** GATE-01, GATE-02, GATE-05, GATE-06, D3, D8
- **Related artifacts:** `docs/architecture/threat-model.md`, `docs/architecture/risk-policy.md`,
  `docs/architecture/permission-model.md`, `docs/architecture/invariants.md`

> This ADR is an agent-prepared draft. It is not APPROVED. Only a human reviewer may
> change the status and sign the approval record. The draft deliberately does not
> claim that any shared contract, policy threshold, or runtime permission is frozen.

## Context

TradingAgents produces free-text analysis and a rating through an LLM-driven graph.
A rating is advice, not an execution authorization. The project needs a deterministic,
auditable boundary between "the model suggested something" and "the paper ledger
changed". Upstream has risk-debate agents (`tradingagents/agents/risk_mgmt/`) and a
free-text portfolio context, but no deterministic gate, no portfolio version, no
idempotency key, and no transactional audit outbox.

The shared contracts named in `execution_plan_261111.md` §5.1
(`AdvisoryProposal`, `EvidencePack`, `RunSpec`, `RiskVerdict`, `AuditSink`, `RunEvent`)
are not all frozen. At the time of this draft, only E's `RunEvent` and
`ExperimentManifest` exist, and they are on an unmerged draft PR with changes
requested. B's `AdvisoryProposal` and A's `EvidencePack` do not exist in any branch.

The execution plan's `AdvisoryProposal` field list also omits the traded instrument.
The offline tests use a test-only `ticker` field as a gap-filler. C/B must resolve this
before implementation, either by adding an approved instrument field or by freezing a
`run_id -> RunSpec.ticker` lookup. This is an open interface blocker, not an approved
contract.

## Decision

1. `RiskGate` is the **sole authority** that may change the paper ledger.
2. The public evaluation entry point is fixed:
   `RiskGate.evaluate_and_commit(proposal, evidence_pack, current_portfolio) -> RiskVerdict`.
3. LLM output is untrusted input. It may supply a proposal, but it cannot grant a
   rule exemption, raise a limit, choose a policy version, or authorize a bypass.
4. Every money value is a `Decimal`. Binary floats are rejected rather than
   silently coerced.
5. The gate re-reads `portfolio_version` inside the write transaction and compares it
   with the proposal/snapshot. A mismatch is `STALE_PORTFOLIO`, not a retry with the
   new version.
6. `proposal_hash`, `policy_hash`, `evidence_pack_hash`, and proposal expiry are
   verified before any ledger write. Hash canonicalization is a shared-contract
   decision; until frozen, the test fixture documents the proposed canonical form.
7. Ledger change, risk verdict, and audit outbox event are written in **one SQLite
   transaction**. Audit is an in-database outbox. Calling an external sink outside
   the transaction is not accepted as atomic audit.
8. `proposal_hash` is the idempotency key. A duplicate returns the stored verdict and
   never creates a second ledger entry. A concurrent duplicate is serialized by
   `BEGIN IMMEDIATE` and the unique constraint.
9. Fail closed: missing evidence, invalid policy, invalid portfolio, stale version,
   or unavailable audit/storage produces `REVIEW`, `REJECTED` or `BLOCKED` with a
   structured reason. It never produces a silent success.
10. HOLD is a valid no-trade suggestion only with a valid evidence pack (`APPROVED`,
    no ledger entry). A missing/unverifiable pack makes HOLD `REVIEW`. HOLD is not a
    failure and is distinct from `REVIEW`, `BLOCKED` and `INCOMPLETE`.
11. The gate never connects to a broker and never processes a real order. Paper-only
    and long-only are policy preconditions, not optional flags.
12. No network or LLM call is made during evaluation.

## Proposed verdict mapping

The shared `RiskVerdict` contract is not frozen; these status names are a proposal
for B/E review, not an approved public contract.

| Condition | Status | reason_code | Ledger effect |
|---|---|---|---|
| Valid BUY/SELL | `APPROVED` | none | one atomic entry |
| Valid HOLD with a valid pack | `APPROVED` | none | none |
| Invalid schema/action/quantity/price | `REJECTED` | `INVALID_OUTPUT` | none |
| Malformed hash syntax | `REJECTED` | `INVALID_OUTPUT` | none |
| Hash/identity does not match content or run binding | `REJECTED` | `INTEGRITY_VIOLATION` | none |
| Policy/limit violation | `REJECTED` | `POLICY_REJECTED` | none |
| Price older than the freshness parameter | `REJECTED` | `STALE_DATA` | none |
| Naive/ambiguous time | `REJECTED` | `INVALID_TIME` | none |
| Missing evidence pack / no claims | `REVIEW` | `EVIDENCE_MISSING` | none |
| Dangling evidence citation | `REVIEW` | `INVALID_CITATION` | none |
| Sole support unreachable | `REVIEW` | `VENDOR_UNAVAILABLE` | none |
| Sole support stale | `REVIEW` | `STALE_DATA` | none |
| Future-dated price/evidence | `REJECTED` | `FUTURE_DATA` | none |
| Stale caller snapshot (proposal version matches DB) | `REJECTED` | `STALE_PORTFOLIO` | none |
| Proposal loses a concurrent portfolio-version race | `STALE_PORTFOLIO` | `STALE_PORTFOLIO` | none |
| Policy missing/inactive/expired | `BLOCKED` | `INCOMPATIBLE_STATE` | none |
| Audit or storage unavailable | `BLOCKED` | `AUDIT_UNAVAILABLE` | rollback |
| Duplicate proposal hash | stored verdict | original reason | none |
| Budget/deadline exhausted | `INCOMPLETE` (B, outside gate) | `BUDGET_DENIED` | none |

The 20% concentration cap is a position-increasing (BUY) control. A SELL is
risk-reducing and exempt from the concentration cap; the 10% notional cap still
applies to both BUY and SELL.

A proposal that loses a concurrent `portfolio_version` race returns the distinct
status `STALE_PORTFOLIO`; a stale caller snapshot whose proposal version still
matches the DB returns `REJECTED/STALE_PORTFOLIO`. Neither writes the ledger. This
distinction is pinned by the approved ATM-01 and ATM-07/ATM-09 tests.

Hash/identity rule: malformed hash syntax is `INVALID_OUTPUT`; a well-formed hash
that does not match the recomputed content or binds a different run/snapshot/policy
is `INTEGRITY_VIOLATION`. Missing/unusable evidence is a `REVIEW` data-availability
outcome, not an integrity violation. See `risk-policy.md` for the exact case list.

Evidence availability is the state; the reason code is the cause. Only `available`
items are usable; `stale` and `unreachable` items are excluded, producing `STALE_DATA`
or `VENDOR_UNAVAILABLE` when they were the sole support. `AUDIT_UNAVAILABLE` is not an
evidence availability value.

`HOLD` is an `AdvisoryProposal.action`, not a `RiskVerdict.status`; it is
`APPROVED` no-action. For E's `RunEvent.RunStatus`, the proposed mapping is:
`APPROVED` -> `OK`, `REJECTED` -> `BLOCKED`, `REVIEW` -> `REVIEW`, `BLOCKED` ->
`BLOCKED`; `INCOMPLETE` is app/budget-level, not a risk verdict. If contracts v1
chooses differently, the mapping is deferred to that contract.

Outbox `payload_hash` uses contracts.audit canonicalization: canonical JSON of the
RunEvent fields excluding `payload_hash`, compact sorted keys, UTC timestamps with a
trailing `Z`. This is required so E's `verify_payload`/replay accepts risk_gate
events. The `UNIQUE(proposal_hash)` idempotency key is intentional: the hash includes
`run_id`, so it is at least as strict as `(run_id, proposal_hash)`.

The offline suite injects `price_freshness_seconds=240`, `fee_bps=10` and
`slippage_bps=0` as **test-only** fixture parameters. They are not approved product
defaults. The product values remain PENDING; unconfigured or invalid policy must fail
closed. The freshness boundary cases assert the rule against the parameter, not a
product default of 300 seconds.

## Transaction and schema outline

The test suite expects the following D-internal tables. They are supporting
implementation details, not frozen shared contracts:

- `portfolios(portfolio_id, version, base_currency, cash, as_of)`
- `positions(portfolio_id, symbol, quantity, mark_price)`
- `ledger_entries(entry_id, proposal_hash, verdict_id, side, quantity, exec_price,
  fee, cash_after, position_after, created_at)`
- `risk_verdicts(verdict_id, proposal_hash, status, reasons, checked_rules,
  portfolio_version, expires_at, created_at)`
- `outbox_events(event_id, run_id, sequence, phase, timestamp, status, payload_hash,
  prev_event_hash, metrics, reason_code)`
- `schema_meta(key, value)`

Additional D-internal methods used by the application and the offline tests:
`RiskGate.ensure_initialized(portfolio)` (setup only, does not authorize trades) and
`RiskGate.snapshot()` (read-only current state). The public authority remains
`evaluate_and_commit`.

## Considered alternatives

- **LLM-as-final-judge.** Rejected: non-deterministic, prompt-injectable, not
  auditable.
- **Post-hoc audit only.** Rejected: the ledger would already be wrong; INV-01
  requires prevention.
- **External broker/paper API.** Rejected for this course scope: network, credentials,
  vendor availability, and real-account risk. The demo is a local SQLite paper ledger.
- **Optimistic concurrency without re-read.** Rejected: TOCTOU between the caller's
  snapshot and commit.
- **Separate audit database/service.** Rejected for the demo: cannot be atomic with
  the local ledger. The outbox is in the same database; publication is a separate
  consumer step.

## Consequences and limitations

- Availability is sacrificed for safety: unconfigured thresholds reject instead of
  using invented financial defaults.
- SQLite serializes writers. This is acceptable for a single-user course demo; it is
  not a multi-tenant trading platform.
- INV-01 is enforced at the module/API/permission boundary. A local process with
  write access to the SQLite file can bypass the application; the threat model must
  state this trust-boundary limitation honestly.
- Tail deletion or full-chain substitution of the outbox cannot be detected from
  internal hash links alone; a trusted external reference is required. This is an
  audit limitation, not an execution-authority bypass.
- The 20% concentration and 10% notional caps come from the execution plan; they are
  course-demo policy, not investment advice.
- `price_freshness_seconds`, `fee_bps` and `slippage_bps` are PENDING human approval.
  No product default is claimed.

## Reopen conditions

Reopen this ADR if any of the following occurs: a shared contract changes a field
meaning or hash canonicalization; a broker/live-trading scope is proposed; a
multi-process or multi-tenant deployment is proposed; the concentration/notional
thresholds or fee/slippage model change; or the outbox/audit sink mapping to E's
`RunEvent` is frozen differently.

## Approval record

This section is intentionally blank. The agent may not create, infer, or backfill an
approval. A human reviewer must record the reviewer identity, date, reviewed commit
SHA, and any conditions before this ADR becomes APPROVED.
