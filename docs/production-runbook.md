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
- `X_BEARER_TOKEN`: the X API bearer token; and
- `TRADINGAGENTS_ALERT_WEBHOOK_URL`: an optional but strongly recommended alert
  destination.

`fly.toml` fixes the non-secret policy: broad global mode, hourly editorial-news
cycles, one bounded X cycle per day, no ticker watchlist, no US-hours gate, and
no runtime schema migration. This repository's checked-in value is `true`
because `tradagent` is the already-approved collector. In a fresh fork or new
app, set it to `false` through setup and focused verification so a first deploy
cannot collect accidentally.

Do not put secrets in `fly.toml`, command history, tickets, or logs. Pipe them to
`fly secrets import --stage -a tradagent`, then clear the shell variables. Confirm
only secret names with:

```bash
fly secrets list -a tradagent
```

If a webhook was staged previously, it will take effect on the next deploy or
machine update. It does not need to be added to any retired app.

## Deploy and activate

Activation is reviewed configuration, not a secret override. After focused local
tests and database preparation pass, change `MEDIA_COLLECTION_ENABLED` to `true`
in `fly.toml`, review that exact diff, and commit it. From that clean commit:

```bash
fly config validate -c fly.toml
fly deploy -a tradagent
fly status -a tradagent
fly logs -a tradagent
```

Look for a complete global collection cycle and no repeated crash loop. Then test
the alert path from inside the running image:

```bash
fly ssh console -a tradagent -C "tradingagents-poller --test-alert"
```

The command emits a sanitized test payload and exits nonzero if delivery fails.
It does not query the database or a provider.

## Verify collection

Use the collector's read-only inspection modes:

```bash
fly ssh console -a tradagent -C "tradingagents-poller --stats"
fly ssh console -a tradagent -C "tradingagents-poller --audit"
```

`--stats` summarizes stored rows. `--audit` reports whether the expected query
slots were covered and lists recent provider receipts without printing secret
URLs. A healthy cycle has a successful receipt for every configured broad-news
slot. That receipt may prove zero forecast-eligible stories with exact `0`/`[]`
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

## Pause safely

For an incident or schema change, stop writes immediately:

```bash
fly scale count 0 -a tradagent
fly status -a tradagent
```

For a durable pause, change `MEDIA_COLLECTION_ENABLED` back to `false` in a
reviewed configuration commit before any later deploy or resume.

Back up Postgres before changing schema. Apply migrations with a dedicated schema
administrator, never `MEDIA_DB_URL`; follow [`migrations/README.md`](../migrations/README.md).
After a restore test or migration check succeeds, review and commit the switch
back to `true`, deploy that commit, and restore the machine count if necessary:

```bash
fly deploy -a tradagent
fly scale count 1 -a tradagent
fly logs -a tradagent
```

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
- only the collector runtime has data-source secrets;
- no runtime role can migrate schema;
- collection receipts and heartbeat are current;
- X request counts stay within the frozen budget;
- alert delivery succeeds; and
- no documentation or dashboard implies that collected data is proven alpha.
