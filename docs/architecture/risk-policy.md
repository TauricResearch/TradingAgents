# FR-04 Risk Policy — Draft for Human Approval

- **Status:** PROPOSED — PENDING HUMAN APPROVAL
- **Owner:** D
- **Policy version:** `DRAFT-NOT-FROZEN` (the product version must be approved and
  hashed before implementation; tests use a separate `test-policy-v1` fixture)
- **Related:** FR-04, NFR-04, NFR-05, NFR-09, INV-01, INV-04, INV-06, INV-07

> Threshold values marked PENDING are not approved financial parameters. If they are
> not configured, the gate must reject safely. Tests inject explicit fixture values;
> those values do not become product defaults.

## 1. Allowed actions and paper-only preconditions

| Rule | Required behaviour | Source | Status |
|---|---|---|---|
| Action enum | Only exact `BUY`, `SELL`, `HOLD` | FR-04 / execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
| Paper only | No broker, no real account, no real order | FR-04 | PLAN-SPECIFIED (not frozen) |
| Long only | Short selling and negative positions are rejected | execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
| No leverage | Cash may not go below zero after costs | execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
| HOLD | Valid no-trade suggestion **with a valid evidence pack**; no order, no ledger entry; missing pack -> `REVIEW` | FR-04 / execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
| BUY/SELL quantity | Positive integer; `bool`, float, string, `None` rejected | FR-04 | PLAN-SPECIFIED (not frozen) |
| SELL quantity | `quantity <= current holding` | execution plan §5.1 | PLAN-SPECIFIED (not frozen) |

`REVIEW`, `BLOCKED`, `INCOMPLETE` are system states, not trading actions. They must not
be counted as successful trades, nor as evidence that the model "won".

## 2. Monetary arithmetic

1. All prices, cash, fees, NAV and thresholds are `Decimal`.
2. JSON decimal fields are decimal fixed-point strings; binary floats are rejected.
3. No implicit float conversion. No `float()` anywhere in a money path.
4. Quantization is explicit in the policy. The test fixture uses `0.01`.
5. Comparisons use exact Decimal values; boundary equality is decided by the stated
   operator (`<=` or `<`), never by floating rounding.

## 3. Deterministic reference formulas

These formulas are the proposed test oracle. They must be approved before they become
the implementation's public policy.

Let:

- `nav_before = cash + Σ(qty_i * mark_price_i)`
- BUY execution price: `exec_price = reference_price * (1 + slippage_bps / 10000)`
- SELL execution price: `exec_price = reference_price * (1 - slippage_bps / 10000)`
- `notional = quantity * exec_price`
- `fee = notional * fee_bps / 10000`
- BUY: `cash_after = cash - notional - fee`
- SELL: `cash_after = cash + notional - fee`
- `qty_after = qty_before + quantity` (BUY) or `qty_before - quantity` (SELL)
- `nav_after = cash_after + Σ_{i≠s}(qty_i * mark_i) + qty_after * exec_price`

Required checks, in fail-closed order:

1. Policy is present, active, hash-consistent, and has all required fields.
2. Portfolio is present, version matches, cash ≥ 0, all position quantities ≥ 0.
3. Proposal schema, action, quantity, price and time types are valid.
4. Proposal hash, evidence pack hash, run identity and expiry are valid.
5. Price is not future-dated and is within `price_freshness_seconds`.
6. Currency matches the portfolio base currency.
7. `nav_before > 0`.
8. `cash_after >= 0`.
9. `notional <= max_order_pct * nav_before`.
10. `qty_after * exec_price / nav_after <= max_position_pct`.
11. SELL: `quantity <= current holding`.
12. Audit outbox, verdict and ledger rows can be committed atomically.

A failure at any step returns the mapped structured status/reason and performs no
ledger mutation.

## 4. Approved-in-plan thresholds vs pending configurations

| Parameter | Value | Source | Status |
|---|---|---|---|
| `max_position_pct` | 20% (`0.20`) | execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
| `max_order_pct` | 10% (`0.10`) | execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
| `price_freshness_seconds` | PENDING | execution plan requires a threshold but gives no value | Safe reject if unset |
| `fee_bps` / fee model | PENDING | execution plan requires explicit fee; no value | Safe reject if unset |
| `slippage_bps` / slippage model | PENDING | execution plan requires explicit slippage; no value | Safe reject if unset |
| Base currency | PENDING (demo proposal: USD) | execution plan requires compatibility | Safe reject if unset |
| Policy version/hash | PENDING | shared contract decision | Safe reject if unset |
| Quantization | PENDING (test fixture: `0.01`) | money precision | Safe reject if unset |
| HOLD evidence requirement | DECIDED: valid pack required; missing -> `REVIEW/EVIDENCE_MISSING` | FR-04 evidence rule | Decided in this spec; not a financial threshold |

The 20% and 10% caps are course-demonstration constraints, not investment advice.

### Test fixture parameters (not product policy)

The offline suite injects `price_freshness_seconds=240`, `fee_bps=10` and
`slippage_bps=0` via `fakes.TEST_FIXTURE_PARAMETERS`. These are **test-only** values,
not approved product defaults. The product values remain PENDING. The unconfigured or
invalid-policy cases (`FND-13/14/15`, `EVD-12/13/14`) require safe rejection.

EVD-07/EVD-08 pass the freshness value as an explicit `freshness` parameter and assert
the rule "age equal to the parameter is allowed, one second over is rejected", rather
than freezing a product default of 300 seconds.

## 5. Status and reason mapping (proposed contract)

`RiskVerdict.status` is not frozen. The proposed mapping is:

| Condition | Status | reason_code |
|---|---|---|
| Valid BUY/SELL | `APPROVED` | — |
| Valid HOLD with a valid pack | `APPROVED` (no action) | — |
| Schema/action/quantity/price invalid | `REJECTED` | `INVALID_OUTPUT` |
| Malformed hash syntax (not 64 lowercase hex) | `REJECTED` | `INVALID_OUTPUT` |
| Well-formed hash does not match content or run binding | `REJECTED` | `INTEGRITY_VIOLATION` |
| Limit/cash/holding/currency/price-age violation | `REJECTED` | `POLICY_REJECTED` |
| Price older than `price_freshness_seconds` | `REJECTED` | `STALE_DATA` |
| Naive/ambiguous time | `REJECTED` | `INVALID_TIME` |
| Missing evidence pack or non-executable proposal without claims | `REVIEW` | `EVIDENCE_MISSING` |
| Claim cites an evidence id absent from the pack | `REVIEW` | `INVALID_CITATION` |
| Sole usable support is unreachable | `REVIEW` | `VENDOR_UNAVAILABLE` |
| Sole usable support is stale | `REVIEW` | `STALE_DATA` |
| Future-dated price/evidence | `REJECTED` | `FUTURE_DATA` |
| Stale caller snapshot (proposal version matches DB) | `REJECTED` | `STALE_PORTFOLIO` |
| Proposal loses a concurrent portfolio-version race | `STALE_PORTFOLIO` | `STALE_PORTFOLIO` |
| Policy missing/inactive/expired | `BLOCKED` | `INCOMPATIBLE_STATE` |
| Audit/storage unavailable | `BLOCKED` | `AUDIT_UNAVAILABLE` |
| Duplicate `proposal_hash` | stored verdict | original reason |
| Budget/deadline (B) | `INCOMPLETE` | `BUDGET_DENIED` |

The 20% concentration cap is a position-increasing (BUY) control. A SELL is
risk-reducing and exempt from the concentration cap; the 10% notional cap still
applies to both BUY and SELL (approved FND-22/ACT-15/FND-23).

A stale caller snapshot whose proposal version still matches the DB is
`REJECTED/STALE_PORTFOLIO`. A proposal that loses a concurrent version race
(proposal version differs from the DB) returns the distinct status
`STALE_PORTFOLIO` with no ledger write; this distinction is pinned by ATM-01 versus
ATM-07/ATM-09.

HOLD requires a valid pack; claims are optional because no order is created. BUY
and SELL require at least one claim with resolvable evidence.

The gate stores exactly one outbox event per stored verdict (`Phase.RISK_GATE`);
this is the count the duplicate/idempotency tests assert. Outbox status mapping:
APPROVED=`OK`, REJECTED/BLOCKED=`BLOCKED`, REVIEW=`REVIEW`.

### Outbox payload compatibility

The outbox `payload_hash` follows E's `contracts.audit.recompute_payload_hash` byte
semantics: canonical JSON over the RunEvent fields excluding `payload_hash`, sorted
keys and compact separators, with UTC timestamps rendered as `...Z` (not `+00:00`).
This prevents `verify_payload`/replay from rejecting valid risk_gate events. The
outbox stores the same `Z` timestamp.

B's accepted reason table includes `INVALID_CITATION`, `INTEGRITY_VIOLATION`,
`INVALID_TIME`, `STALE_DATA` and `VENDOR_UNAVAILABLE`. E's current `RunEvent` draft
does not yet include all five; contracts v1 must align before implementation. If a
storage/busy failure is not well represented by `AUDIT_UNAVAILABLE`, an RFC to E/B is
required before adding a new code.

### Hash-mismatch rule

One rule applies to all hash/identity cases:

1. A hash that is not 64 lowercase hex characters is **malformed**:
   `REJECTED/INVALID_OUTPUT` (IDM-03, IDM-04).
2. A well-formed hash that does not match the recomputed content, or that binds the
   proposal to a different run/snapshot/policy than the supplied object, is an
   **integrity violation**: `REJECTED/INTEGRITY_VIOLATION` (EVD-02, EVD-03, EVD-04,
   EVD-11, EVD-15, IDM-02, IDM-05..09, IDM-14).
3. Missing or unusable evidence is a **review/data-availability** outcome, not an
   integrity or policy violation: `REVIEW` with `EVIDENCE_MISSING`,
   `INVALID_CITATION`, `VENDOR_UNAVAILABLE` or `STALE_DATA` depending on the cause.

No hash/identity failure writes the ledger.

### Evidence availability state machine

Only evidence items with `availability=available` are usable. `stale` and
`unreachable` items are excluded; the availability state is the state, and the reason
code is the cause. If a proposal loses all usable support:

- unreachable sole support -> `REVIEW/VENDOR_UNAVAILABLE` (EVD-21);
- stale sole support -> `REVIEW/STALE_DATA` (EVD-22);
- missing pack -> `REVIEW/EVIDENCE_MISSING` (EVD-01, EVD-20);
- dangling citation -> `REVIEW/INVALID_CITATION` (EVD-19).

A stale **proposal price** is a separate price-freshness failure:
`REJECTED/STALE_DATA` (EVD-08). `AUDIT_UNAVAILABLE` is an audit/storage cause and is
not an evidence `availability` value.

### Gate verdict -> RunEvent.RunStatus

`HOLD` is an `AdvisoryProposal.action`, not a `RiskVerdict.status`. The proposed
mapping to E's event status is:

| Gate outcome | `RunEvent.RunStatus` |
|---|---|
| `APPROVED` trade | `OK` |
| `APPROVED` HOLD no-action | `OK` |
| `REJECTED` | `BLOCKED` |
| `REVIEW` | `REVIEW` |
| `BLOCKED` | `BLOCKED` |
| `INCOMPLETE` (B/app level) | `INCOMPLETE`, not emitted by the risk gate |

If contracts v1 chooses a different mapping, this is deferred to that contract; C
must not infer a mapping from prose.

## 5a. Contract gap: instrument identity

The execution plan's `AdvisoryProposal` field list does not name the traded instrument.
A gate cannot update a specific position without an instrument identity. The offline
tests therefore use a **test-only** `ticker` field in the fake proposal and include it
in the proposed canonical hash. This is a gap-filler, not a new formal contract.

Before implementation, C/B must either add an approved instrument field to
`AdvisoryProposal` or freeze a `run_id -> RunSpec.ticker` lookup that the gate can
consume. Until then, integration is BLOCKED at this interface. The behavioural tests
remain valid once either resolution is frozen; only the field-mapping shim changes.

## 6. Idempotency and version semantics

- `proposal_hash` is the idempotency key.
- The SQLite unique constraint is intentionally `UNIQUE(proposal_hash)` (single
  column). `proposal_hash` covers `run_id`, so this is at least as strict as
  `(run_id, proposal_hash)`; a cross-run collision would imply identical formal
  proposal content including the run id.
- The hash covers all formal `AdvisoryProposal` fields except `proposal_hash` itself.
  Test-only bypass fields (`policy_override`, `bypass`) are not part of the formal
  hash and must not influence the decision.
- Duplicate hash returns the stored verdict. It does not re-evaluate, charge twice,
  add a position twice, or append a second ledger entry.
- `portfolio_version` increments exactly once per committed execution.
- HOLD, REVIEW, REJECTED and BLOCKED do not increment `portfolio_version` and do not
  write a ledger entry.
- A failed audit/storage transaction rolls back verdict, ledger and outbox together;
  a retry with the same hash may then commit once.

## 7. Proposed hash canonicalization (needs B/C/E approval)

The test fixture uses canonical JSON:

- object keys sorted lexicographically;
- separators `,` and `:` with no extra whitespace;
- UTF-8 encoding;
- `Decimal` rendered as a plain fixed-point string;
- aware datetimes normalized to UTC ISO-8601; naive datetimes are invalid for the
  product contract;
- tuples rendered as arrays;
- booleans before integers in type dispatch;
- SHA-256 over the encoded bytes, lowercase hex.

This is a proposal. It is not an approved shared contract. C/B own `AdvisoryProposal`,
A owns `EvidencePack`, E owns `RunEvent`; a mismatch must be resolved by an RFC and
joint review, not by silently changing the tests.

## 8. SQLite tables expected by the tests

The tests are written against the D design and will fail red until the implementation
provides these tables. B/E may review the names, but they are not shared contracts.

- `portfolios(portfolio_id, version, base_currency, cash, as_of)`
- `positions(portfolio_id, symbol, quantity, mark_price)`
- `ledger_entries(entry_id, proposal_hash, verdict_id, side, quantity, exec_price,
  fee, cash_after, position_after, created_at)`
- `risk_verdicts(verdict_id, proposal_hash, status, reasons, checked_rules,
  portfolio_version, expires_at, created_at)`
- `outbox_events(event_id, run_id, sequence, phase, timestamp, status, payload_hash,
  prev_event_hash, metrics, reason_code)`
- `schema_meta(key, value)`

The ledger amount columns are Decimal strings. Positions with zero quantity may be
omitted from read snapshots. The outbox is append-only and uses a unique
`(run_id, sequence)` pair with `event_id` as the consumer dedupe key.

## 9. Change control

Changing a threshold, status meaning, hash canonicalization, or the 20%/10% caps
requires a requirement/ADR update, a test update, human review, and a new policy
version/hash. A PR may not silently relax the policy to make a failing test pass.
