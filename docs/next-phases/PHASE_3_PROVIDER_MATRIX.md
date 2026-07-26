# Phase 3 Public Provider Matrix

This is the mandatory Phase 3 provider spike record. It records normalized
capabilities and failure boundaries only. It does not retain full provider
payloads, private conversations, credentials, or live fund observations.

## Selected Adapter

| Candidate | Selection | Reason | Scope |
| --- | --- | --- | --- |
| Eastmoney public fund pages | Selected | It exposes code search, dated NAV history, purchase/redemption labels, fund profile, approximate fees, disclosed benchmark text, manager, and allocation fields in one public source. | Live local mode |
| Synthetic Phase 3 fixture | Test/demo only | Covers every acceptance-catalog share class with deterministic evidence, dates, and partial-failure cases. | CI, tests, local demo |
| A second public provider | Deferred | Multiple-provider selection is not needed for the validated Phase 3 boundary and would broaden the provider surface. | Not implemented |

The adapter confines endpoint parsing to `tradingagents/china_funds/eastmoney.py`.
No application code rotates proxies, disguises user agents, or retries a provider
request indefinitely. Requests have a bounded timeout. HTTP 429 and timeout
signals remain provider failures; capability failures do not discard data from
unrelated capability groups.

## Capability Matrix

| Capability | Eastmoney public adapter | Normalized output | Cache policy | Trust consequence |
| --- | --- | --- | --- |
| Identity/share class | Code search | Code, display name, manager/company when exposed | 30 days | Ambiguous/unverified identity blocks operation |
| NAV history | `pingzhongdata` trend series | Dated NAV points, cut off at `analysis_date` | 6 hours per code/cutoff | Domestic lag >2 relevant trading days or QDII lag >5 blocks operation |
| Transaction status | Fund list status data | Subscription/redemption labels and observation time | 5 minutes | Missing, expired, or not-current-day status blocks affected action |
| Fees | Trend/profile fields | Approximate subscribe/redeem rules with warnings | 7 days | Unknown fee/holding rule blocks affected redemption |
| Manager/disclosure | Trend/profile fields | Manager and allocation; unavailable holdings remain missing | 7 days | Missing holdings lowers confidence only |
| Benchmark | Fund profile | Disclosed text and tracked-index name where exposed | 30 days | Missing benchmark blocks relative metrics, not fund-only research |
| QDII context | Catalog classification plus NAV/status data | NAV lag, date cutoff, currency, unknown market-move reflection | Derived, not separately cached | UI must state published NAV is not an execution NAV |

`provider_cache` stores only normalized JSON, source reference, original
retrieval/effective/expiry times, and a normalized-content hash. It never stores
the raw Eastmoney response. A cache hit retains original evidence timestamps. An
expired cache can support observation-only research only when a fresh provider
attempt fails; it is explicitly marked stale and cannot satisfy the identity,
NAV, or current transaction-status execution gate.

## Validation Boundary

- The acceptance catalog has 20 checked-in code/name fixtures. CI validates code
  resolution, unambiguous name resolution, A/C separation, QDII context, and
  provider capability degradation without a real network call.
- Live validation is manual and opt-in because public provider availability,
  terms, throttling, and coverage may change. A live failure is recorded as a
  provider limitation, never converted into an invented fund value.
- The deterministic market calendar includes Shanghai Stock Exchange published
  2025-2026 closures and uses a weekday fallback outside that published range.
  QDII overseas-market holidays remain an explicit provider/data limitation; the
  app therefore does not claim to know whether an intraday overseas move is in
  the next published NAV.

Run the bounded manual matrix with:

```bash
python scripts/probe_china_funds.py --analysis-date YYYY-MM-DD --timeout 8
```

The command makes at most four public requests per acceptance code in one
process, reuses only in-memory responses for the remaining capability parsers,
and prints no provider payloads.

## Live Probe Record

A bounded live run on 2026-07-25 covered all 20 acceptance-catalog codes with
an eight-second per-request timeout, no retry loop, and no credentials. All 20
returned identity, dated NAV history, current transaction labels, manager,
asset allocation, approximate fee data, and disclosed benchmark text without a
capability exception. NAV history lengths ranged from 46 to 3,672 normalized
points; the latest effective dates were 2026-07-22 or 2026-07-23, including the
expected QDII publication lag.

The same run returned no normalized holding rows for any acceptance code.
Holdings coverage is therefore an unresolved provider limitation. The adapter
keeps holdings unavailable and the trust layer adds `HOLDINGS_UNAVAILABLE`; it
does not infer constituents from a fund name, benchmark, or allocation chart.
This result records reachability at the observation time, not a promise of
future provider availability.
