# Three-runtime formal trial production runbook

This runbook governs the `global-event-v2` forward **paper** experiment. It
does not authorize brokerage connectivity, order submission, or real-money
trading. Production has three online runtimes and no combined paper worker:

| Responsibility | Fly app | Process | PostgreSQL login | Pause switch |
| --- | --- | --- | --- | --- |
| Public evidence collection | `tradagent` | `--formal-collector` | `tradingagents-ingest-v2` | `MEDIA_COLLECTION_ENABLED=false` |
| Outcome-blind decisions | `tradagent-paper-decision` | `decision-daemon` | `tradingagents-paper-decision` | `PAPER_DECISIONS_ENABLED=false` |
| Price capture and marking | `tradagent-paper-marker` | `marker-daemon` | `tradingagents-paper-marker` | `PAPER_MARKS_ENABLED=false` |

The retired `tradagent-paper` app, `fly.paper.toml`, `tradingagents-paper`
database login, and `--component paper` CLI value are not production runtime
surfaces. Keep the old app scaled to zero and remove its database secret. The
one durable role-decommission receipt closes its transitional database policies
irreversibly during formal release.

Outcome analysis is offline. No long-lived analyzer or schema-administrator
database URL belongs in any Fly worker.

## Non-negotiable safety rules

- Deploy and inspect all three apps with their own pause switch explicitly
  false. An enable switch is an emergency/runnable-state control; it is never
  authority to start the trial.
- Set both `MEDIA_AUTO_MIGRATE=false` and, in each paper app,
  `PAPER_AUTO_MIGRATE=false`. Runtime identities must never apply migrations.
- Give each app only its exact database login. `current_user` and
  `session_user` must both equal that login; `SET ROLE` is rejected.
- Give the decision app only its configured model-provider credential. Give the
  marker app no X, OpenAI, Anthropic, Google, or other model credential. Give
  the collector no model credential. All three may receive the alert webhook.
- Never copy a generated database URI into a ticket, shell history, artifact,
  or runbook. Store only content IDs, build IDs, full image digests, opaque
  control-plane fingerprints, and validated redacted receipts.
- Never insert, update, copy, or delete evidence, decisions, targets, price
  captures, marks, heartbeats, release receipts, or review artifacts to clear a
  gate. Start a new governed run when semantics materially change.
- A missing or unconfirmed `TRADINGAGENTS_ALERT_WEBHOOK_URL` is an activation
  blocker.
- Require exactly one non-destroyed Fly Machine for each runtime. A second
  Machine is not harmless redundancy: it violates the serialized formal
  runtime contract.

## Two different preflight concepts

Do not interchange these gates.

1. **Preauthorization release material** proves the exact paused image,
   non-secret configuration, credential scope, build identity, and executable
   semantics. It runs before formal authorization and performs zero database or
   provider calls. The three release-material commands below produce this
   evidence.
2. **Postauthorization activation preflight** is the read-only
   `tradingagents-ops preflight` command. It authenticates the real database
   login, migration-013 role/RLS contract, durable image/configuration
   authorization, and runtime-specific operational state. It cannot pass
   before formal release exists. It still requires all activity switches to be
   false.

The collector activation preflight also requires fresh, separate `paused`
heartbeats from the authorized decision and marker images. A paused event never
hides a failure unless a strictly newer success exists. The decision preflight
checks the current safe decision window and exact evidence coverage. The marker
preflight intentionally does not read decision coverage or outcome data.

## Release overview

Use this order for a first release or any release that changes an image,
dependency, formal configuration, protocol, or executable semantics:

1. Freeze changes, pause every runtime, back up production, and verify a
   disposable restore.
2. Provision the exact split logins and apply every pending migration through
   `013_formal_runtime_role_split.sql` as schema administrator.
3. Deploy exactly one paused Machine for each of the three final images.
4. Capture preauthorization runtime material and Fly Machine inventories.
5. Keep the collector daemon paused and run its explicit one-shot release
   rehearsal to persist one exact final-image collection cycle.
6. Take a new backup containing that cycle; restore it to a fresh isolated
   cluster and produce the governed empty-trial restore receipt.
7. Test the alert route from all three exact images and capture the three exact
   runtime receipts; the release command builds their aggregate.
8. Plan the formal release locally, review only its safe content identifiers,
   then execute it once as schema administrator.
9. Wait for fresh paused decision and marker heartbeats and run all three
   postauthorization activation preflights.
10. Enable collector first, marker second, and decision last.

Any image or formal configuration change after steps 4–7 invalidates their
evidence. Repeat from the final paused deployment; do not reuse old receipts.

## 1. Pause, backup, and migration

Pause `tradagent`, `tradagent-paper-decision`, and
`tradagent-paper-marker`. If the legacy app still exists, pause and scale it to
zero. Confirm there are no `running` fetch receipts or collection cycles and no
decision or price-capture operation in progress before schema work.

Take a fresh production backup and restore it to an isolated disposable
cluster. Record opaque fingerprints and completion times, not connection
material. A backup existing in the control plane is not sufficient; the
restore must be proven readable before migration begins.

Apply only pending migrations, in numeric order, through:

```text
001_formal_experiment_roles.sql
002_ingest_identity_rotation.sql
003_formal_source_integrity.sql
004_formal_itt_provenance.sql
005_formal_primary_run_registry.sql
006_atomic_fetch_lineage.sql
007_collection_cycles.sql
008_formal_price_capture_integrity.sql
009_server_observed_evidence.sql
010_formal_artifact_governance.sql
011_formal_llm_budget_and_attempt_binding.sql
012_formal_release_authorization.sql
013_formal_runtime_role_split.sql
```

Every migration contains its own `BEGIN`/`COMMIT` boundary. Invoke each file
separately with `psql -X -v ON_ERROR_STOP=1 -f`; do not concatenate, combine,
skip, or reorder files. A statement failure rolls back that migration before
the next file can begin. Migration 004 may take an exclusive lock when upgrading
legacy `float4` columns. Migrations 006, 007, and 009 fail if a fetch/cycle is
still running. Migration 008 refuses to reinterpret existing formal marks whose
provider vintage was not captured. Migration 013 requires the split Reader
users to exist and requires zero prior formal authorization rows.

The expected migration head is exactly
`013_formal_runtime_role_split.sql`. Verify its functions, normalized body
hashes, owners, ACLs, forced-RLS policies, and role memberships before ending
the maintenance window. A similarly named trigger or function is not adequate.

The schema administrator is `tradingagents-app-v2` (a direct member of the
stable `schema_admin` role). Its DSN must be absent from all runtime apps. An
authenticated maintainer can enter the existing production cluster without
copying a password:

```sh
fly mpg connect <production-cluster-id> \
  --username tradingagents-app-v2 --database fly-db
```

Fly MPG configures this login with the stable owner role as its default, so the
expected administrator identity may be `current_user=schema_admin` with
`session_user=tradingagents-app-v2`. Release and clone-inspection code accepts
only that exact Fly split (or a direct session where both identities match) and
requires both identities to be members of `schema_admin`. Runtime identities
remain stricter: their `current_user` and `session_user` must be identical.

## 2. Configure least-privilege credentials

Create `tradingagents-paper-decision` and `tradingagents-paper-marker` as Fly
MPG **Reader** users before migration 013. Do not grant Writer, schema admin,
`BYPASSRLS`, `CREATE` on `public`, or membership between runtime roles. Reader's
broad inherited reads are constrained by forced RLS; migration 013's exact
policy catalog is the security boundary.

The runtime secret allocation is exact:

| App | Required secret classes | Forbidden secret classes |
| --- | --- | --- |
| `tradagent` | ingest-v2 `MEDIA_DB_URL`, `X_BEARER_TOKEN`, alert webhook | paper-role URLs, all model-provider keys |
| `tradagent-paper-decision` | decision-role `MEDIA_DB_URL`, exact configured model key, alert webhook | X key, marker URL, extra provider keys |
| `tradagent-paper-marker` | marker-role `MEDIA_DB_URL`, alert webhook | X key and every model-provider key |

Do not also set legacy `DATABASE_URL`. The formal configuration validator
rejects missing, extra, or cross-role credential names before database or
provider access.

`fly mpg attach` may print a complete URI. Keep shell tracing and terminal
recording disabled and redirect both stdout and stderr to an access-controlled
temporary file or an approved secret-import workflow. Delete that temporary
material as soon as the Fly secret is installed. Never paste the URI into
`fly secrets set` interactively.

## 3. Deploy the final images paused

Deploy only the checked-in split configurations:

```sh
fly deploy -c fly.toml
fly deploy -c fly.paper.decision.toml
fly deploy -c fly.paper.marker.toml
```

Confirm the effective non-secret settings include:

```text
tradagent:                  MEDIA_COLLECTION_ENABLED=false
tradagent-paper-decision:   PAPER_DECISIONS_ENABLED=false
tradagent-paper-marker:     PAPER_MARKS_ENABLED=false
all:                        MEDIA_AUTO_MIGRATE=false
both paper apps:            PAPER_AUTO_MIGRATE=false
```

Confirm each app has exactly one non-destroyed Machine and the expected process
from the table at the top of this runbook. Do not deploy `fly.paper.toml`.
The paused collector intentionally remains in a sleep-only control loop so its
exact Machine stays reachable by SSH. That loop performs no database or
provider call; a clean exit would leave an `on-failure` Machine stopped and
make the evidence ceremony impossible.

## 4. Capture preauthorization release evidence

Run these inside the three paused final images. They validate configuration and
credential scope but make no database, X, news, market-data, or model call:

```sh
mkdir -p .context/release

fly ssh console -a tradagent \
  -C "/opt/venv/bin/tradingagents-poller --formal-collector --release-material" \
  > .context/release/collector-material.json

fly ssh console -a tradagent-paper-decision \
  -C "/opt/venv/bin/tradingagents-paper decision-release-material" \
  > .context/release/paper-decision-material.json

fly ssh console -a tradagent-paper-marker \
  -C "/opt/venv/bin/tradingagents-paper marker-release-material" \
  > .context/release/paper-marker-material.json
```

The decision material requires its exact configured provider credential name
but does not contact the provider. Marker material must succeed with no model
credential. Save the Fly control-plane inventories separately:

```sh
fly machines list -a tradagent --json \
  > .context/release/collector-machines.json
fly machines list -a tradagent-paper-decision --json \
  > .context/release/paper-decision-machines.json
fly machines list -a tradagent-paper-marker --json \
  > .context/release/paper-marker-machines.json
```

Keep `.context/release` out of version control. The release planner rejects a
non-deployment image tag, a partial digest, a mismatched app, or anything other
than one current Machine per app. Do not edit generated JSON.

## 5. Run the final-image collector rehearsal

Authorization does not gate public evidence collection, but a daemon enable is
unnecessary for the release ceremony. Keep all three daemon switches false and
run the collector's explicit one-shot command inside the exact paused image:

```sh
fly ssh console -a tradagent \
  -C "/opt/venv/bin/tradingagents-poller --formal-collector --release-rehearsal" \
  > .context/release/collector-rehearsal.json
```

This controlled command runs the real ten broad-news requests and the same
bounded X trend/discovery/search children as normal collection while the daemon
switch remains false. It must complete a content-bound cycle under the released
build. Exact slots, server-observed timestamps, raw-content identities, and
fetch-lineage pairs come from the database lifecycle. Do not synthesize a
success, reuse a historical receipt, reduce the topic set, or backdate a cycle.

The command fails unless all ten broad-news slots each contain at least one
eligible raw-content lineage item. X trend, discovery, or search slots may be a
genuine observed empty response, but may not be missing or failed. All three
release-bound images remain unchanged and paused until authorization.

### Evidence coverage contract

The formal protocol collects general company-relevant and global events—not
ticker searches, issuer feeds, or company-authored promotion. Its frozen broad
themes cover technology/model launches, geopolitics, macro policy and major
global developments. Independent editorial publisher/host pairs are checked at
collection and again at forecast selection.

Every exact `(provider, query_key)` slot is mandatory. Each broad-news slot must
have nonempty independent-editorial raw lineage; only the protocol's explicit
X/discovery provider set may record a genuine observed empty response. Every
slot still needs a completed, fresh, server-observed receipt. Formal prompts
cap `globalnews` at 80 rows and X at 20 rows.
`trendnews` may rank bounded X topics during collection but is never formal
forecast evidence. Company-authored material is excluded at both boundaries.

Changing themes, slots, sources, limits, editorial allowlists, or collector
semantics is a new protocol/release—not an incident workaround.

## 6. Restored-clone rehearsal

Take a new backup only after the final-image collection cycle is terminal.
Restore it to a fresh isolated disposable cluster; an earlier backup does not
qualify. The governed restore receipt must bind, in order:

- the production-cluster, backup, and distinct restored-cluster fingerprints;
- the exact final collection-cycle manifest from the immutable database row;
- migration head `013_formal_runtime_role_split.sql` and the exact role-contract
  ID; and
- zero formal trial activity rows for the configured confirmatory run, with a
  database-observed verification time and `external_calls=0`.

Use a clone-specific direct schema-administrator identity only for this
short-lived inspection; never put it in a Fly worker. Set its URL only in the
local environment, then let the repository inspect the clone and build the
receipt:

```sh
export TRADINGAGENTS_RESTORE_DB_URL='postgresql://...restored-clone...'

tradingagents-ops build-restore-rehearsal \
  --collector-rehearsal .context/release/collector-rehearsal.json \
  --paper-decision-material .context/release/paper-decision-material.json \
  --source-cluster-fingerprint "$SOURCE_CLUSTER_FINGERPRINT" \
  --restored-cluster-fingerprint "$RESTORED_CLUSTER_FINGERPRINT" \
  --backup-fingerprint "$BACKUP_FINGERPRINT" \
  --backup-completed-utc "$BACKUP_COMPLETED_UTC" \
  > .context/release/restore-rehearsal.json

unset TRADINGAGENTS_RESTORE_DB_URL
```

The command authenticates a direct non-superuser schema-admin session, verifies
the migration-013 role contract, reads the exact collector cycle from the
restored database, and counts every governed formal-activity table. Any prior
decision, forecast, target, price capture, mark, attempt, artifact, or
nonconfirmatory label blocks release. Do not handcraft or repair its JSON.

This empty-state rule is deliberate. The database forbids formal decisions and
marks before authorization, so requiring a stored preauthorization decision or
mark would be circular and impossible on a clean first release. Exact image,
configuration, semantic, PostgreSQL integration, and deterministic replay
tests are release/CI contracts; stored marker replay becomes an offline audit
only after real intervals exist.

After saving and validating the non-secret receipt:

1. Confirm no clone command is running.
2. Remove every clone-only Fly secret or attachment and wait for deployment to
   finish.
3. Confirm only production secret **names** remain; never print values.
4. Destroy the disposable clone and confirm billing stopped.

Never destroy production, run rehearsal against production `MEDIA_DB_URL`, or
destroy a clone while an app still has its URL.

## 7. Alert-delivery evidence

With all three apps still paused, test the same configured route from each
image:

```sh
mkdir -p .context/release
fly ssh console -a tradagent \
  -C "/opt/venv/bin/tradingagents-ops alert-test --component collector --json" \
  > .context/release/collector-alert.json
fly ssh console -a tradagent-paper-decision \
  -C "/opt/venv/bin/tradingagents-ops alert-test --component paper-decision --json" \
  > .context/release/paper-decision-alert.json
fly ssh console -a tradagent-paper-marker \
  -C "/opt/venv/bin/tradingagents-ops alert-test --component paper-marker --json" \
  > .context/release/paper-marker-alert.json
```

Transport success alone is insufficient. Confirm that all three messages
arrived at the intended destination with the exact component labels. A
successful JSON command emits a content-addressed receipt tied to that image's
build and component configuration; it never emits the webhook URL. The release
command below validates the three files, requires one full route fingerprint,
enforces recency, and builds the exact aggregate. Do not hand-edit a receipt.

## 8. Plan and execute formal release

First run a dry plan. It validates bounded duplicate-key-safe JSON, exact
component configurations, Fly tags/digests, restore evidence, alert evidence,
protocol identities, and cross-image outcome semantics. It makes no database
writes and prints only safe content identifiers:

```sh
tradingagents-ops formal-release \
  --collector-material .context/release/collector-material.json \
  --paper-decision-material .context/release/paper-decision-material.json \
  --paper-marker-material .context/release/paper-marker-material.json \
  --collector-machines .context/release/collector-machines.json \
  --paper-decision-machines .context/release/paper-decision-machines.json \
  --paper-marker-machines .context/release/paper-marker-machines.json \
  --restore-rehearsal .context/release/restore-rehearsal.json \
  --collector-alert .context/release/collector-alert.json \
  --paper-decision-alert .context/release/paper-decision-alert.json \
  --paper-marker-alert .context/release/paper-marker-alert.json
```

Require `status=planned` and `database_writes=false`. Review the protocol,
registration, configuration, build, preflight, receipt, decommission, and
authorization IDs. Do not continue if any ID or image differs from the reviewed
change record.

Then expose `TRADINGAGENTS_ADMIN_DB_URL` only to this short-lived local admin
process and rerun the identical command with `--execute`. The execute path first
performs the idempotent append-only trial bootstrap, then commits the legacy
role decommission, complete release-receipt set, and sole authorization in one
locked transaction. It refuses a non-PostgreSQL URL, indirect/`SET ROLE`
authority, partial prior state, or evidence drift. A safe successful result is
`status=released`; an exact idempotent retry is `status=already_released`.

Unset the admin URL immediately afterward. It must never be installed on a
runtime app.

## 9. Postauthorization activation preflights

Leave every switch false. The decision and marker daemons can now authenticate
their exact authorization and append `paused` heartbeat events. Wait for one
fresh paused event from each; do not insert heartbeats manually.

Run the checks after the collection cutoff and before the next XNYS open so the
collector and decision data-window gates are meaningful:

```sh
fly ssh console -a tradagent \
  -C "/opt/venv/bin/tradingagents-ops preflight --component collector --json"
fly ssh console -a tradagent-paper-decision \
  -C "/opt/venv/bin/tradingagents-ops preflight --component paper-decision --json"
fly ssh console -a tradagent-paper-marker \
  -C "/opt/venv/bin/tradingagents-ops preflight --component paper-marker --json"
```

Require `runtime_ready=true` for all three. Among other checks, this proves:

- exact explicit pause and migration settings, build identity, credential
  scope, retry envelope, and content-addressed component configuration;
- a direct exact PostgreSQL login with no schema/database creation authority;
- migration-013 legacy decommission, ACL, role membership, forced-RLS, policy,
  owner, trigger, and function-body contract on the same connection used to
  read authorization;
- the sole exact primary run and durable image/configuration/outcome binding;
- collector heartbeat freshness and separate fresh failure-free paused
  decision/marker health; and
- for collector/decision, the safe window and immutable cutoff-cycle receipt
  coverage.

The preflight always opens the store with automatic migration explicitly
disabled. Failures redact connection/provider details. A result from the old
`paper` component, a different app, a different build, or a different window is
not substitutable.

## 10. Activate in dependency order

After all three preflights pass without rebuilding or changing formal
configuration:

1. Enable `MEDIA_COLLECTION_ENABLED=true` on `tradagent`.
2. Confirm its next natural collection/heartbeat is healthy.
3. Enable `PAPER_MARKS_ENABLED=true` on `tradagent-paper-marker`.
4. Confirm marker authentication and liveness. A mark occurs only when a frozen
   target is due in its bounded post-open window.
5. Enable `PAPER_DECISIONS_ENABLED=true` on
   `tradagent-paper-decision` as the final state change.
6. Monitor the next scheduled cycle through redacted logs, alerts, and
   append-only health/status projections. Do not use the decision credential to
   inspect marks, NAV, prices, or returns.

If any gate changes between preflight and activation, pause and repeat the
affected evidence/release ceremony. An enable flag cannot override a missing or
mismatched durable authorization.

## Incident response and rollback

For an unhealthy activation or decision-side incident, immediately return
`PAPER_DECISIONS_ENABLED` to false. This stops new model calls and targets while
preserving the append-only record.

Do not automatically stop a healthy marker when an already-frozen target has a
time-bounded capture due: doing so can convert a recoverable decision incident
into an unrecoverable outcome gap. Keep it running long enough to complete the
governed attempt unless the marker, price-integrity contract, credential, or
database itself is implicated. The collector may continue gathering public
evidence unless evidence integrity is implicated.

Pause all three runtimes for schema, database, role, authorization, or suspected
cross-boundary access incidents. Never repair an incident by granting table
access, using `SET ROLE`, editing a row, resetting a production LLM counter, or
re-enabling the legacy login.

A terminal price-integrity failure permanently halts that formal run. Preserve
all raw receipts and start a newly preregistered run if continuation is
scientifically justified.

## Required alerts

- Failed collector query, collection cycle, lineage binding, or database write
- Empty/stale required-source coverage and stale `running` fetch/cycle receipt
- X request/post budget exhaustion or attempted overrun
- Decision pre-reservation retry exhaustion or any post-reservation failure
- Unexpected model identity, missing response identity, prompt limit, or daily
  LLM reservation-budget exhaustion
- Marker capture failure and terminal price-integrity halt
- Missing/stale/active split heartbeat or failure not followed by a strictly
  newer success
- Role/RLS/authorization/configuration drift
- Backup, restore rehearsal, offline verification, or alert-delivery failure

## LLM and price-cost controls

The decision release fixes three model calls per decision and three per UTC day,
with `TRADINGAGENTS_LLM_MAX_RETRIES=0`. Each attempted external invocation first
reserves both database-owned counters in
`formal_llm_budget_counters` and appends its immutable reservation artifact in
the same transaction. A reservation is never refunded. A crash after
reservation is an intent-to-treat missing decision, not permission to retry or
reset the counter.

The marker captures the frozen `yfinance` adjusted and unadjusted daily-bar
regular-session Open, not an exchange auction print. It stores both endpoints,
corporate actions, universe/benchmark manifest, timestamps, return vector, and
build identity atomically before the fixed deadline. There is no late catch-up
or operator price override. Adding a vendor, fallback, consensus/tolerance
rule, or different price definition requires a new outcome-semantics identity
and release.

## Leakage-bounded review operations

Online workers never materialize or view efficacy reports. Outcome analysis is
an offline, short-lived operation after the database has committed the governed
outcome-access receipt for the relevant gate.

- 20 intervals: operations-only; no forecast, target, weight, NAV, return, or
  other outcome read.
- 60 intervals: fixed calibration/source-quality diagnostic after an access
  receipt; no strategy comparison or protocol action.
- 126 intervals: blinded operational counts only; no outcome access, strategy
  identities, ranks, tests, or efficacy statistics.
- Exactly 252 assigned intervals: the sole confirmatory readout, only after
  every successful decision has an offline `external_calls=0` verification and
  the exact final verification manifest exists.

Viewing an already-materialized 60- or 252-gate artifact must append its own
outcome-access receipt. Never query withheld tables manually, recreate a failed
report in a notebook, or tune the protocol after an interim look.

## Credential rotation

Create a replacement Fly Reader user for only the affected runtime and apply
its narrow migration-owned grants/policies first. Attach it temporarily as
`MEDIA_DB_URL_NEXT` through a non-logging secret workflow. Deploy and validate
direct login, forbidden privileges, exact role contract, and authorization
binding from inside the correct app. Then stage replacement of `MEDIA_DB_URL`
and removal of `MEDIA_DB_URL_NEXT` in one Fly secret deployment.

For collector rotation, require a natural successful final receipt afterward.
For decision or marker rotation, require its exact paused heartbeat and
postauthorization preflight. Only then revoke the old user's grants and delete
it. Never use the legacy combined role as a fallback, and never move one
runtime's URL into another app.
