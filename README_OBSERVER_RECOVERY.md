# Koral Equities | Observer single-instance and crash recovery

**Scope: observation-only, no account reads, no model calls, no orders.**
The observer stores source snapshots in
`%USERPROFILE%\\.tradingagents\\observations\\koral_v3`, not in a V1/V2/V3/V3.1 portfolio.

## What a restart may and may not do

- **One observer per directory:** `observer_instance_lock` holds an OS-managed
  exclusive lock for the *full process lifetime* (including a one-off capture).
  A second process fails without making network requests or writing account state.
- **After crash/kill:** the operating system automatically releases the lock.
  The on-disk `.observer.lock` is intentionally retained and is **not**
  evidence that a process is currently alive. **Never delete it to fix a lock conflict.**
- **Still within the NY phase window:** an uncaptured phase can be collected
  when the observer restarts; existing immutable matching evidence returns
  `ALREADY_CAPTURED` without being overwritten.
- **After the NY phase window:** a missed snapshot must stay **missing**.
  No historical fetch can claim that it was a real-time preopen or preclose
  observation. A future earnings veto or blocked AI result is acceptable.
- **Corrupt/mismatched existing evidence:** fail closed and investigate.
  Never silently delete, overwrite or rewrite the evidence to pass a gate.
- A lock is not an uptime monitor or a cloud scheduler. If the PC is asleep,
  powered off, or an old-version observer remains running, scheduled captures
  can still be missed. Exchange holidays and half-days also require better
  calendar certification before unsupervised operation.

## Existing processes during the upgrade

An observer started *before this code was installed* does not hold the new
OS lock. **Stop the old PowerShell observer with Ctrl+C and ensure it is no
longer running before using a pinned, tested update and launching the new
observer.** Do not run the two different versions concurrently. Preserve
all saved observations, the `.env`, research files, and the paper portfolios.

The latest explicitly selected research subjects are `COST JPM WMT`.
Do not substitute the previous `AAPL MSFT NVDA` universe on Monday,
26 October 2026. Observe the real-time source windows and then use the
zero-AI `preflight_dry_run` on the **same** watchlist and NY date.

## Acceptance gates (must be independently executed, not merely committed)

1. Windows and Linux focused tests pass for exclusive locking, a second
   CLI process refusing the same directory, unclean process exit and
   automatic OS lock release.
2. Existing matching captures are immutable across restart and different
   ticker sets fail closed.
3. Interrupted vendor requests or atomic publication never produce an
   approved or partial source snapshot.
4. A missed NY observation remains missing rather than backdated.
5. All V1/V2/V3/V3.1 paper portfolio bytes remain unchanged by this work.

The focused repository command, after a separately verified pinned install,
is:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q tests/test_autopilot_observe.py tests/test_autopilot_feeds.py tests/test_autopilot_live_dry_run.py tests/test_autopilot_verify_dry_run.py
```

The command never needs an open market, market API keys, AI credits, or an
active paper account. **Passing it does not demonstrate live forward edge.**

Current state: source and tests committed on the development branch;
full GitHub CI, Windows install and genuine running-observer crash recovery
remain separate verification gates. Keep PR #1 draft.
