# Brief: Unified Portfolio Intelligence

**Date:** 2026-05-03
**Status:** Required
**Author:** Agent

---

## Problem

The dashboard can run analyses and track positions, but it has no concept of the **full portfolio picture** — how much cash is available, how much is deployed, what the allocation looks like across accounts, and where the next trade should go.

The current model (positions with a `platform` field) doesn't capture:
- Total cash across accounts
- Cash available for deployment vs. reserved
- Spread bet allocation as a separate bucket
- Account-level balances for non-position assets (NS&I, old SIPPs as cash equivalents)

The goal is a **single view** of the entire investment picture, driven by the research cycle (TradingAgents → signal → position → exit), with governance enforcing allocation rules.

---

## Core Loop

```
Research (TradingAgents)
    ↓
Signal generated (Buy / Hold / Overweight / Sell)
    ↓
Position sizing → how much of investable cash
    ↓
Purchase → IG ISA / IG Shares / Aviva / AJ Bell
    ↓
Exit plan created → stop, targets, time stop
    ↓
Monitor → governance checks (drift, stops, time stops)
    ↓
Exit triggered → cash returned
    ↓
Research next position
```

The loop is driven by research. All accounts are delivery mechanisms. Governance is on the portfolio, not per-account.

---

## Account Model

All accounts are delivery mechanisms. They differ only in tax treatment and access speed — not in governance rules.

**Account types:**

| Type | Tax treatment | Access | Examples |
|---|---|---|---|
| `isa` | Tax-free growth | Instant | IG ISA |
| `shares` | CGT on gains | T+2 settlement | IG Share Dealing |
| `sipp` | 25% tax-free, rest as income | Age 55+ | AJ Bell SIPP, Aviva pension |
| `spreadbet` | Tax-free (no CGT) | Instant | IG Spread Betting |
| `savings` | Interest taxed | Variable | NS&I Premium Bonds |
| `cash` | Interest taxed | Instant | Bank accounts |

**Accounts to track:**

```
ig-spreadbet     type: spreadbet     # betting bank — separate allocation
ig-isa           type: isa           # real shares
ig-shares        type: shares        # real shares
aviva            type: sipp          # group pension
ajbell           type: sipp          # SIPP
nsandi           type: savings       # Premium Bonds (manual balance)
cash-other       type: cash          # everything else (bank, legacy pots)
```

**Key decisions:**
- No account-level governance — portfolio-wide rules apply
- Accounts with positions track individual holdings; accounts without positions track a single `balance` value
- Old/legacy accounts tracked as `cash` with manual balance entries
- No need for API access to IG / AJ Bell / Aviva right now — balances updated manually

---

## Portfolio State

**Portfolio composition:**

```
Portfolio total
├── Cash (total cash across all accounts)
│   ├── Reserve (10% floor — governance minimum)
│   ├── Spread bet allocation (configurable % of total)
│   └── Investable (total − reserve − spread bet)
├── Deployed (current market value of all positions)
└── Spread bet book (separate P&L tracking)

Allocation targets (governance):
  cash_reserve:  10%
  spreadbet:     20%
  deployed:      70%
```

These are portfolio-wide targets, not per-account. The governance engine checks the deployed/deployed+cash ratio against the 70% target.

---

## Spread Betting

Separate bucket, not mixed with share positions.

**Sizing model:**
- Total spread bet allocation = X% of portfolio (configurable in governance.yaml)
- Per-bet sizing: risk = 1-2% of betting bankroll
- Stake per point = (risk amount) / (stop in points)

**Tracked separately:**
- `spreadbet_positions` table: ticker, direction (long/short), stake_per_point, entry_price, stop_price, current_price, pnl
- Not mixed with `positions` table — different tax treatment and sizing model
- P&L in GBP, updated from IG prices (manual or API when available)

**Recommendations only:** The dashboard generates spread bet recommendations from the same research signals. Execution is manual via IG. Future: IG API integration.

---

## Schema Changes

### New: `accounts` table

```sql
CREATE TABLE accounts (
  id            TEXT PRIMARY KEY,
  provider      TEXT NOT NULL,           -- "IG", "Aviva", "AJ Bell", "NS&I", etc.
  account_type  TEXT NOT NULL CHECK(account_type IN ('isa','shares','sipp','spreadbet','savings','cash')),
  name          TEXT,                    -- friendly label: "IG ISA", "Aviva Pension"
  balance       REAL DEFAULT 0,          -- for cash/savings accounts: current balance in GBP
  currency      TEXT DEFAULT 'GBP',
  notes         TEXT,
  created_at    TEXT DEFAULT (datetime('now')),
  updated_at    TEXT DEFAULT (datetime('now'))
);

-- e.g. INSERT INTO accounts (id, provider, account_type, name, balance) VALUES
--   ('ig-isa',       'IG',         'isa',       'IG ISA',           0),
--   ('ig-shares',    'IG',         'shares',    'IG Share Dealing', 0),
--   ('ig-spreadbet', 'IG',         'spreadbet', 'IG Spread Betting', 10000),
--   ('aviva',        'Aviva',      'sipp',      'Aviva Pension',    0),
--   ('ajbell',       'AJ Bell',    'sipp',      'AJ Bell SIPP',     0),
--   ('nsandi',       'NS&I',       'savings',   'NS&I Premium Bonds', 15000),
--   ('cash-other',   'Other',      'cash',      'Cash & Savings',   25000);
```

### Update: `positions` table

Add `account_id` FK (nullable for existing positions):

```sql
ALTER TABLE positions ADD COLUMN account_id TEXT REFERENCES accounts(id);
```

### New: `spreadbet_positions` table

```sql
CREATE TABLE spreadbet_positions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id      TEXT NOT NULL REFERENCES accounts(id),  -- always 'ig-spreadbet'
  ticker          TEXT NOT NULL,
  direction       TEXT NOT NULL CHECK(direction IN ('long','short')),
  stake_per_point REAL NOT NULL,     -- £ per point
  entry_price     REAL NOT NULL,
  entry_date      TEXT NOT NULL,
  stop_price      REAL,
  target_price    REAL,
  current_price   REAL,
  pnl_gbp         REAL,
  notes           TEXT,
  status          TEXT DEFAULT 'open' CHECK(status IN ('open','closed')),
  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);
```

### New: `account_balances` history table

For cash/savings accounts, track balance changes over time:

```sql
CREATE TABLE account_balances (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  balance     REAL NOT NULL,
  date        TEXT NOT NULL,
  note        TEXT,
  created_at  TEXT DEFAULT (datetime('now'))
);
```

---

## Governance Changes

Single portfolio-wide rule set. Rules from `~/.tradingagents/governance.yaml` apply to the **total portfolio** (investable + deployed), not to individual accounts.

**Allocation rules:**
- Max single position: 15% of total portfolio
- Cash reserve minimum: 10% of total portfolio
- Max spread bet allocation: 20% of total portfolio (separate bucket)
- Max number of open positions: 24

**New governance checks:**
- `spreadbet_overexposure` — spread bet positions > 20% of total
- `cash_reserve_breach` — cash < 10% of portfolio
- `position_limit_breach` — > 24 open positions

**Per-account rules removed** from governance.yaml. All accounts share the same rules.

---

## New View: Portfolio Dashboard

Replaces the current Portfolio tab (or sits above it). Shows:

**1. Allocation bar**
```
[Spread Bet 20%] [Deployed 70%] [Cash 10%]
```
Each segment is a % of total portfolio. Live-computed from account balances + position values.

**2. Account summary table**

| Account | Type | Balance | Deployed | Notes |
|---|---|---|---|---|
| IG ISA | ISA | — | VWCE, AAPL | Real shares |
| IG Spread Bet | Spreadbet | £10,000 | £2,000 risk | 20% of total |
| Aviva Pension | SIPP | — | Mixed fund | Accumulating |
| AJ Bell SIPP | SIPP | — | Cash | SIPP pot |
| NS&I Premium Bonds | Savings | £15,000 | — | Manual balance |
| Cash | Cash | £25,000 | — | Bank + misc |

**3. Cash breakdown**
- Total cash: £50,000
- Reserve (10%): £7,143
- Spread bet allocation (20%): £14,286 — available for spread bets
- Investable: £28,571 — available for new positions

**4. Active positions** (existing positions table, enriched with account badge)

**5. Research queue** — watchlist filtered to `approved` stage → shows tickers ready to buy, sorted by priority

**6. Spread bet positions** (collapsed section)
- Shows open spread bets with live P&L
- Entry, stop, current price, P&L in GBP

**7. Governance summary**
- Current violations (if any)
- Allocation bar showing limits
- Rebalancing suggestions

---

## Entry Points

**Buying a position:**
1. Signal appears → user reviews in signals view
2. Position sizing calculated: `investable_cash × weight` (e.g. 10% of investable = £2,857)
3. User selects account (ISA / Shares / SIPP) — all equivalent for governance
4. Position created with `account_id` → appears in portfolio dashboard under that account
5. Exit plan created automatically

**Spread bet:**
1. Same signal → user decides spread bet vs. share
2. Stake calculated: `(1% of betting_bankroll) / (entry_price − stop_price)`
3. User enters spread bet details manually (or via IG API when available)
4. Position tracked in `spreadbet_positions` table

**Adding cash:**
- User updates account balance in the Portfolio Dashboard view
- Balance history tracked in `account_balances`
- Allocation recomputed

---

## Implementation Steps

**Step 1:** Create `accounts` table, seed with known accounts (IG ISA, IG Shares, IG Spreadbet, Aviva, AJ Bell, NS&I, cash)
**Step 2:** Add `account_id` to `positions` table, backfill with platform→account mapping
**Step 3:** Create `spreadbet_positions` table
**Step 4:** Create `account_balances` table
**Step 5:** Build Portfolio Dashboard view (allocation bar, account table, cash breakdown)
**Step 6:** Update governance engine with spread bet checks
**Step 7:** Wire the Dashboard into the existing layout (tabs)
**Step 8:** Add manual balance update form to Portfolio Dashboard
**Step 9:** (Future) IG API integration for live spread bet positions

---

## Notes

- All values in GBP throughout
- No need for API access to IG/AJ Bell/Aviva right now — balances are manual entry
- NS&I: update balance monthly or when interest is credited
- Research signals are the primary entry point — the dashboard's job is to track positions, not generate ideas (that's TradingAgents)
- Allocation is computed on demand from: sum of account balances + sum of position values
- Exit plans are per-position, not per-account

---

## Exit Criteria

- [ ] Accounts table with all 7 accounts seeded
- [ ] Positions linked to accounts via `account_id`
- [ ] Portfolio Dashboard shows allocation bar (spread bet / deployed / cash)
- [ ] Cash breakdown computed from account balances
- [ ] Spread bet positions table visible in Portfolio Dashboard
- [ ] Manual balance update works
- [ ] Governance checks apply portfolio-wide (not per-account)
- [ ] Research queue filtered to `approved` stage visible in Portfolio view