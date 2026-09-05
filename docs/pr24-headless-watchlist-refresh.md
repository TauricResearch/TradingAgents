# PR24: Headless Watchlist Refresh

## Purpose

PR24 adds a command-line entry point for the same explicit watchlist refresh used by the cockpit. It is designed for a user-run terminal command or an operating-system task scheduled by the user, without installing or managing a background service itself.

## Commands

Preview the saved symbols without provider calls:

```powershell
python -m tradingagents.research_platform.watchlist_refresh_cli --data-dir .runshots --dry-run
```

Run the refresh with an explicit research date and lookback:

```powershell
python -m tradingagents.research_platform.watchlist_refresh_cli --data-dir .runshots --as-of 2026-07-10 --lookback-days 90
```

The command prints JSON with the batch id, selected symbols, terminal job records, succeeded count, and failed count. It exits with status `1` when any job fails.

## Safety

The command reads only explicitly saved watchlist entries, queues ordinary single-worker research jobs, and never attaches manual trade signals. It does not create a Windows Task Scheduler entry, run persistently, or execute orders.
