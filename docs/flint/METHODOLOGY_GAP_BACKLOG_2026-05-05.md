# Methodology Gap Backlog

Date: 2026-05-05
Repository: `tradingagents-flint-shadow`

## Open Questions

1. Which news providers are trusted for issuer-specific claims?
2. What minimum evidence count is required for a bullish or bearish stance?
3. How do we classify a non-trading day for run semantics?
4. Which macro signals are mandatory for a buy recommendation?
5. Which judge result labels block Flint ingestion automatically?
6. Which source families are allowed to drive a final rating?
7. What telemetry is required for replay and audit?
8. Which claims may be stored as structured rationale versus discarded?
9. What target-profile fields must be mandatory for the recommendation contract?
10. Which external data sources are commercially redistributable?

## Implementation Targets

- run-scoped evidence storage
- source registry and claim graph
- deterministic factor model
- explicit judge layer
- investor-profile-aware recommendation contract
- source policy and macro context documentation
- replayable trace telemetry
