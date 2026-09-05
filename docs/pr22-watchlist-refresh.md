# PR22: Watchlist Batch Refresh

## Purpose

PR22 adds an on-demand `Refresh Watchlist` action to the local cockpit. It queues one ordinary research job for each ticker explicitly saved in the watchlist, then reports progress from the existing local job API.

## Safety and Scope

- The existing `LocalResearchJobRunner` remains single-worker, so provider requests and local artifact writes stay serialized.
- The selected provider, analysis mode, as-of date, and lookback are shared across the queued jobs.
- Batch jobs never carry a manual signal, so they do not create a trade decision, risk review, or backtest by default.
- An empty watchlist returns an empty batch rather than issuing a vendor request.

This is user-triggered batch refresh only. It intentionally does not install a background scheduler, create a persistent operating-system task, or execute trades.
