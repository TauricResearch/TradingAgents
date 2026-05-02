# Brief: TradingAgents Phase 3 — Portfolio Intelligence System

**Date:** 2026-05-02
**Status:** Proposed

## Context

Phase 1 delivered: Bun/Hono server, SQLite, SSE streaming, HTMX dashboard, AI analysis pipeline. Phase 2 was scoped as incremental UI improvements (price columns, markdown rendering).

After review, the scope is better expressed as a **complete portfolio intelligence system** with three layers:

```
Inventory (hLedger) ←→ Prospects (pipeline) ←→ Exits (active management)
                              ↓
                    Governance (risk, rebalance, benchmark)
                              ↓
                    Feedback (post-mortems, learning)
```

---

## Layer 1: Inventory — "What do I own?"

**Owner:** hLedger. We read, never write.

### 1.1 hLedger Integration
- `~/.hledger.journal` — single source of truth for accounts + transactions
- Price file on filesystem (not DB): `P 2026-05-02 TKA.DE €8.45` entries
- `just` facade for all operations:

```bash
just hl                    # current holdings summary
just hl prices             # price history
just hl update-prices      # hledger prices --auto (Yahoo Finance)
just hl add TICKER QTY PX  # record purchase
just hl allocation         # tree view with market values
```

### 1.2 Server Integration
- `server/lib/hledger.ts` — thin wrapper: `hledger balance --json --value` → parse
- `GET /api/holdings` — hLedger balances enriched with live price + P&L
- No price data in SQLite — redundant, gets out of sync
- SQLite stays focused on: signal history, analysis logs, session state

### 1.3 Cash as a Position
- Cash balances surfaced in dashboard (not hidden in hLedger output)
- Cash drag alert: "You're 40% cash, earning 0%. Money market at 4.2% costs €X/month"
- Currency breakdown if multi-currency

### 1.4 hLedger Playbook
- `playbooks/hledger-playbook.md` — journal conventions, account naming, price update workflow

**Dependencies:** hLedger 1.52 installed ✅
**Priority:** P1 (foundation for everything else)

---

## Layer 2: Prospects — "What should I look at?"

### 2.1 Watchlist Pipeline
- Existing watchlist table → upgrade to gated pipeline
- Stages: `researching` → `analyzed` → `candidate` → `approved` → `acquired`
- Each gate requires evidence: AI analysis report, thesis draft, risk assessment

### 2.2 AI Analysis on Demand
- "Analyze" button on any watchlist item → triggers TradingAgents SSE pipeline
- Results stored as analysis log + signal record
- Position context injected: "You currently hold X in this sector"

### 2.3 Prospect Dashboard
- Watchlist panel: ticker, stage, last signal, thesis summary, days in pipeline
- Filter by stage, priority, sector
- "Promote to position" → generates hLedger transaction template

**Dependencies:** Layer 1 (holdings feed sector context)
**Priority:** P1

---

## Layer 3: Exits — "When do I get out?"

### 3.1 Position Exit Plans
- YAML file per position: `~/.tradingagents/positions/TKA.DE.yaml`
- Captures: entry thesis, invalidation conditions, profit targets, time stop

```yaml
ticker: TKA.DE
entry_date: 2026-04-20
entry_price: 8.45
quantity: 500
thesis: "Industrial automation cycle turning"
invalidation:
  price: 7.20              # -15% hard stop
  thesis: "KONE delayed beyond Q3"
targets:
  - price: 10.50           # +24%, scale out 1/3
  - price: 12.00           # +42%, scale out another 1/3
time_stop: "2026-10-01"
notes: "Earnings catalyst Aug 15"
```

### 3.2 Exit Dashboard
- Per position: current P&L, distance to stop, distance to next target
- Thesis status indicator: AI monitors news for invalidation triggers
- Visual: progress bars to targets, warning when approaching stop
- Alert banner: "3 positions within 10% of stop loss"

### 3.3 Exit Execution
- "Exit position" button → generates hLedger sell transaction
- Partial exits supported (scale out N of M shares)
- Auto-log post-mortem template on exit

**Dependencies:** Layer 1 (hLedger for transaction recording)
**Priority:** P1

---

## Layer 4: Governance — "What are the rules?"

### 4.1 Portfolio Risk Rules
- Max single position: 15% of portfolio
- Max sector concentration: 30%
- Cash floor: 10%
- Max portfolio drawdown: 15% → go to 50% cash
- Dashboard shows violations in red

### 4.2 Rebalancing
- `just hl rebalance` → shows allocation drift vs. target
- Rule-based: "If position > 15%, trim to 12%. If sector > 30%, trim largest"
- Generates hLedger transaction templates, doesn't auto-execute

### 4.3 Benchmarking
- Track portfolio total return vs. benchmark (VWCE, S&P 500)
- Monthly snapshot: "Portfolio +12.3%, VWCE +8.1% → +4.2% alpha"
- Dashboard: simple line chart, rolling 3/6/12 month comparison

**Dependencies:** Layer 1 (holdings data for allocation calc)
**Priority:** P2

---

## Layer 5: Feedback — "Did we get it right?"

### 5.1 Exit Post-Mortems
- Triggered when position is exited (full or partial)
- Template captures:
  - Thesis: played out or not?
  - AI signal: was it correct?
  - Exit trigger: what caused the exit? (stop, target, time stop, manual)
  - Lesson: what would we do differently?

### 5.2 Signal Accuracy Tracking
- For each signal → eventual outcome (after exit)
- Metrics: % correct by signal type, avg return on buy signals, avg loss avoided on sell signals
- Dashboard: "AI accuracy: 67% (18/27 signals)"

### 5.3 Decision Journal
- Append-only log: why we bought, why we sold, what we learned
- Stored as markdown: `~/.tradingagents/decisions/YYYY-MM-DD-TICKER.md`
- Searchable, grep-friendly

**Dependencies:** Layer 3 (exit data), Layer 2 (signal history)
**Priority:** P3

---

## File Structure

```
~/.hledger.journal                    # accounts + transactions (user-managed)
~/.hledger/prices.journal             # price history (auto-updated)
~/.tradingagents/
├── positions/
│   └── TKA.DE.yaml                   # exit plan per position
├── decisions/
│   └── 2026-05-02-TKA.DE.md          # decision journal entries
├── post-mortems/
│   └── 2026-08-15-TKA.DE.md          # exit post-mortems
├── logs/                             # existing: AI analysis logs
└── portfolio.db                      # existing: signals, sessions, summaries

server/
├── lib/
│   ├── db.ts                         # existing: SQLite
│   ├── hledger.ts                    # NEW: hLedger subprocess wrapper
│   └── markdown.ts                   # existing
├── routes/
│   ├── holdings.ts                   # NEW: hLedger → JSON API
│   ├── portfolio.ts                  # existing (enrich with hLedger data)
│   ├── analysis.ts                   # existing
│   └── signals.ts                    # existing
└── views/
    ├── holdings.tsx                  # NEW: Holdings tab
    ├── prospects.tsx                 # NEW: Prospects pipeline
    └── exits.tsx                     # NEW: Exit dashboard
```

## `just` Facade Additions

```bash
just hl                              # holdings summary
just hl prices                       # price history
just hl update-prices                # fetch latest prices
just hl add TICKER QTY PX            # record purchase
just hl allocation                   # allocation tree
just hl rebalance                    # show drift vs. rules
just analyze TICKER                  # run AI analysis (existing)
just analyze-all                     # analyze all holdings + prospects
just summarize                       # generate summaries (existing)
```

## Success Criteria

1. `just hl` shows all holdings with live prices and P&L
2. Dashboard has three tabs: Holdings, Prospects, Exits
3. Each holding shows: current value, P&L, distance to stop, distance to target
4. Prospect pipeline shows stage, last AI signal, thesis status
5. Exit dashboard flags positions approaching stops or targets
6. Post-mortem generated on every exit
7. Signal accuracy visible on dashboard
8. All hLedger operations via `just` — no manual CLI needed

## Phased Delivery

| Phase | Deliverable | Effort | Priority |
|-------|------------|--------|----------|
| 3.1 | hLedger integration + `just hl` facade | 2-3 hrs | P1 |
| 3.2 | Holdings dashboard (live prices, P&L, allocation) | 3-4 hrs | P1 |
| 3.3 | Exit plans (YAML) + exit dashboard | 3-4 hrs | P1 |
| 3.4 | Prospects pipeline (watchlist → gates) | 3-4 hrs | P1 |
| 3.5 | Governance rules (risk, rebalance) | 2-3 hrs | P2 |
| 3.6 | Benchmarking (vs. passive) | 2-3 hrs | P2 |
| 3.7 | Feedback loop (post-mortems, accuracy) | 2-3 hrs | P3 |
| 3.8 | hLedger playbook | 30 min | P1 |

**Total estimated effort:** 18-26 hours across 8 deliverables
