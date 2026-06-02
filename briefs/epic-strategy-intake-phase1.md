# Epic: Strategy Intake Pipeline — Phase 1

**Date:** 2026-05-30
**Epic ID:** STRAT-001
**Status:** Active
**Priority:** P1
**Stories:** STRAT-001-S01 through STRAT-001-S05
**Brief:** `briefs/brief-strategy-intake-pipeline.md`

---

## Vision

Give TradingAgents a first-class concept of a *trading strategy* — not just per-ticker analysis. Capture strategy ideas from external sources (books, papers, podcasts), label them with a standard framework, and store them as structured, testable entities. Phase 1 delivers the table and CLI for capture + AI extraction. Backtesting (Phase 2) and dashboard (Phase 3) follow.

**Core heuristic:** If you can't write it as a set of IF statements, it's not a strategy. It's a vibe.

---

## Background

TradingAgents already has per-ticker AI analysis (`trading analyze`), signals, screening, and benchmark comparison. What it doesn't have is a way to evaluate whether a *strategy rule set* — independent of any single ticker — has merit. This is the gap Murtazin's article highlights: the edge is never in the idea; it's in what you do after you find it.

Phase 1 is the capture layer. We build the table, the CLI, and the AI extraction command. No backtesting yet — that's Phase 2.

| Capability | Now | After Phase 1 |
|---|---|---|
| Store strategy rules | ❌ | `strategies` table + `trading strategy add` |
| Extract from sources | ❌ | `trading strategy extract --from-url` via LLM |
| List/search strategies | ❌ | `trading strategy list --status backtested` |
| View strategy detail | ❌ | `trading strategy show <id>` |
| Backtest | ❌ | Phase 2 (follow-up epic) |
| Dashboard view | ❌ | Phase 3 (follow-up epic) |

---

## Stories

### STRAT-001-S01: `strategies` table + `strategy_backtests` table

**What:** Add both tables to `schema.sql`.

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS strategies (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  source          TEXT,              -- book/paper/podcast URL/tweet URL
  source_type     TEXT CHECK(source_type IN ('book','paper','podcast','twitter','onchain','manual')),
  edge_type       TEXT CHECK(edge_type IN ('risk_premium','inefficiency','unknown')),
  market          TEXT,              -- 'equities','futures','crypto','options','forex'
  behaviour       TEXT CHECK(behaviour IN ('trend_following','mean_reversion','momentum','carry','arbitrage','other')),
  entry_rules     TEXT NOT NULL,     -- JSON: structured conditions
  exit_rules      TEXT NOT NULL,     -- JSON: target, stop, time-based, signal reversal
  position_sizing TEXT,              -- JSON: sizing method + params
  parameters      TEXT,              -- JSON: key parameters with defaults
  timeframe       TEXT,              -- '1d','1h','4h','1w'
  status          TEXT DEFAULT 'draft' CHECK(status IN ('draft','extracted','backtested','paper_trading','live','retired')),
  notes           TEXT,
  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
CREATE INDEX IF NOT EXISTS idx_strategies_edge_type ON strategies(edge_type);

CREATE TABLE IF NOT EXISTS strategy_backtests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id     TEXT NOT NULL REFERENCES strategies(id),
  start_date      TEXT NOT NULL,
  end_date        TEXT NOT NULL,
  is_oos          INTEGER DEFAULT 0,  -- 0 = in-sample, 1 = out-of-sample
  total_return    REAL,
  sharpe_ratio    REAL,
  max_drawdown    REAL,
  win_rate        REAL,
  num_trades      INTEGER,
  avg_hold_days   REAL,
  params_swept    TEXT,  -- JSON: which params were varied (if parameter sweep)
  created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_backtests_strategy ON strategy_backtests(strategy_id);
```

**Acceptance:**
- Both tables exist in `schema.sql` with correct CHECK constraints
- `DatabaseFactory` creates them on startup (existing `CREATE TABLE IF NOT EXISTS` pattern)
- `just check` passes (biome + tsc + DB gate)

**Estimate:** 0.25d

---

### STRAT-001-S02: `trading strategy add` — Manual entry

**What:** Interactive CLI command to add a strategy to the `strategies` table.

**Usage:**
```bash
# Interactive (prompts for each field)
trading strategy add

# Non-interactive (all flags at once)
trading strategy add \
  --name "RSI Mean Reversion" \
  --source "Quantitative Momentum, Gray & Vogel" \
  --source-type book \
  --edge-type risk_premium \
  --market equities \
  --behaviour mean_reversion \
  --entry-rules '{"indicator":"rsi_14","threshold":30,"confirmation":"close_above_open"}' \
  --exit-rules '{"target":"rsi_70","stop":"atr_14_x2","time_stop_days":20}'
```

**Fields to prompt (interactive):**
1. Name (required)
2. Source (optional, free text)
3. Source type (select: book/paper/podcast/twitter/onchain/manual)
4. Edge type (select: risk_premium/inefficiency/unknown)
5. Market (select: equities/futures/crypto/options/forex)
6. Behaviour (select: trend_following/mean_reversion/momentum/carry/arbitrage/other)
7. Entry rules (required, JSON — validate parse)
8. Exit rules (required, JSON — validate parse)
9. Position sizing (optional, JSON)
10. Parameters (optional, JSON — e.g. `{"rsi_period":14,"rsi_threshold":30}`)
11. Timeframe (optional, free text — e.g. `1d`)
12. Notes (optional)

**Acceptance:**
- Interactive mode prompts for each field with sensible defaults/skips
- Non-interactive mode accepts all fields as flags
- Entry rules and exit rules validate as parseable JSON (error if not)
- Generates a human-readable `id` (slug from name + timestamp, e.g. `rsi-mean-reversion-2026-05-30`)
- Status defaults to `draft`
- Prints confirmation with the generated ID

**Estimate:** 0.5d

---

### STRAT-001-S03: `trading strategy list` + `trading strategy show`

**What:** List and detail commands for stored strategies.

**Usage:**
```bash
# List all strategies
trading strategy list

# Filter by status or edge type
trading strategy list --status backtested
trading strategy list --edge-type risk_premium

# Show full detail for one strategy
trading strategy show rsi-mean-reversion-2026-05-30

# JSON output
trading strategy show rsi-mean-reversion-2026-05-30 --json
```

**List output format:**
```
STRATEGIES
═══════════════════════════════════════════════════════════════
ID                          Name              Edge Type      Status    Source
───────────────────────────────────────────────────────────────
rsi-mean-reversion-2026...  RSI Mean Rev...   risk_premium   draft     Quant. Momentum
momentum-cross-2026-05...   Momentum Cros...  risk_premium   extracted Value/Momentum Everywhere
spy-vix-spread-2026-05...   SPY-VIX Sprea...  inefficiency   draft     Podcast: Flirting w/ Models
```

**Show output format:**
- Full strategy definition with all fields
- Source attribution
- Status badge
- Created/updated timestamps

**Acceptance:**
- `trading strategy list` shows table of all strategies
- `trading strategy list --status backtested` filters correctly
- `trading strategy list --edge-type risk_premium` filters correctly
- `trading strategy show <id>` prints full detail
- `trading strategy show <id> --json` outputs machine-readable JSON
- Empty list shows helpful message: "No strategies yet. Run `trading strategy add` or `trading strategy extract`."

**Estimate:** 0.25d

---

### STRAT-001-S04: `trading strategy extract` — AI-powered extraction

**What:** Fetch external content (article, paper, transcript) via `defuddle` and use LLM to extract structured strategy rules into the framework template.

**Usage:**
```bash
# Extract from a URL (article, podcast transcript, paper)
trading strategy extract --from-url https://medium.com/...

# Extract from a local file (Markdown, plain text)
trading strategy extract --from-file ./natenberg-chapter-4.md

# Preview extraction without saving (dry run)
trading strategy extract --from-url https://... --dry-run
```

**Behaviour:**
1. Load content via `defuddle` (URL) or `readFile` (local)
2. Send to LLM with a prompt that includes:
   - The framework template: market, edge_type, behaviour, entry_rules, exit_rules, position_sizing, parameters, timeframe
   - Instructions to extract only what's explicitly stated; mark missing fields as `null`
   - A confidence score per field (0–1)
3. LLM returns structured JSON matching the `strategies` schema
4. Save as `draft` status (never `extracted` or higher)
5. Print the extracted strategy for human review

**LLM prompt skeleton:**
```
You are a trading strategy extraction tool. Given the following content, extract any trading strategy described into this JSON template:

{
  "name": "...",
  "market": "equities|futures|crypto|options|forex|null",
  "edge_type": "risk_premium|inefficiency|unknown",
  "behaviour": "trend_following|mean_reversion|momentum|carry|arbitrage|other",
  "entry_rules": { ... },
  "exit_rules": { ... },
  "position_sizing": { ... },
  "parameters": { ... },
  "timeframe": "...",
  "confidence": { "entry_rules": 0.8, "exit_rules": 0.6, ... }
}

Rules:
- Only extract what is EXPLICITLY stated. Do not invent rules.
- For any field you cannot determine, set it to null and give it confidence 0.
- Entry/exit rules must be specific enough to code as IF statements.
- If the content describes no clear strategy, return {"error": "no strategy found"}.
```

**Acceptance:**
- `trading strategy extract --from-url <url>` fetches content, extracts strategy, saves as draft
- `trading strategy extract --from-file <path>` works for local .md/.txt files
- LLM extraction returns structured JSON matching the schema
- Missing fields are `null`, not hallucinated
- Confidence scores included per field
- `--dry-run` prints extraction without saving
- If no strategy is found, prints "No actionable strategy found in this content"
- Uses existing LLM config (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` from `.env`) — same as `analyze`
- Saved strategy has `source_type` auto-set to the content type and `source` set to the URL/path

**Estimate:** 1d

---

### STRAT-001-S05: Register `strategy` command in CLI + `just check` green

**What:** Wire the new `strategy` command group into `src/cli/main.ts` and verify all gates pass.

**Changes:**
- `src/cli/commands/strategy.ts` — main command with `add`, `list`, `show`, `extract` subcommands
- `src/cli/main.ts` — add `strategy: () => import(...)` to `subCommands`

**Acceptance:**
- `trading strategy` shows help with all subcommands
- `trading strategy add` runs
- `trading strategy list` runs
- `trading strategy show <id>` runs
- `trading strategy extract --help` shows usage
- `just check` passes (biome lint + format + tsc + DB gate)
- `just typecheck` passes on CLI types

**Estimate:** 0.25d

---

## Execution Order

```
S01 (schema) → S02 (add) → S03 (list/show) → S04 (extract) → S05 (register + green)
        ↘                                    ↗
          └── can run in parallel ──────────┘
```

S04 (extract) depends on the table existing (S01) but is otherwise independent of the CLI commands (S02–S03). Can be built in parallel.

---

## Dependencies

| Dependency | Used by | Notes |
|---|---|---|
| `src/server/lib/schema.sql` | S01 | Add `strategies` + `strategy_backtests` tables |
| `src/server/lib/db.ts` | All | DatabaseFactory — existing pattern |
| `src/cli/commands/strategy.ts` | S02–S04 | New file, follows `screen.ts` pattern (command group + subcommands) |
| `src/cli/main.ts` | S05 | Register `strategy` subcommand |
| `defuddle` (web_fetch tool) | S04 | Content extraction from URLs |
| LLM provider (OpenAI/Anthropic) | S04 | Strategy extraction prompt — same config as `analyze` |
| `src/lib/settings.ts` | All | `cfg` for DB path, etc. |

---

## Exit Criteria

- [ ] S01: `strategies` + `strategy_backtests` tables in `schema.sql`; created on startup
- [ ] S02: `trading strategy add` works interactively and non-interactively
- [ ] S03: `trading strategy list` and `trading strategy show` work with filtering
- [ ] S04: `trading strategy extract --from-url` extracts + saves as `draft`
- [ ] S05: `trading strategy` registered in CLI; `just check` green
- [ ] At least one real strategy extracted from the Murtazin article (smoke test)
- [ ] Brief updated with Phase 1 completion notes

---

## Not in Scope (Phase 1)

- Backtesting engine (R03) — Phase 2
- Dashboard view (R04) — Phase 3
- Strategy-to-signal bridge (R05) — Phase 4 stretch
- Strategy status promotion workflow (stays manual via CLI for now)
- Parameter sensitivity sweep (part of backtesting engine)
- Correlation matrix (part of dashboard)
- Strategy decay tracking (part of dashboard)
- `trading strategy edit` / `trading strategy delete` / `trading strategy promote` — future convenience commands

---

## Related

- Brief: `briefs/brief-strategy-intake-pipeline.md` — full requirements and context
- Pattern: `src/cli/commands/screen.ts` — command group with subcommands (create/list/delete/run/enrich/sentiment)
- Pattern: `src/cli/commands/scan.ts` — single-purpose CLI command with flags
- Table: `src/server/lib/schema.sql` — existing schema patterns
- Epic: `briefs/epic-demo-execution-pipeline.md` — epic format reference
