# Controlled deployment procedure

This document is the §9 deliverable of Phase 4: how to move the service onto a
verified commit **without** the operator discovering afterwards that the running
process was serving older code.

It is written to be executed in a test environment first. Nothing here restarts
production on its own: the restart step is marked **REQUIRES EXPLICIT
AUTHORIZATION** and no script in this repository performs it.

## Why this document exists

The data-lineage audit could not answer a basic question: *is the process serving
the commit that is on disk?* A long-running service imports its modules once, at
start. Merging a fix changes the files, not the running process, so a service
started before the merge keeps executing the old code — and every check that
inspects files on disk reports it as healthy.

Phase 1 added the identifiers (`build_info.commit`, `loaded_at`) that make the
question answerable. This procedure is how to use them.

## 1. Identify the target commit

```bash
git fetch origin
git log --oneline origin/custom -1
```

Record the SHA. It must be the merge commit on `custom`, not a feature branch:
a feature branch has not passed the integration checks.

**Gate:** do not proceed unless CI on that commit is 7/7 green (5 test jobs,
lint, clean-install smoke, P0 regression, end-to-end reliability). A red check is
a blocker, not a warning.

## 2. Compare against what the service is running

```bash
curl -s http://127.0.0.1:8010/api/health | python -m json.tool
```

Read three fields:

| Field | Meaning | What a problem looks like |
|---|---|---|
| `build.commit` | the commit this process loaded | differs from step 1 |
| `build.service_started_at` | when this process imported its code | older than the merge commit's date |
| `build.validators` | whether each deterministic component is loaded and exposing its callables | any `"loaded": false` |

The pair (**commit** older than the deployment **and** a recent
`service_started_at`) is not contradictory: it means the process restarted after
the merge but the working tree was not updated. The pair (*recent* commit with an
*old* `service_started_at`) means the files changed and the process did not
restart — the stale-process case this document exists to catch.

**Gate:** `validators` must be all `true`. A `false` here means a module the
analysis depends on failed to import or lacks an expected callable, and every
metric it would have certified is missing. That is a blocker.

## 3. Verify in an isolated environment first

Never rehearse on the production unit. Use a separate `results_dir` and a
separate port so nothing collides:

```bash
cd /path/to/TradingAgents
export TRADINGAGENTS_RESULTS_DIR=/tmp/ta-smoke/logs
export TRADINGAGENTS_CACHE_DIR=/tmp/ta-smoke/cache
export TRADINGAGENTS_MEMORY_LOG_PATH=/tmp/ta-smoke/memory/log.md

# Offline suites: no vendor calls, no LLM calls.
.venv/bin/python -m pytest -q \
  tests/test_p4_e2e_brkb.py \
  tests/test_p4_determinism.py \
  tests/test_p4_negative.py \
  tests/test_p4_execution_boundary.py

# The service itself, on a spare port.
.venv/bin/python -m uvicorn webapp.app:app --host 127.0.0.1 --port 8011 &
curl -s http://127.0.0.1:8011/api/health | python -m json.tool
kill %1
```

**Gate:** the health payload from the isolated instance must report the commit
checkouts from step 1. If it reports `unknown`, the checkout has no git metadata
(a tarball deployment) — that is acceptable only if you record the commit SHA in
the deployment notes manually, because the service cannot tell you.

## 4. Confirm no stale process holds the old code

```bash
systemctl status tradingagents-web --no-pager
systemctl show tradingagents-web -p ExecMainStartTimestamp -p MainPID
```

Compare `ExecMainStartTimestamp` with the merge time. A process older than the
merge is running pre-merge code regardless of what the files say.

To find a process started by hand as well:

```bash
ss -ltnp | grep -E ':(8010|8011)\b'
```

**Gate:** no listener on the production port whose start time predates the merge.

## 5. Restart — **REQUIRES EXPLICIT AUTHORIZATION**

> Do **not** run this step autonomously. The repository's own contract
> (`AGENTS.md` §6) forbids unattended production action, and a restart drops
> in-flight analyses. Obtain authorization, then run:

```bash
sudo systemctl restart tradingagents-web
```

Afterwards, re-run step 2 and confirm `build.commit` equals the target SHA and
`build.service_started_at` is *later* than the merge.

## 6. Post-deployment verification

1. **Health** — step 2 again; all `validators` true, commit as expected.
2. **One real analysis** on a known instrument, then read its run record:

   ```bash
   ls -1 "$TRADINGAGENTS_RESULTS_DIR"/BRK-B/runs/ | tail -1
   ```

   Confirm the record exists, carries a `run_id`, a `fingerprint.commit` equal to
   the deployed SHA, a populated `metric_registry`, and a
   `decision.execution_action`.

3. **Confirm nothing was overwritten** — the run directory must hold every
   analysis performed since deployment, one file per run. A single file for
   multiple analyses means the run-scoped naming regressed.

4. **Confirm the order boundary** — in that run record,
   `execution_gate.authorized_orders` must be empty unless the gate actually
   proposed, and `decision.reason_codes` must name every reason.

## 7. Rollback

```bash
git checkout <previous-verified-sha>
sudo systemctl restart tradingagents-web   # REQUIRES EXPLICIT AUTHORIZATION
```

Verify with step 2. Run records written by the newer build remain readable: the
schema is additive and versioned (`schema_version`), so a rollback does not
orphan them.

## What this procedure does not cover

- **Live broker connectivity.** This repository has no broker adapter. The
  verified boundary is the `ExecutionGate`; no broker end-to-end test exists and
  none is claimed. See `tests/test_p4_execution_boundary.py`, which fails if an
  adapter is ever added without revisiting this statement.
- **Database migrations.** There is no external database; state is files on disk
  under `results_dir`.
- **Multi-instance consistency.** A single systemd unit is assumed. With several
  instances behind a load balancer, step 2 must be repeated per instance, because
  each holds its own imported modules.

## Checklist

- [ ] Target SHA is the `custom` merge commit and CI is green
- [ ] `build.commit` matches the target SHA
- [ ] `build.service_started_at` is later than the merge
- [ ] All `build.validators` are `true`
- [ ] Isolated-environment suites pass
- [ ] No listener predates the merge on the production port
- [ ] Restart performed **with authorization**
- [ ] One run record inspected: id, fingerprint, registry, gate verdict
- [ ] No run records were overwritten
