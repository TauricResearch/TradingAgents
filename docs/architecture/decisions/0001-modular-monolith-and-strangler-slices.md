# ADR 0001: Modular monolith delivered through vertical strangler slices

Status: accepted
Date: 2026-08-05

## Context

The repository has working collector, research, portfolio, paper, deployment, and test behavior,
but several large modules mix orchestration, persistence, configuration, scheduling, and domain
logic. A broad package rewrite would collide with substantial current V2 changes and could fork
backtest and paper semantics.

The current setuptools configuration installs `tradingagents*` and `cli*`; independent top-level
application packages would not be included automatically.

## Decision

Keep one installable modular monolith. New code follows the inward dependency direction:

```text
domain <- ports <- application <- adapters/apps
```

Deliver it through one exercised vertical seam at a time. Every new boundary requires:

- a current caller or compatibility adapter;
- characterization and parity tests;
- an import-boundary test;
- no default runtime behavior change until parity is demonstrated; and
- an explicit removal condition for the legacy path.

Composition roots will initially live under `tradingagents/apps/`. We will not create empty
directories or interfaces merely to match the target diagram.

## Consequences

- Existing CLIs, Fly entrypoints, schemas, and the frozen V2 protocol remain stable during early
  extraction.
- Some legacy imports and global configuration remain temporarily.
- Architecture coverage grows as a ratchet instead of applying unachievable rules to all legacy
  modules immediately.
- Separate packages, services, and an external event bus require measured need and a later ADR.

## Rejected alternatives

- Big-bang rewrite: too much semantic and deployment risk.
- Immediate microservices: adds coordination and operations without current scale evidence.
- Full empty package skeleton: creates abstractions without proving useful contracts.
