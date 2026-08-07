# Collector production runbook

## Scope

Production now means one continuously running evidence collector. Forecasts,
portfolio decisions, labels, and evaluations are offline research jobs; they are
not daemons and they do not place orders.

```text
Fly collector -> managed Postgres -> immutable offline research artifacts
```

The retired paper-decision and price-marker apps are not required. Their staged
secrets do not affect the collector, and no model or broker credential belongs on
the collector app.

## Required configuration

The Fly app in `fly.toml` is currently named `tradagent`. It needs:

- `MEDIA_DB_URL`: a restricted collector-runtime Postgres DSN;
- `MEDIA_DB_DIRECT_URL`: an optional direct/session-affine DSN override for the
  singleton lease (a Fly MPG `pgbouncer.<cluster>.flympg.net` URL derives its
  matching private `direct.<cluster>.flympg.net` endpoint automatically);
- `X_BEARER_TOKEN`: the X API bearer token; and
- `TRADINGAGENTS_ALERT_WEBHOOK_URL`: the required production alert destination.

`fly.toml` fixes the non-secret policy: broad global mode, hourly editorial-news
cycles, one bounded X cycle per day, no ticker watchlist, no US-hours gate, and
no runtime schema migration. It also fixes the private health listener to port
`5500`, and requires the production alert webhook during preflight; no Fly
service publishes the health port to the internet. This repository's checked-in
collection value is `true`
because `tradagent` is the already-approved collector. In a fresh fork or new
app, set it to `false` through setup and focused verification so a first deploy
cannot collect accidentally.

Do not put secrets in `fly.toml`, command history, tickets, or logs. Pipe them to
`fly secrets import --stage -a tradagent`, then clear the shell variables. Confirm
only secret names with:

```bash
fly secrets list -a tradagent
```

> **Credential-output warning:** Never run, capture, or paste
> `fly mpg status --json`. Current `flyctl` versions can include plaintext
> cluster credentials in that response. Use `fly status -a tradagent`,
> `fly secrets list -a tradagent`, or `fly mpg users list <CLUSTER_ID>` for the
> narrow inventory you need. Project allowlisted fields and redact them inside
> the process before emitting any structured diagnostic; never save a raw MPG
> status response.

If a webhook was staged previously, it will take effect on the next deploy or
machine update. It does not need to be added to any retired app.

## Deploy and activate

Activation is reviewed configuration, not a secret override. After focused local
tests and database preparation pass, change `MEDIA_COLLECTION_ENABLED` to `true`
in `fly.toml`, review that exact diff, and commit it. From that clean commit:

```bash
scripts/deploy_collector.sh tradagent
fly status -a tradagent
fly checks list -a tradagent
fly logs -a tradagent
```

The deploy wrapper refuses a dirty worktree, embeds the exact commit, waits for
the new process to complete its own healthy cycle, and verifies that the passing
check belongs to the sole started Machine running that exact revision. Before it
changes Fly, it saves the deployed image and configuration together and requires
the baseline Machine's `collector_health` check to pass. A failed or interrupted
rollout restores both only while exact ownership of the candidate remains
provable. A legacy Machine without that check requires the narrowly scoped,
one-invocation break-glass procedure below; its snapshot is restorable but is not
represented as healthy. Fly uses an immediate one-worker handoff rather than
overlapping collectors; a PostgreSQL advisory lease independently blocks an
accidental second worker or manual one-shot from calling providers.

By default the wrapper deploys only the exact commit currently advertised by the
authenticated `origin/main` remote branch; it never trusts a possibly stale local
remote-tracking ref. It resolves that exact remote branch before Fly inspection
and again immediately after the rollback snapshot, before deployment. An
unavailable, malformed, or changed remote fails closed without printing remote
transport output, which can contain credentials. A different configured target
uses `COLLECTOR_DEPLOY_TARGET_REF=<remote>/<branch>`. An explicitly reviewed
emergency rollout from another ref must opt in with
`COLLECTOR_DEPLOY_ALLOW_UNMERGED=true`; do not make that setting persistent. The
wrapper also takes a local per-app lock and atomically creates
`refs/heads/tradingagents-deploy-lock/<app>` on the shared writable Git remote.
The default lock remote is `fork`; set
`COLLECTOR_DEPLOY_LOCK_REMOTE=<remote>` only when every deployment host uses that
same repository. The alias is accepted only when its one expanded,
credential-free push URL resolves to the checked-in canonical identity
`github.com/clarkipeng/tradingagents`; the wrapper then uses that captured URL
for both reads and writes. Fetch/push splits, multiple push URLs, embedded HTTPS
credentials, or a different fork fail before Fly is read. This remote lock is
held from before the rollback snapshot
until forward verification or fenced rollback completes. Creation is
non-forced, ownership is reauthenticated around Fly mutations, and cleanup uses
an exact `--force-with-lease`, so one process cannot delete another process's
lock. Git transport output is suppressed because remote URLs can contain
credentials, inherited Git tracing is disabled, and a lost Git acknowledgement
is reconciled from the exact server ref. Every attempt receives a random,
non-secret image-tag suffix while the embedded `GIT_REVISION` remains the exact
reviewed SHA. After the candidate appears, success and rollback ownership require
its exact nonce-tag, Machine ID, immutable instance ID, digest, Fly release ID,
release version, rollback lineage, and configuration fingerprint. Release
history must also prove that the candidate's nearest prior complete release is
the saved baseline (or the exact release most recently restored by this fenced
wrapper) before either success or rollback.

Rollback does not start a second unguarded `fly deploy`. The helper acquires
Fly's exclusive lease on the exact candidate Machine, requires the lease version
and two independent API views to reproduce the authenticated tuple and sole,
complete, stateless Machine topology. It authenticates the full saved baseline,
pins its image by digest, records a hashed from/to lineage, and submits the full
config exactly once with both the lease nonce and candidate `instance_id` as
`current_version`. It then keeps the bounded ten-minute lease while fresh GETs
prove the new instance, digest-pinned config, started state, healthy host, and
one-Machine topology. Lost update responses are reconciled with reads and never
retried. A release that lands before the lease changes that version; a release
attempted after acquisition cannot update the leased Machine. Either case fails
closed or serializes after the rollback, so this attempt cannot erase an
intervening good release. If explicit lease release fails, the helper fails and
the Git mutex is preserved until an operator waits for lease expiry and
reconciles state. No token, identifier, file path, or API response body is logged.

A same-commit deployment or configuration-only update from another host is
treated as superseding this attempt and is never rolled back.
An empty, multi-Machine, or otherwise unbound state after an interrupted immediate
handoff is also ambiguous: the wrapper fails closed and refuses automatic rollback
instead of risking replacement of another actor's release.

All production releases must use this wrapper. The remote ref serializes wrapper
deployments across hosts, but Git cannot prevent a raw `fly deploy`, direct
Machines API call, or force-update of the lock ref by an administrator. The
Machine tuple, release-history checks, health verification, and rollback lease
still detect those cases and fail closed; they do not make unsupported mutation
paths safe.

Once `fly deploy` has been invoked, the lock is releasable only after the wrapper
authenticates a healthy exact forward state or an exact completed fenced
rollback. A failed CLI acknowledgement followed by a temporarily unchanged
Machine is not terminal—the server operation may still land—so the wrapper
leaves the lock in place for manual reconciliation. It does the same after an
unverifiable or failed rollback and after a signal interrupts a mutating child.

An ungraceful host crash intentionally leaves its remote lock in place. Never
auto-expire or force-delete it. First prove there is no deploy process and no Fly
mutation in progress, then read the one exact ref and conditionally delete only
the SHA you inspected through the checked-in recovery helper:

```bash
scripts/unlock_collector_deploy.sh inspect tradagent
# Copy the exact remote owner SHA printed above only after Fly reconciliation.
scripts/unlock_collector_deploy.sh release tradagent <exact-owner-sha>
```

The helper validates the same single canonical push URL as the deploy wrapper,
uses it for both read and exact-CAS delete, suppresses Git transport/tracing, and
reconciles a lost delete acknowledgement. A crash also leaves the local
`$TMPDIR/tradingagents-tradagent.deploy.lock`; the helper accepts only its exact
one-file owner record, refuses a live PID, and removes a verified dead local lock
without recursive deletion. If either command reports malformed state, a live
PID, or a changed owner, stop: the lock is not yours to remove.

Current `fly releases --json` output is finite. If enough intervening failed
attempts push the baseline outside that history window, predecessor proof fails
closed and automatic rollback is intentionally unavailable; do not bypass it.

The image build rejects any missing or non-full-lowercase Git SHA, so a raw
`fly deploy` cannot create an untraceable production image. It records the
accepted value in OCI metadata and
`/opt/tradingagents/REVISION`. Before Fly replaces the running worker, its
temporary release Machine automatically runs `--global-only --preflight`. That
database-read-only command validates the frozen collector configuration,
database schema, and restricted runtime role without calling a provider or
writing a receipt. Because production requires the webhook, it also sends one
sanitized `release_preflight_probe` and fails unless the destination confirms
delivery. Any nonzero result stops the deployment before the persistent worker
changes. A
failed release still advances Fly's release history, so the app-level version can
name the failed attempt while the sole started Machine correctly remains on the
last complete release. Verify the running Machine image/release, not only the
app-level version, when investigating a stopped rollout.

Provider responses are byte-bounded and schema-validated. Malformed X error
envelopes and non-RSS HTML cannot masquerade as valid empty observations.
Only transient Google transport failures receive immediate bounded retries, and
a per-cycle circuit breaker limits a broad Google outage to two failed query
slots. After any daemon-level database failure, the next supervised attempt may
request free editorial-news slots again; stable item IDs deduplicate stored
evidence. Paid X calls are separately protected by durable per-request budgets
and the exact daily-cycle identity, so a retry cannot silently spend twice.
PostgreSQL metadata writes are atomic,
transaction-local timeouts prevent a row lock from hanging the worker
indefinitely, and a 30-second direct-session heartbeat terminates collection
after a lost singleton lock. The ordinary database engine uses only
PgBouncer-compatible network startup parameters and explicitly disables
psycopg named prepared statements; every transaction applies fixed `SET LOCAL`
timeouts and the pinned search path, so statement names or settings cannot leak
to the next transaction-pooled client. The session-affine direct engine
separately retains its startup read-only fail-safe. Preflight proves session
affinity and cross-session advisory exclusion; an unknown database host fails
closed unless
`MEDIA_DB_DIRECT_URL` is configured. These rules are pinned as collector policy
v2 (`collector_f6aaca9c1014887d9e78da82`) under protocol
`protocol_b4c36948d856e9a82e7167bb`. Only the exact historical identity pairs in
the protocol compatibility list remain readable, including the currently
deployed `collector_fa2421d5a25636de4f035323` lineage. A candidate that failed
before producing live evidence is not made compatible merely because Fly
created a failed release record.

The schema gate authenticates all 75 collector columns, including exact
nullability and the absence of server defaults, identity/generated expressions,
bounded strings, domains, or alternate collations. Historical `TEXT` and fresh
unbounded `VARCHAR` columns are treated as one type family, but each essential
`CHECK` constraint must still match an explicitly approved hash. Only the four
representation-sensitive checks allow both hashes produced by reparsing the
reviewed migrations against those types. Do not approve a new hash merely
because PostgreSQL preserved a different expression tree through an `ALTER
TYPE`; restore the reviewed migration definition and rerun preflight.

CI recreates this contract on PostgreSQL 16 and routes two independent psycopg
clients through a real PgBouncer transaction pool with one backend and named
prepared statements disabled. It also runs the packaged collector image through
the pool while keeping the advisory-lock connection direct, matching production.

If release preflight rejects the database, its log projection contains only a
fixed failure stage and exception-type vocabulary, never the DSN or database
message. For example, `primary_connection` / `OperationalError` localizes the
failure to opening the configured primary engine without disclosing
credentials. Inspect the failed release logs, `fly releases`, and the sole
started Machine together. Do not bypass preflight or add the failed candidate to
the historical compatibility list; correct the connection/runtime contract and
redeploy through the wrapper.

After activation, Fly checks `/healthz` over its private network. The endpoint
reports whether the current process has produced complete coverage; it cannot be
satisfied solely by a previous image's recent receipts. The port is not a public
API. A hashed static-slot manifest prevents malformed empty coverage from
passing, and an incomplete current-day X cycle stays unhealthy during later
hourly news cycles. A daemon runtime failure keeps the process alive but
unhealthy, closes the store and any singleton lease, and reacquires both before
another provider call. Retries use signal-responsive exponential backoff from 5
seconds to a 300-second cap. Identical incidents emit one transition alert plus
at most one daily reminder; changed failure stages/types are coalesced to at
most one transition alert per hour, and recovery is reported only after a
complete cycle. CLI validation and `--once` remain fail-fast. Look for a passing
`collector_health` check, a
complete global collection cycle, and no repeated restart loop. The deploy
wrapper also tests the alert path
from inside the exact running Machine before it reports success. You can repeat
that non-provider test independently after a webhook rotation:

```bash
fly ssh console -a tradagent -C "tradingagents-poller --test-alert"
```

The command emits a sanitized informational test payload and exits nonzero if
delivery fails. It does not query the database or a provider.

## Verify collection

Use the collector's read-only inspection modes:

```bash
fly ssh console -a tradagent -C "tradingagents-poller --stats"
fly ssh console -a tradagent -C "tradingagents-poller --audit"
fly ssh console -a tradagent -C "tradingagents-poller --audit-history"
```

`--stats` summarizes stored rows. `--audit` reports current health only, so an
old immutable failure receipt cannot look like a present outage. Use
`--audit-history` when investigating an incident; it prints the same current
health followed by a clearly delimited list of recent immutable receipts. A
healthy cycle has a successful receipt for every configured broad-news slot.
That receipt may prove zero forecast-eligible stories with exact `0`/`[]`
lineage; a raw empty or failed provider response is unhealthy. X should run only
once per UTC day, with at most two trend requests, three searches, and ten
returned posts per search.

Also check:

```bash
fly status -a tradagent
fly logs -a tradagent
fly secrets list -a tradagent
```

Absence of an alert is not proof of health. Review cycle receipts and heartbeat
freshness periodically, and test alert delivery after rotating the webhook.
The private Fly check covers a running but unhealthy process; an independent
monitor is still required to notify you if Fly or the whole app is unreachable.

## Pause safely

For an incident or schema change, stop writes immediately:

```bash
fly scale count 0 -a tradagent
fly status -a tradagent
```

The worker uses Fly's `always` restart policy, so killing its process is not a
pause mechanism. Scaling the process group to zero remains authoritative.

Back up Postgres before changing schema. Apply migrations with a dedicated schema
administrator, never `MEDIA_DB_URL`; follow [`migrations/README.md`](../migrations/README.md).
The deploy wrapper intentionally requires one known-good started Machine so it
can prove and restore the rollback state. After a restore test or migration check
succeeds, restart the previously deployed Machine, verify it is stable, and then
deploy the reviewed commit through the wrapper:

```bash
fly scale count 1 -a tradagent
fly status -a tradagent
scripts/deploy_collector.sh tradagent
```

For the single transition from a legacy baseline that has no
`collector_health` check, review its exact image and configuration snapshot first,
then apply the override to that command only:

```bash
COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE=true \
  scripts/deploy_collector.sh tradagent
```

The wrapper logs a prominent warning. Do not export or persist this variable, and
do not use it after the health-enabled collector is active. Under break-glass the
wrapper can restore the exact baseline image/configuration, but it cannot certify
that baseline as healthy.

## Rotate credentials

Rotate one secret at a time, update the Fly secret without displaying it, and
verify a real subsequent receipt. For X:

1. create or reveal the replacement bearer token in the official developer
   console;
2. stage or set `X_BEARER_TOKEN` only on `tradagent`;
3. deploy/restart the collector;
4. verify the next `xtrend`/`x` receipt and daily request counters; and
5. revoke the old token after the new one succeeds.

For the webhook, run `--test-alert` after rotation. For the database credential,
pause first, rotate the restricted runtime role, update the secret, resume, and
verify both a completed write cycle and a read-only audit.

An image/configuration rollback cannot restore a previous Fly secret value: Fly
does not reveal it to the wrapper. During every credential rotation, keep the old
credential valid and recoverable in the password manager until the new one has a
real runtime success. If verification fails, re-import the old value before
revoking anything; redeploying the old image alone is not a secret rollback.

## Offline research workflow

Collection can begin immediately. Wait for enough prospective sessions before
interpreting performance; a few days are useful only for plumbing checks.

The `tradingagents-research` CLI owns the four non-daemon stages. Inspect the
installed version's arguments rather than copying stale flags:

```bash
tradingagents-research snapshot --help
tradingagents-research decide --help
tradingagents-research label --help
tradingagents-research evaluate --help
```

The invariant is more important than the transport:

1. `snapshot` commits the exact evidence visible at a cutoff.
2. `decide` should run with an evidence-only artifact view and no outcome
   credentials; the current CLI enforces import and artifact bindings but does
   not create an OS-level sandbox for you.
3. `label` runs only after the horizon and accepts a committed decision ID. The
   current adapter stores and hashes the yfinance values returned at label time;
   those are not contemporaneously captured market-data vintages, so results are
   exploratory.
4. `evaluate` currently verifies artifact binding and reports one costed batch
   against its benchmark. Full multi-arm controls, folds, bootstrap analysis,
   and final-holdout policy remain to be implemented.

Preserve the artifact root and do not choose among repeated stochastic decision
or mutable-price artifacts. The current filesystem runner has no durable
first-attempt registry, so those reruns are exploratory. A confirmatory run must
add an append-only attempt manifest and an enforced canonical-selection rule.

Do not call a live news source while replaying a snapshot. Do not give the
decision job an outcome-bearing database credential. Do not describe a provider
alias, self-declared checkpoint JSON, or a LangGraph resume checkpoint as proof
of frozen model weights. See
[`global-event-v2.md`](global-event-v2.md) for the research and leakage contract.

## Incident guide

### X authentication or quota failure

Confirm only that `X_BEARER_TOKEN` exists, never print it. A `401`/`403` usually
means the token, product entitlement, or app permission is wrong; a `429` may be
the daily budget or provider rate limit. Do not broaden queries or add ticker
searches to compensate. News collection should continue and the X absence should
remain explicit.

### Partial news coverage

Inspect receipts to identify the failed slot. Retry only through the normal
idempotent collection path. A story discovered late retains its real receipt
time and cannot become evidence for an earlier cutoff.

### Database outage

Pause if reconnects or failures persist. The collector must not fall back from
Postgres to a local container database. Resume after connectivity and permissions
are restored; deduplication makes a normal re-poll safe.

### Alert failure

Logs remain the fallback. Rotate or correct the webhook, run `--test-alert`, and
confirm the destination received the sanitized payload. Never paste the webhook
URL into an issue or log excerpt.

### Suspected corruption or rewritten evidence

Stop collection, preserve the database and logs, and work from a restored copy.
Do not repair historical content in place. Record corrections as new vintages or
a forward migration, then explain which snapshots are affected.

## Release checklist

- collector-only tests and migration checks pass;
- database backup and restore procedure has been exercised;
- Fly image and configuration match the reviewed commit;
- the automatic database-read-only release preflight succeeds and its sanitized
  webhook probe arrives;
- `collector_health` is passing for the new Machine;
- the image revision label and `/opt/tradingagents/REVISION` match the commit;
- only the collector runtime has data-source secrets;
- no runtime role can migrate schema;
- collection receipts and heartbeat are current;
- X request counts stay within the frozen budget;
- alert delivery succeeds; and
- no documentation or dashboard implies that collected data is proven alpha.
