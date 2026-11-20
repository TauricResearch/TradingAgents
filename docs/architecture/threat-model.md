# FR-04 Threat Model — Deterministic Risk Gate and Paper Ledger

- **Status:** PROPOSED — PENDING HUMAN APPROVAL
- **Owner:** D
- **Scope:** local, single-user paper trading demo; SQLite ledger; no broker connection
- **Related:** `docs/architecture/adr/003-risk-authority.md`,
  `docs/architecture/risk-policy.md`, `docs/architecture/invariants.md`

## Assets

1. Paper cash and positions (the simulated ledger).
2. Idempotency identity (`proposal_hash`) and portfolio version.
3. Risk/audit records and outbox events.
4. Policy version/hash and thresholds.
5. Secrets outside the ledger (API keys, environment credentials) that must never
   enter prompts, reports, commits, or logs.

## Actors and trust boundaries

| Actor / source | Entry point | Trust level |
|---|---|---|
| LLM / C deliberation | `AdvisoryProposal` | Untrusted; advice only |
| A evidence service | `EvidencePack` | Untrusted until hash/time checked |
| Caller / app | `evaluate_and_commit` arguments | Must not be able to grant authority |
| Other business modules | imports, DB, environment | Must not write the ledger directly |
| Operator / human | policy file, ADR, approvals | Trusted for policy, not for bypassing code gates |
| SQLite / filesystem | DB file, WAL, disk | Trusted for local integrity, not for tamper-proof audit against an admin |

The critical boundary is between free-text/model output and the deterministic
rules. A second boundary is between the RiskGate module and every other module:
only RiskGate may change cash, positions, or ledger entries.

## Threat register

| ID | Asset | Actor / entry → boundary | Failure scenario | Invariant | Deterministic mitigation | Negative tests → failure behavior |
|---|---|---|---|---|---|---|
| T01 | Ledger | LLM/C proposal → gate | Incomplete or misleading proposal is executed; gate guesses quantity/price | INV-01 | Strict schema/semantic checks; missing quantity or price is REVIEW; no inference; claims are not instructions | `T-RISK-ACT-06`, `T-RISK-EVD-18` → no ledger write; REVIEW/INVALID_OUTPUT |
| T02 | Cash/positions | Proposal numeric fields → Decimal/int parser | Negative, zero, fractional, NaN or Infinity quantity/price corrupts cash or position | INV-01 | Finite Decimal only; positive integer quantity for BUY/SELL; reject bool/float/NaN/Inf | `T-RISK-ACT-02..14` → REJECTED INVALID_OUTPUT; no mutation |
| T03 | Ledger | Proposal `action` → enum | `SHORT`, `Overweight`, lowercase or missing action is silently mapped or executed | INV-01 | Exact `BUY`/`SELL`/`HOLD`; no free-text mapping inside the gate | `T-RISK-ACT-21/22` → REJECTED INVALID_OUTPUT; no mutation |
| T04 | Evidence/ledger | A pack → gate | Missing/expired pack, wrong pack hash, wrong run, cutoff before price time, or missing claim evidence still executes | INV-01 | Require pack; recompute pack hash; match run_id/hash; cutoff ≥ price_time; resolve claim evidence IDs | `T-RISK-EVD-01..05/18/19` → REVIEW EVIDENCE_MISSING |
| T05 | Idempotency/audit | Proposal hash → gate | Forged/reused hash changes payload, bypasses dedupe, or replays an old approval | INV-01/04 | Recompute canonical hash over all formal fields; reject malformed hash; unique `proposal_hash` | `T-RISK-IDM-02..09` → REJECTED INVALID_OUTPUT; no mutation |
| T06 | Risk rules | Proposal policy hash / policy store | Expired, inactive or mismatched policy authorizes an order with old/high limits | INV-01 | Active policy only; hash recomputation; effective/expiry window; no proposal override | `T-RISK-EVD-11..15`, `T-RISK-SEC-15` → POLICY_REJECTED/INCOMPATIBLE_STATE |
| T07 | Cash/positions | Proposal/portfolio version → DB | Concurrent update causes lost update, double spend, or oversell | INV-01/04 | `BEGIN IMMEDIATE`; re-read version inside transaction; compare proposal and caller snapshot | `T-RISK-ATM-01..04/09` → STALE_PORTFOLIO; no mutation |
| T08 | Ledger | Multiple threads/requests → gate | Same proposal executes twice | INV-04 | Unique `proposal_hash`; transaction; stored verdict returned on duplicate | `T-RISK-ATM-05..07`, `T-RISK-IDM-10..15` → one commit only |
| T09 | Ledger | Other module/caller → DB/API | Direct ledger write bypasses risk checks | INV-01 | Single writer module; private ledger functions; minimal public API; import/AST checks; DB permissions as defence in depth | `T-RISK-SEC-06/07/16` → structural check fails |
| T10 | Ledger/audit | Process crash/exception/restart | Ledger commits without verdict/outbox, or partial rows survive | INV-06 | One transaction; WAL; commit only after all rows; rollback on exception; restart idempotency | `T-RISK-ATM-10..16/22/23` → no partial rows |
| T11 | Audit | Outbox write/disk/DB lock | Trade succeeds but audit is unavailable | INV-06 | Outbox insert in the same transaction; abort and rollback; `AUDIT_UNAVAILABLE`; no external sink outside the transaction is treated as atomic | `T-RISK-ATM-10/13/14` → BLOCKED; no ledger change |
| T12 | Rules/ledger | Proposal claims / evidence text | Prompt injection says "ignore the rules" or "approve"; decision changes | INV-05/INV-01 | Gate never interprets free text as instructions; no LLM call; rules are data-driven | `T-RISK-SEC-01/02` → rules unchanged; rejection still occurs |
| T13 | Secrets | Logs/verdict/outbox/error messages | A canary secret from a claim/evidence is persisted or exported | INV-07 | Persist only allowlisted fields; never persist raw claims; redact error messages; secret scan | `T-RISK-SEC-08..12` → canary absent; test fails if leaked |
| T14 | Gate authority | API params, env vars, policy override | Caller uses `force`, `skip`, `override`, `disable` or a supplied verdict to bypass | INV-01 | Fixed signature; no bypass parameters; extra fields ignored/rejected; environment does not disable the gate; minimal public surface | `T-RISK-SEC-03..05/13/14/16` → TypeError/REJECTED; no mutation |
| T15 | Cash/NAV | Price/currency/fee/slippage | Binary float or currency mismatch makes an over-limit order pass | INV-01 | Decimal arithmetic; reject floats; explicit quantization; currency equality; fee/slippage in policy | `T-RISK-ACT-08..14`, `T-RISK-FND-09..12/16/24` → REJECTED |
| T16 | Portfolio limits | Quantity/price/position | Concentration > 20%, notional > 10%, or sell > holding | INV-01 | Deterministic pre/post-NAV formulas; execution price with slippage; holding check; fail closed on zero/negative NAV | `T-RISK-FND-01..12/17/22/23` → POLICY_REJECTED |

## Failure behaviour summary

- `REJECTED`: the proposal is well-formed enough to evaluate but violates a rule or
  fails identity/time checks. No ledger entry; no version increment.
- `REVIEW`: evidence is missing or unverifiable. This is a system state, not a
  trading decision; it is excluded from success-rate denominators.
- `BLOCKED`: the system cannot safely evaluate or commit (policy missing/inactive,
  portfolio invalid, audit/storage unavailable). No partial commit.
- `INCOMPLETE`: B's budget/deadline boundary stopped the run. Not owned by D and not
  counted as a risk-gate rejection.
- `HOLD`: a valid no-trade suggestion. `APPROVED` no-action; no ledger entry.

## Limitations

- A local administrator with write access to the SQLite file can alter it. This threat
  model does not claim protection against host compromise or a malicious DB admin.
- Hash chains detect accidental or internal tampering, not tail deletion or full-chain
  substitution without a trusted external reference.
- SQLite is a single-writer demo store, not a distributed ledger.
- The model may still be influenced by prompt injection in its own reasoning. The
  final defence is that the gate ignores free text and enforces INV-01.
- Secret protection covers fields the gate persists; it does not sanitize every
  upstream log. Export/log scanning remains a shared responsibility with E.

## Approval

Blank until a human reviewer records identity, date, commit SHA and conditions.
