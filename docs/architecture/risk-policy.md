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
| HOLD | Valid no-trade suggestion; no order, no ledger entry | FR-04 / execution plan §5.1 | PLAN-SPECIFIED (not frozen) |
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
| HOLD evidence requirement | PENDING (test proposal: valid pack required) | FR-04 evidence rule | Safe reject if unset |

The 20% and 10% caps are course-demonstration constraints, not investment advice.

## 5. Status and reason mapping (proposed contract)

`RiskVerdict.status` is not frozen. The proposed mapping is:

| Condition | Status | reason_code |
|---|---|---|
| Valid BUY/SELL | `APPROVED` | — |
| Valid HOLD | `APPROVED` (no action) | — |
| Schema/action/quantity/price invalid | `REJECTED` | `INVALID_OUTPUT` |
| Limit/cash/holding/currency/price-age violation | `REJECTED` | `POLICY_REJECTED` |
| Missing/unverifiable evidence | `REVIEW` | `EVIDENCE_MISSING` |
| Future-dated price/evidence | `REJECTED` | `FUTURE_DATA` |
| Stale portfolio version | `REJECTED` | `STALE_PORTFOLIO` |
| Policy missing/inactive/tampered | `BLOCKED` | `INCOMPATIBLE_STATE` |
| Audit/storage unavailable | `BLOCKED` | `AUDIT_UNAVAILABLE` |
| Duplicate `proposal_hash` | stored verdict | original reason |
| Budget/deadline (B) | `INCOMPLETE` | `BUDGET_DENIED` |

The canonical reason list is shared with E's `RunEvent` draft. If a storage/busy
failure is not well represented by `AUDIT_UNAVAILABLE`, an RFC to E/B is required
before adding a new code.

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
