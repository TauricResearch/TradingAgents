---
date: 2026-05-04
tags: [feature, database, ui, refactoring, infrastructure]
agent: local-ai
environment: local
---

## Debrief: Daily Price Records Epic (PRICES-001)

### What Was Done

**Epic PRICES-001 — 4 stories, 19 commits ahead of main**

**S01 — Prices table + backfill**
- Added `prices` table to `server/lib/schema.sql` (ticker, date, OHLCV, volume, currency)
- Updated `scripts/get_price.ts` to extract full OHLCV from Yahoo Finance `indicators.quote[0]` (array-of-arrays format, not `quote[].quote[]`)
- Added `scripts/sync-prices.ts` — caught bug: `quote[0].quote` was wrong; correct path is `indicators.quote[0]` (each key is an array of values)
- Added `--prices` flag to `scripts/seed_database.ts` with `seedPrices()` function
- `connectDb()` now auto-applies `schema.sql` on first connect — new DBs get schema automatically
- Schema now includes all 12 positions (degiero + ibkr + test platforms) instead of test-only

**S02 — sync-prices.ts**
- Catch-up mode: fetches latest price for all open positions
- `--all` mode: gap detection + fill + catch-up
- `--ticker TICKER`: single ticker backfill
- `--dry-run`: preview without writing
- Weekend exclusion in gap detection (markets don't trade Sat/Sun — no false positives on gap reports)
- Gap fill warns if gap > 1mo (YF API limit) — falls back gracefully
- `INSERT OR REPLACE` — fully idempotent

**S03 — Holdings view with sparklines + stop monitoring**
- New `GET /api/holdings/positions` endpoint — reads positions from `prices` table + exit plans
- Sparkline: 20 bars sampled evenly across available history (not consecutive last 20 days)
- Stop status: danger (<5% above invalidation), watch (5–20%), safe (>20%)
- Urgency sorting: danger rows first, then worst P&L
- Exit plan loading from `~/.tradingagents/positions/{platform}/{ticker}.yaml`
- New "Positions" section in holdings view with freshness badges (green/yellow/red)
- Auto-refresh every 60s

**S04 — Freshness indicator**
- Built into positions table (`lastPriceDate` + `renderFreshnessBadge()`)
- 🟢 <1 day, 🟡 1–2 days, 🔴 >2 days
- No separate TD needed — absorbed into S03

**Also done:**
- `scripts/get_price.ts`: crypto ticker mapping (ETH→ETH-USD, BTC→BTC-USD) — bare tickers returned wrong price
- `Justfile`: `sync-prices`, `sync-prices-all`, `sync-prices-ticker`, `seed-db-prices`
- Rewrote `playbooks/briefs-playbook.md` (lean 10-line format; archived original)
- Archived original TauricResearch README to `archive/upstream/tauric-readme.md`
- New fork README (`README.md`) with quick-start, architecture, key commands

### Problems

1. **`quote[0].quote` format was wrong** — Yahoo Finance's chart API returns `indicators.quote[0]` as a plain object with array values (not nested `quote[]`). Fixed by using `indicators.quote?.[0]` and accessing `.open[i]`, `.high[i]`, etc.

2. **Stray DELETE after insert in seedPositions()** — `db.exec("DELETE FROM positions WHERE platform = 'degiero' OR platform = 'ibkr'")` ran after the insert loop and wiped the degiero/ibkr positions. Removed entirely.

3. **get_price.ts returned wrong prices for crypto** — bare `ETH` returned $22 (invalid Yahoo Finance symbol). Need `ETH-USD`. Added `yfTicker()` mapper function. Re-seeded both dev and test DBs.

4. **Weekend gaps detected as real gaps** — gap detection checked raw day count (>1 day diff = gap). But markets don't trade weekends. Fixed to count only weekdays between consecutive price dates.

5. **Schema not auto-applied on new DB** — `connectDb()` in `seed_database.ts` didn't apply schema. New DBs failed with "no such table: prices". Fixed by reading and exec'ing `schema.sql` in `connectDb()`.

6. **`Bun.spawnSync` --ticker flag not passed** — The `bun run scripts/sync-prices.ts --ticker AAPL` was being wrapped by `bun run` prefix in Justfile (treated `--ticker` as bun run flag). Fixed by using `bun scripts/sync-prices.ts` directly.

### Lessons Learned

1. **Verify Yahoo Finance response structure empirically** — Don't trust TypeScript types for API responses. `bun -e` to inspect actual structure (`quote[0].quote` vs `quote[0].open`) before writing the parser. The API shape varies and the types were misleading.

2. **Post-insert DELETE statements are a trap** — Any cleanup statement after an insert loop should be reviewed carefully. If the intent was "clear before insert", the clear should be in `clearTable()` not after the insert. The DELETE was a legacy artifact from when only test positions existed.

3. **Crypto tickers need suffix mapping** — Yahoo Finance uses standard suffixes (`ETH-USD`, `BTC-USD`). Any non-USD, non-EUR equity that doesn't trade on standard exchanges needs mapping. Add a ticker map at the fetch layer, not in the schema.

4. **Weekend gap detection needs business logic** — Gap detection can't just count calendar days; it must count trading days. Stock/ETF gaps exclude weekends; crypto gaps may not. Default to conservative (exclude weekends for all) — catch-up will fill weekend gaps anyway.

5. **Idempotent schema application** — Using `CREATE TABLE IF NOT EXISTS` in `connectDb()` means both new and existing DBs are handled automatically. No separate migration step needed.

6. **Bun's `__dirname` works in scripts** — `join(__dirname, "get_price.ts")` correctly resolves to the script's directory. Useful for subprocess calls from any working directory.

### PR Status

- **PR**: https://github.com/pjsvis/TradingAgents/pull/4
- **Commits**: 19 ahead of `main`
- **TDs in review**: `td-dc8ff6` (script migration), `td-d604a9` (sync-prices), `td-ef441f` (Portfolio Intelligence), `td-37fab4` (holdings sparklines)
- **Epic PRICES-001**: All 4 stories complete

### Verification

```bash
# Prices table populated
sqlite3 portfolio.db "SELECT ticker, COUNT(*) FROM prices GROUP BY ticker ORDER BY ticker;"

# sync-prices works
bun scripts/sync-prices.ts --all --verbose

# Holdings API returns enriched positions
curl -s http://localhost:3000/api/holdings/positions | python3 -c "
import json,sys; d=json.load(sys.stdin)
for p in d['positions']: print(p['ticker'], p['stopLevel'], len(p['sparkline']))
"

# Holdings page renders (stop badges + sparklines)
# Visit http://localhost:3000/holdings
```