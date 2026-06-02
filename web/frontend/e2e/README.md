# E2E manual checklist

- [ ] Add 3 tickers, kick off all at once, see queueing
- [ ] Cancel a running analysis, see clean error
- [ ] Restart server mid-run, verify WS reconnects and replays the gap
- [ ] YFinance blocked -> see stale badge, server keeps running
- [ ] Open in 2 browser tabs -> both get every event
- [ ] Reload mid-run -> see persisted events from DB
