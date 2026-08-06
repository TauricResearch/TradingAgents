# ADR 0002: TargetPortfolio is the research-to-execution boundary

Status: accepted
Date: 2026-08-05

The architectural boundary is accepted; the current `schema_version=1` models remain an internal
compatibility contract until normalized schema export and a public versioning policy are added.

## Context

The current formal optimizer returns nested dictionaries whose meaning is understood by paper
storage and backtest code. A future broker order is not portable: supported order types, sessions,
fractional quantities, confirmations, and account restrictions differ by broker.

Creating broker orders in forecasting code would couple the research protocol to one account and
would grant an LLM-adjacent path unnecessary execution authority.

## Decision

Research and portfolio policy produce an immutable, versioned `TargetPortfolio`. It contains:

- opaque portfolio, run, strategy, protocol, instrument, forecast, and target identifiers;
- an explicit point-in-time `AsOf` boundary and effective time;
- a time-varying listing snapshot separated from opaque instrument identity;
- long-only weight allocations with an exact universe;
- constraints and allocation diagnostics; and
- producer and provenance references.

The current optimizer is exposed through an adapter. Explicit compatibility functions translate
between `TargetPortfolio` and the existing paper JSON without changing weights or diagnostics.
The formal target function now runs both the direct legacy optimizer and the canonical adapter,
fails closed on any difference, and returns only the canonical path's legacy-compatible payload.
No canonical object is persisted yet, so the database and artifact JSON remain unchanged.

A future deterministic order planner—not the forecast model—will combine a target with account
state, prices, execution policy, risk limits, and broker capabilities.
Quantity targets, shorts, leverage, and market-neutral semantics are intentionally deferred to a
later schema version with account, price, cash, and notional invariants.

## Invariants

- Duplicate or mismatched instruments fail validation.
- NaN/infinite weights fail validation.
- Weight targets plus cash sum to one and obey gross/position caps.
- Long-only targets cannot contain negative positions or cash.
- Timestamps are timezone-aware and normalized to UTC.
- Legacy serialization is lossless for the existing formal optimizer output.

## Consequences

- Broker adapters can evolve without entering the research domain.
- Existing ticker strings receive explicitly provisional opaque IDs until an instrument master is
  introduced; symbols are not claimed to be permanent identity.
- Embedding the 20-listing V2 snapshot is acceptable while targets are transient; introduce a
  content-addressed `UniverseSnapshotId` before persisting materially larger universes.
- The first slice adds no order submission, storage migration, or runtime flag.
