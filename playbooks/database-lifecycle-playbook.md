---
date: 2026-05-07
tags: [playbook, database, sqlite, backup, test, live]
---

# Database Lifecycle Playbook

## Purpose

Manage the two SQLite databases used by TradingAgents: **LIVE** (production data) and **TEST** (development/sandbox). Prevent accidental cross-contamination and ensure recoverability.

---

## The Two Databases

| Database | File | Purpose | Environment Variable |
|----------|------|---------|---------------------|
| **LIVE** | `portfolio.db` | Real positions, trades, signals, analyses | `PORTFOLIO_DB` |
| **TEST** | `test_portfolio.db` | Development data, experimentation, integration tests | `TEST_PORTFOLIO_DB` |

### Switching Context

The codebase uses `TEST_MODE=1` to switch from LIVE to TEST:

```bash
# LIVE mode (default)
bun run src/server/index.tsx      # uses portfolio.db
bun scripts/seed_database.ts        # seeds portfolio.db
just trading AAPL                   # uses portfolio.db

# TEST mode
TEST_MODE=1 bun run src/server/index.tsx  # uses test_portfolio.db
TEST_MODE=1 bun scripts/seed_database.ts --db ./test_portfolio.db
```

**Never** run a script that modifies data without confirming which database it targets.

---

## Backup Process

### Automated Daily Backup

```bash
# Backup LIVE database
just backup
# → creates backups/portfolio-2026-05-07-09-15-00.db

# Backup TEST database
just backup-test
# → creates backups/test_portfolio-2026-05-07-09-15-00.db
```

### Backup Retention

```bash
# List all backups
just backups-list

# Prune backups older than 7 days
just backups-prune 7
```

### Manual Backup (before risky operations)

```bash
# Before running a new migration, seed script, or bulk update:
just backup
# Verify: just backups-list
# Run risky operation
# If broken: restore from backup
```

### Restore from Backup

```bash
# Stop the server first
pkill -f bun

# Restore LIVE database
cp backups/portfolio-2026-05-07-09-15-00.db portfolio.db

# Restore TEST database
cp backups/test_portfolio-2026-05-07-09-15-00.db test_portfolio.db

# Restart server
bun run src/server/index.tsx
```

---

## Development Workflow

### Rule: TEST First, LIVE Last

1. **All new features start in TEST mode**
   ```bash
   TEST_MODE=1 bun run src/server/index.tsx
   # Verify feature works with test data
   ```

2. **Integration tests run against TEST database**
   ```bash
   TEST_MODE=1 bun test tests/trade-calculator-integration.test.ts
   ```

3. **Only verified features touch LIVE database**
   ```bash
   # After tests pass, run in LIVE mode
   bun run src/server/index.tsx
   ```

### Rule: Never Mix Data

| Don't | Do Instead |
|-------|-----------|
| Copy `portfolio.db` to `test_portfolio.db` | Use `just backup` then `cp` |
| Run `sync-prices` on LIVE without backup | `just backup && just sync-prices` |
| Test a new migration on LIVE | `TEST_MODE=1` first, then LIVE |
| Seed random test data into LIVE | Always use TEST database for experiments |

---

## IG API Demo Account Database

The IG API integration uses the **TEST database** for all API calls:

```bash
# IG API tests run in TEST mode
TEST_MODE=1 bun scripts/ig-test-trade.ts AAPL
```

This ensures:
- Demo trades don't pollute LIVE positions
- Test account balances don't affect real P&L
- Failed API calls don't corrupt production data

---

## Recovery Procedures

### Scenario 1: Accidental LIVE data deletion

```bash
# 1. Stop everything
pkill -f bun

# 2. List backups
just backups-list

# 3. Restore most recent backup
cp backups/portfolio-2026-05-07-09-15-00.db portfolio.db

# 4. Restart
bun run src/server/index.tsx
```

### Scenario 2: Corrupted TEST database

```bash
# Simply recreate — it's test data
TEST_MODE=1 bash scripts/init-test-db.sh --reset
TEST_MODE=1 bun scripts/seed_database.ts
```

### Scenario 3: Need to compare LIVE vs TEST state

```bash
# Row counts for both databases
echo "=== LIVE ==="
sqlite3 portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals"

echo "=== TEST ==="
sqlite3 test_portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals"
```

---

## Verification Checklist

Before any database-modifying operation:

- [ ] Confirmed `TEST_MODE` env var state (1 = TEST, unset = LIVE)
- [ ] Ran `just backup` if modifying LIVE database
- [ ] Verified `just backups-list` shows recent backup
- [ ] Checked which database file is being used (look at startup log: "DB connected: ...")
- [ ] For IG API calls: confirmed demo account (not live)

---

## Quick Reference

| Need | Command |
|------|---------|
| Backup LIVE | `just backup` |
| Backup TEST | `just backup-test` |
| List backups | `just backups-list` |
| Prune old backups | `just backups-prune 7` |
| Start server (LIVE) | `bun run src/server/index.tsx` |
| Start server (TEST) | `TEST_MODE=1 bun run src/server/index.tsx` |
| Reset TEST DB | `TEST_MODE=1 bash scripts/init-test-db.sh --reset` |
| Seed TEST DB | `TEST_MODE=1 bun scripts/seed_database.ts` |
| Check DB path | `sqlite3 portfolio.db "PRAGMA database_list"` |
