# Playbook: hLedger — Asset Accounting

**Principle:** hLedger owns the accounting data. We read, never write.

---

## Journal File

**Location:** `~/.hledger.journal` (or set `$HLEDGER_FILE`)

### Account Naming

```
Assets:Broker:Cash          # cash balances (EUR, USD, etc.)
Assets:Broker:TICKER        # holdings — quote commodity if it contains dots
Equity:Opening-Balances     # initial balances
Expenses:Fees               # broker commissions
Income:Dividends            # dividend income
```

### Commodity Quoting

Ticker symbols with dots **must be quoted**:

```
# ✗ WRONG — hLedger rejects dots in unquoted commodities
  Assets:Broker:TKA.DE               500 TKA.DE

# ✓ RIGHT — quotes required for TKA.DE, BRK.B, etc.
  Assets:Broker:TKA.DE               500 "TKA.DE"
```

### Adding a Transaction

```
2026-04-20 Buy TKA.DE
  Assets:Broker:TKA.DE               500 "TKA.DE"
  Assets:Broker:Cash               -4225 EUR          @ 8.45 EUR
  Expenses:Fees                       10 EUR
```

The `@ 8.45 EUR` records the per-share price. hLedger computes total cost (500 × 8.45 = 4225).

### Recording Dividends

```
2026-06-15 TKA.DE dividend
  Assets:Broker:Cash                  250 EUR
  Income:Dividends                   -250 EUR
```

### Selling (Partial Exit)

```
2026-08-15 Sell 1/3 TKA.DE @ target 1
  Assets:Broker:Cash                3500 EUR          @ 10.50 EUR
  Assets:Broker:TKA.DE              -166 "TKA.DE"
  Income:Capital-Gains              -1341 EUR         ; realized gain
```

### Price Directives

Price file: `~/.hledger/prices.journal`

```
P 2026-05-02 "TKA.DE" 9.20 EUR
P 2026-05-02 AAPL 189.50 USD
P 2026-05-02 EUR 1.08 USD
```

Update prices manually or via `just hl-update-prices` (hLedger fetches from Yahoo Finance).

---

## `just` Commands

| Command | What it does |
|---------|-------------|
| `just hl` | Holdings summary with market values |
| `just hl-prices` | Show price history |
| `just hl-update-prices` | Fetch latest prices from Yahoo Finance |
| `just hl-allocation` | Allocation tree by account (depth 3) |
| `just hl-register TICKER` | Full transaction history for a ticker |
| `just hl-net-worth` | Net worth over time (monthly) |

---

## Dashboard Integration

The server reads hLedger via `server/lib/hledger.ts`:

- `GET /api/holdings` → holdings (ticker, qty, cost basis) + cash balances
- `GET /api/holdings/prices` → price history
- `GET /api/holdings/allocation` → human-readable allocation tree

No price data is stored in SQLite. hLedger is the single source of truth.

---

## Common Workflows

### New Position

1. Add transaction to journal: `just hl` to verify
2. Create exit plan: `~/.tradingagents/positions/TICKER.yaml`
3. (Optional) Add to prospects pipeline via dashboard

### Price Update

```bash
just hl-update-prices    # fetches from Yahoo Finance, appends to journal
```

Or manually add price directives to the journal file.

### Check Allocation

```bash
just hl-allocation
```

Shows each account's percentage of total portfolio value.

### Audit a Ticker

```bash
just hl-register TKA.DE
```

Shows every transaction affecting TKA.DE with running balance.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `unexpected '.'` | Unquoted commodity with dot | Use `"TKA.DE"` not `TKA.DE` |
| `unbalanced transaction` | Postings don't sum to zero | Add a balancing account (usually Cash or Equity) |
| Holdings show 0 quantity | Wrong account name or commodity mismatch | Check exact spelling in `just hl-register` |
| Dashboard shows empty holdings | Wrong `HLEDGER_FILE` path | Set env var or use default `~/.hledger.journal` |

---

## Related

- [Git Workflow](git-workflow-playbook.md) — dev → review → merge process
- [Brief: Portfolio Intelligence](../briefs/brief-portfolio-intelligence-2026-05-02.md) — Phase 3 plan
