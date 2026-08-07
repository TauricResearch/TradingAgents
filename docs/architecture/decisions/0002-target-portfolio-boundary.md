# ADR 0002: TargetPortfolio is the research-to-execution boundary

Status: accepted
Date: 2026-08-05

The architectural boundary remains accepted. Implementation note (2026-08-06): the unused legacy
paper-JSON compatibility path described in the original slice was removed with the permanent paper
workers. The offline decision runner currently persists validated target weights; it has not yet
been wired through the canonical `TargetPortfolio` port.

## Context

The optimizer returns nested dictionaries whose meaning is understood by research and backtest
code. A future broker order is not portable: supported order types, sessions,
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

The initial compatibility adapter proved parity with the optimizer but had no remaining caller
after the paper runtime was retired, so it was removed. A later execution slice should make the
canonical `TargetPortfolio` the persisted output of the active offline allocator directly, with
one adapter contract rather than another dual path.

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
- Any future adapter must prove lossless serialization for the active optimizer output.

## Consequences

- Broker adapters can evolve without entering the research domain.
- Existing ticker strings receive explicitly provisional opaque IDs until an instrument master is
  introduced; symbols are not claimed to be permanent identity.
- Embedding the 20-listing V2 snapshot is acceptable while targets are transient; introduce a
  content-addressed `UniverseSnapshotId` before persisting materially larger universes.
- The first slice adds no order submission, storage migration, or runtime flag.
