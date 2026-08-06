# Formal runtime role split

The formal trial has three online responsibilities and no combined paper
credential:

- `tradingagents-ingest-v2` collects public evidence. It cannot read any paper
  run, decision, target, price, mark, artifact, NAV, or return. Its only formal
  database projection is an activation boolean and its collector configuration
  identity.
- `tradingagents-paper-decision` reads public evidence plus frozen run state and
  writes decision attempts, forecasts, targets, and the three decision artifact
  types. It cannot observe price receipts, interval assignments, marks, NAV, or
  returns.
- `tradingagents-paper-marker` reads frozen target intent and writes price
  captures, marks, and interval assignments. It cannot insert a decision or see
  LLM artifacts/forecasts. Its process must not receive an OpenAI, X, or other
  model credential.

Outcome analysis is not an online role. It runs offline only after the governed
60-session or 252-session outcome-access receipt exists. No long-lived analyzer
database URL belongs in a Fly worker.

The database role `schema_admin` is the stable `NOLOGIN`, `NOSUPER`,
`NOBYPASSRLS` owner of every protected table and privileged function. Runtime
logins must never inherit it. Forced RLS applies even to that owner; narrowly
scoped `formal_definer_select`, `formal_definer_insert`, and
`formal_definer_update` policies are the only paths needed by security-definer
functions. Migration 013 snapshots the complete policy catalog and refuses to
report ready if ownership, function bodies, security mode, search paths, ACLs,
role memberships, or policies drift.

## Online decision boundary

The decision worker validates two independent facts before a model call or a
write:

1. Its pinned XNYS calendar proves that `entry_date` is the next exchange
   session after `decision_date`.
2. `formal_decision_slot_projection(run_id, decision_date, entry_date)` proves
   that the requested date is the next outcome-free ledger slot, every prior
   decision has one exact bundle/target/eight-strategy/successful-attempt chain,
   every marker session is coherent, no terminal price-integrity failure exists,
   and the frozen horizon remains open.

The projection never returns interval indices, marks, prices, returns, NAV,
costs, or payloads. Initialization has no targets, marks, or assignments. After
initialization, the latest synchronized marker session pins the next decision
date. A missed decision is represented by the marker's normal carry-forward
row, so it consumes a holding interval and cannot silently extend the trial.
The last eligible target is built after 250 completed assignments; at 251 the
decision horizon is closed. The subsequent final marker interval completes the
252-interval outcome ledger without authorizing another target.

The only marker-derived values visible to the decision worker are the exact
eight held strategy weight vectors from one coherent latest marker session.
These are classified as point-in-time operational state because the frozen
turnover and portfolio-constraint arithmetic cannot be reproduced without
them. They are not outcome feedback: prices, returns, NAV, turnover, costs,
review artifacts, and aggregate efficacy remain withheld. Before the first
mark, all eight strategies receive explicit zero-weight vectors derived from
the frozen ticker universe.

## Health receipts

Decision and marker workers report `success`, `failure`, or `paused` through
`record_formal_runtime_heartbeat(run_id, event_type, runtime_build_id)`. The
caller cannot provide a role, protocol, timestamp, ID, or free-form details.
PostgreSQL derives those fields, verifies the exact authorized run/build pair,
canonicalizes the document, generates its content ID, and appends it. Direct
runtime access to the heartbeat table is denied, mutation is rejected by an
append-only trigger, and a `SET ROLE` session is refused.

The collector may call
`formal_runtime_latest_health_projection(protocol_id, collector_build_id)` only
for its exact authorized build. It sees one outcome-free row per component and
separate latest success, failure, and paused timestamps. Keeping those
timestamps separate prevents a newer pause from hiding a stale success or a
recent failure. The projection exposes no run identity, decision data, target,
price, mark, return, or payload.

## Activation sequence

1. Pause the collector and the legacy combined paper worker. Confirm that no
   fetch, decision, or price-capture receipt is still `running`.
2. Provision `tradingagents-paper-decision` and
   `tradingagents-paper-marker` as Fly MPG **Reader** users. Do not grant Writer,
   schema-admin, `BYPASSRLS`, role inheritance between them, or `CREATE` on
   `public`. Confirm the cluster already has the exact `schema_admin` base role
   described above; migration 013 fails closed if it does not.
3. Give each new Fly app only its own database URL. The decision app receives
   its model credential but no market-marker credential. The marker app receives
   its market-data configuration but no model or X credential.
4. Apply migrations through `013_formal_runtime_role_split.sql` as schema admin
   while every worker remains paused. Run each internally transactional file
   separately with `psql -X -v ON_ERROR_STOP=1 -f`; never concatenate migration
   files. Migration 013 enables and forces RLS;
   inherited MPG Reader access is intentionally not trusted as isolation.
5. Run the exact collector one-shot, restore the resulting backup, and use the
   repository's clone inspector to prove the migration-013 contract and zero
   preauthorization formal activity. Requiring stored decisions or marks here
   would contradict the database authorization gate.
6. Insert the one exact `formal_role_split_decommissions` receipt as schema
   admin. PostgreSQL derives its timestamp, verifies its content-addressed ID,
   revokes legacy DML and LLM reservation execution, and closes every legacy
   RLS policy in the same transaction. This receipt is append-only and is not a
   reversible switch. Build the matching `runtime_role_decommission` release
   payload with `runtime_role_decommission_release_payload()`; its
   `decommission_id` must equal the durable row exactly.
7. Scale the legacy paper app to zero and remove its database secret. Never put
   that credential in either replacement app. Confirm a direct login to each
   replacement returns the pinned, ready contract from
   `formal_role_split_preflight()`; `current_user` and `session_user` must both
   equal the expected login role. A `SET ROLE` session is not accepted.
8. Only after the split preflight, image/configuration receipts, restore
   rehearsal, and alert-delivery test all pass may schema admin insert the formal
   trial authorization. The database rejects authorization if the legacy receipt
   is absent, legacy mutation remains inherited, or any protected RLS policy has
   changed.

If rehearsal fails, restore another pre-authorization backup and repeat the
sequence. Do not delete or edit a decommission receipt, grant the legacy role
back, or repair a partially activated database in place.

After activation, routine operation should require no database editing. Workers
perform the role preflight, slot check, and heartbeat automatically. Operators
only respond to an alert, perform a release/restore ceremony, or authorize a
new preregistered trial. Never repair liveness by granting direct table access,
using `SET ROLE`, editing a heartbeat, or bypassing the frozen slot projection.
