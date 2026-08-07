# Database migration policy

The numbered SQL files in this directory are an append-only history of schemas
that may already exist in deployed databases. They are not a description of the
current runtime architecture.

## Rules

1. Never delete, renumber, reorder, or rewrite an applied migration.
2. Add every schema change as the next forward-only numbered file.
3. Record an application receipt in the database or deployment log before a new
   runtime depends on the change.
4. Back up and test restoration before applying a destructive or hard-to-reverse
   change.
5. Pause database-writing jobs during a migration unless that migration has been
   designed and tested for concurrent writes.
6. Run migrations with a dedicated schema-administrator identity. Collector and
   research runtime identities must not own tables or hold DDL privileges.
7. Do not make an application container auto-migrate on startup.

These files are upgrades, not a standalone fresh-schema baseline. Migration
`001`, for example, expects tables created by the older `PaperStore` runtime. For
a fresh collector test database, use `scripts/prepare_collector_postgres.sh`,
which creates the supported collector base and applies only its required
integrity migrations. Reconstruct the retired full paper schema only from the
matching historical image or tag and then apply its migrations in numeric order.

For an existing installation, inspect its recorded migration state and apply
only later migrations exactly once. Do not infer state merely from whether a
table happens to exist.

## Retired architecture

Several migrations—especially `010` through `013`—encode governance, LLM-budget,
release-authorization, and three-runtime role controls from the retired formal
paper experiment. They remain here because deployed databases may contain those
objects and because changing historical SQL would destroy auditability.

The current design uses one collector plus explicit offline snapshot, decision,
label, and evaluation jobs. New code should not depend on the retired worker
split merely because its tables, roles, functions, or policies still appear in
these files. Remove obsolete deployed objects only through a new, reviewed
forward migration with an explicit rollback and data-retention plan.

## Development expectations

Migration tests should cover both an empty database and an upgrade from the
previous version. Tests should also verify ownership, grants, constraints,
append-only behavior, and rerun failure or idempotency as intended. Synthetic
fixtures belong in tests; production data and credentials do not belong in this
directory.
