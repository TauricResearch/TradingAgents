# Phase 3: China Public-Fund Mode

## Outcome

Resolve China public funds by six-digit code or name, retrieve traceable public
data, assess data trust, and produce fund-appropriate subscribe/hold/redeem/
convert guidance for trusted instruments.

## Scope

- China public-fund identity and share-class modeling.
- Search by exact/partial name and six-digit code.
- Public-provider adapters for profile, NAV history, current transaction status,
  approximate fee rules, manager, holdings/allocation, and benchmark metadata.
- Deterministic trust rules and field-level provenance.
- Active mixed/equity, index feeder, ETF feeder, and QDII coverage represented in
  the confirmed acceptance catalog.
- Single-fund operation guidance with short reasons.
- Special QDII timing and confidence rules.
- Platform-confirmed conversion support.

## Non-Goals

- Brokerage/sales-platform login or order execution.
- Guaranteed complete data for every public fund.
- Point-in-time historical holdings unless a provider supplies dated disclosures.
- Portfolio-wide allocation and transaction ledger; those are Phase 4.
- Commercial data licensing or a paid-data dependency.

## Mandatory Provider Technical Spike

Do not select a provider by popularity or by one successful sample. The first
development slice builds a disposable probe and evaluates candidate public
sources, including open-source public-fund adapters and official manager/
disclosure pages where available.

The probe must test every acceptance-catalog code and record:

```text
identity and share class
latest NAV and NAV date
NAV history range
subscription/redemption status and observation time
fee/holding-period rules
manager/profile
latest holdings/allocation and disclosure date
benchmark name/code
QDII classification
rate limits, encoding, response stability, and terms/reference
```

Provider selection criteria, in order:

1. correct identity and date semantics;
2. traceable source/disclosure references;
3. current transaction status;
4. deterministic historical NAV retrieval;
5. coverage of the acceptance catalog;
6. stable access and maintainable normalization;
7. holdings/manager/fee completeness.

The spike output is a checked-in provider matrix with no secrets or full copied
payloads. Provider-specific endpoint details remain inside adapters.

The implementation record is [PHASE_3_PROVIDER_MATRIX.md](PHASE_3_PROVIDER_MATRIX.md).

## Provider Architecture

Use capability-based adapters rather than one giant provider class:

```text
FundIdentityProvider
FundNavProvider
FundTransactionStatusProvider
FundFeeProvider
FundDisclosureProvider
FundBenchmarkProvider
```

A provider registry selects an ordered chain for each capability. Normalization
returns evidence fields from DOMAIN_AND_TRUST.md. One capability may degrade
without discarding the others.

Cache rules are capability-specific. Transaction status uses a short cache;
historical NAV and dated disclosures may use immutable/content-addressed cache.
Never reuse a provider response without its original effective date.

## Fund Identity Model

Extend fund subtypes without conflating investment strategy and transaction form:

```text
vehicle_type: open_end | etf_feeder | index_feeder | lof | other
strategy_type: active_equity | active_mixed | index | bond | money | fof | other
market_scope: mainland | hong_kong | global | qdii
share_class: A | C | other
parent_product_id: nullable
```

Marketing sector labels such as AI, communications, or high-end equipment are
tags/exposures, not vehicle types.

Identity resolution rules:

- Exact six-digit code wins over name search.
- Name search returns candidates and never silently selects an ambiguous match.
- A/C share classes remain distinct instruments.
- The resolver returns Chinese display name, code, parent product when known,
  types/tags, currency, status, evidence, and warnings.
- A stale/ambiguous identity blocks analysis and advice.

## China Fund Snapshot

Normalized snapshot groups:

```text
identity
profile
nav_history
transaction_status
fees
manager
holdings
sector_allocation
asset_allocation
benchmark
trust_assessment
warnings
```

All dates remain explicit. For historical analysis, NAV is cut off at
`analysis_date`; profile/status/fees/manager/holdings are labeled with their real
latest dates.

## Trust and Action Gate

Research may proceed with partial data. An executable operation requires the
action-specific critical fields in DOMAIN_AND_TRUST.md.

Initial policy:

- Domestic NAV no more than two relevant trading days behind.
- Subscription/redemption status observed on the current local day.
- QDII NAV may lag up to the configured QDII threshold, initially five relevant
  trading days; the report explains the lag.
- Holdings use the latest published reporting period and never pretend to be
  current-day holdings.
- Missing holdings lowers confidence but does not alone block subscribe/hold.
- Unknown purchase/redemption availability blocks the affected action.
- A user trust override can request research but cannot create an executable
  proposal.

Trust reason codes must be stable and testable, for example:

```text
IDENTITY_AMBIGUOUS
NAV_STALE
NAV_MISSING
TRANSACTION_STATUS_STALE
SUBSCRIPTION_CLOSED
REDEMPTION_CLOSED
FEE_RULE_UNKNOWN
HOLDINGS_DISCLOSURE_OLD
BENCHMARK_UNAVAILABLE
QDII_DATA_LAG
```

## Single-Fund Operation Logic

The deterministic layer first limits available actions. The analysis team then
chooses among allowed actions and produces a short reason.

Off-exchange actions:

- `subscribe`: propose a currency amount, not exact units;
- `hold`: no transaction, optionally list re-evaluation triggers;
- `redeem_partial`: propose percentage of confirmed units;
- `redeem_all`: only when minimum-holding/fee constraints are sufficiently known;
- `convert`: only with explicit platform support/evidence, otherwise represent as
  redeem plus subscribe.

The result includes confidence, executable/observation-only state, supporting
and opposing evidence, data warnings, expected evaluation horizon, and relevant
friction. Fees are approximate decision inputs, not accounting-grade outputs.

## Benchmark Policy

Prefer the fund's disclosed performance comparison benchmark or tracked index.
Store benchmark text and machine-usable components separately when possible.
Allow user override and preserve both original and selected benchmark.

Do not use one universal benchmark for AI funds, active mixed funds, Nasdaq QDII,
and Hang Seng technology funds. If a benchmark cannot be converted to a price
series, disclose that relative metrics are unavailable rather than choosing one
with the LLM.

## QDII Policy

QDII analysis additionally records:

- NAV publication lag;
- overseas market/calendar cutoff;
- valuation currency and FX context;
- subscription limits or suspension when available;
- target-market benchmark; and
- whether the apparent latest move is already reflected in published NAV.

QDII advice must not imply a known execution NAV. Missing or stale status lowers
the result to observation-only.

## Confirmed Acceptance Catalog

Every code below must resolve by code and by sufficiently specific name. Data
coverage may vary. Only instruments passing the trust gate may receive an
executable operation recommendation.

| Sector | Fund name | Code |
| --- | --- | --- |
| Technology / AI | 融通科技臻选混合C | `026539` |
| Technology / AI | 东方人工智能主题混合C | `017811` |
| Technology / AI | 博时科技驱动混合C | `021383` |
| Technology / AI | 平安科技精选混合C | `026211` |
| Technology / AI | 广发远见智选混合C | `016874` |
| Technology / AI | 易方达人工智能ETF联接C | `012734` |
| Technology / AI | 中欧上证科创板人工智能指数C | `026790` |
| Technology / AI | 中欧中证芯片产业指数C | `020483` |
| Communications | 国联安优选行业混合 | `257070` |
| Communications | 天弘中证全指通信设备指数C | `020900` |
| Manufacturing / Equipment | 永赢高端装备智选混合C | `015790` |
| Balanced / Multi-strategy | 国泰融安多策略灵活配置混合A | `003516` |
| US / QDII | 南方纳斯达克100指数(QDII)C | `016453` |
| US / QDII | 华安纳斯达克100ETF联接(QDII)A | `040046` |
| US / QDII | 广发全球精选股票(QDII)C | `021277` |
| US / QDII | 摩根纳斯达克100指数(QDII)A | `019172` |
| US / QDII | 易方达全球成长精选混合(QDII)A | `012920` |
| US / QDII | 易方达全球成长精选混合(QDII)C | `012922` |
| US / QDII | 建信新兴市场优选混合(QDII)C | `018147` |
| Hong Kong Technology | 汇添富恒生科技ETF联接(QDII)A | `013127` |

## API Changes

```text
GET  /api/funds/search?q=
POST /api/funds/resolve
GET  /api/funds/{code}
GET  /api/funds/{code}/snapshot?analysis_date=
GET  /api/funds/{code}/trust
GET  /api/funds/{code}/sources
POST /api/funds/{code}/evaluate
POST /api/funds/{code}/conversion-check
```

`evaluate` accepts intended action context, optional amount/units, sales platform,
and analysis settings. It returns allowed actions, blocked actions with reasons,
trust, and the formal advice version when eligible.

## UI Changes

- Search by Chinese name or six-digit code with candidate disambiguation.
- Fund identity header with share class, strategy, vehicle, and QDII marker.
- NAV chart and benchmark comparison with explicit cutoff dates.
- Current transaction-status panel and freshness timestamp.
- Data-source/trust drawer with blocking and non-blocking reason codes.
- Fund-specific operation result using subscribe/redeem/convert vocabulary.
- QDII lag/market-time panel.
- Observation-only state that visibly disables transaction-list export.
- Conversion availability input for the user's sales platform.

## Implementation Slices

1. Provider probe and checked-in capability/coverage matrix.
2. China fund identity/share-class model and search index.
3. NAV provider, historical cutoff, caching, and deterministic metrics.
4. Transaction status and fee capability with trust rules.
5. Manager/holdings/allocation/disclosure capability.
6. Benchmark resolution and QDII calendar/lag rules.
7. Fund action eligibility and asset-aware agent prompts.
8. API/UI search, snapshot, trust, sources, and operation advice.
9. Acceptance-catalog live validation and provider-failure hardening.

## Test Plan

- Exact code and name resolution for all acceptance entries using recorded,
  license-safe fixtures or synthetic equivalents.
- Ambiguous names require selection.
- A/C share classes never merge accidentally.
- NAV future observations excluded from historical analysis.
- Domestic and QDII freshness thresholds.
- Closed/unknown subscription or redemption blocks the action.
- Missing holdings warns but does not fabricate values.
- Conversion requires platform support.
- Benchmark selected from evidence, not LLM invention.
- QDII cutoff, lag, FX context, and holiday cases.
- Provider field-group failure preserves other groups.
- Cache retains original evidence dates and raw hash.
- No CI test depends on the live public endpoint.

## Definition of Done

- All 20 acceptance funds resolve by code and unambiguous name in a live manual
  validation run.
- Each result displays data coverage, provenance, freshness, and trust reasons.
- At least one representative active fund, feeder/index fund, and QDII fund
  completes a trusted live analysis when public data permits.
- Insufficient data produces observation-only research, never invented values or
  an executable trade list.
- Subscribe/redeem/convert semantics and QDII rules are enforced.
- Provider changes fail per capability and do not crash unrelated analysis.
- Backend/frontend deterministic suites and opt-in live smoke matrix pass.
