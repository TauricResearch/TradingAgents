# Brief: Research Registry + Watchlist Seed

**Date:** 2026-05-15
**Status:** Open
**Epic ID:** RESEARCH-001
**PR:** #17 merged (WATCH-001 screening engine foundation)

---

## Objective

Populate the watchlist from research documents and build a canonical registry linking research sources to watchlist entries. The screening engine (WATCH-001, #17 merged) is in place — this brief fills it with actual data.

---

## Background

PR #17 merged `feat(WATCH-001): screening engine foundation — schema, CLI, data layer`. The infrastructure is complete:
- `watchlist` table with ticker, thesis, priority, stage
- `watchlist_enrichment` table for fundamental data
- `screening_rules` table for rule-based filtering
- `screening_screenings` table for run history

**What's missing:**
1. No research document registry — no canonical index of what research exists
2. No link between watchlist entries and source documents
3. Hormuz research (35KB, 2026-05-14) contains ~30 named stocks — none in watchlist
4. Current watchlist has 8 entries (GOOGL, META, AMZN, ASML, SAP, ARM, BTC, SOL) with zero research linkage and no relevance to the Hormuz theme

**The gap in one sentence:** The watchlist is a manual artifact disconnected from the research corpus.

---

## What Exists

| Asset | Status |
|-------|--------|
| `docs/Hormuz Bottleneck_ Recovery Stock Analysis.md` | 35KB, 2026-05-14, ~30 named stocks across 5 sectors |
| `briefs/` | 50+ briefs — project work, not investment research |
| `watchlist` table | Schema ready, 8 stale entries, no `research_doc` column |
| `watchlist_enrichment` table | Schema ready, empty |
| `screening_rules` table | Schema ready, empty |
| WATCH-001 (Epic) | Screening engine complete (#17) |

---

## Requirements

### R01: Research Registry Document

Create `docs/research-registry.md` — canonical index of all investment research documents.

```markdown
# Research Registry

| ID | Document | Date | Sector | Tickers | Status |
|----|----------|------|--------|---------|--------|
| hormuz-2026-05-14 | Hormuz Bottleneck Recovery Stock Analysis | 2026-05-14 | Energy, Materials, Defense | COP, FANG, LIN, APD, CF, LMT, ... | active |
```

Fields per entry: `id`, `document`, `date`, `sector`, `tickers`, `status`, `source_url`

- [ ] **R01.1:** Create `docs/research-registry.md` with index structure
- [ ] **R01.2:** Index the Hormuz doc (2026-05-14)
- [ ] **R01.3:** Add `research_date` field to track last update per research doc

### R02: Watchlist Schema Extension

Add `research_doc` and `last_research_update` columns to `watchlist` table.

```sql
ALTER TABLE watchlist ADD COLUMN research_doc TEXT;  -- FK to research-registry ID
ALTER TABLE watchlist ADD COLUMN last_research_update TEXT;  -- YYYY-MM-DD
```

- [ ] **R02.1:** Add `research_doc` TEXT column (nullable, links to registry ID)
- [ ] **R02.2:** Add `last_research_update` TEXT column (YYYY-MM-DD)
- [ ] **R02.3:** Migration script to apply safely (with rollback)
- [ ] **R02.4:** Update `prospects-db.ts` to surface the new fields

### R03: Seed Hormuz Stocks into Watchlist

Extract tickers from `docs/Hormuz Bottleneck_ Recovery Stock Analysis.md` and seed them.

| Ticker | Sector | Exchange | Priority | Stage | Thesis snippet |
|--------|--------|----------|----------|-------|----------------|
| COP | Upstream E&P | US | high | researching | Permian pure-play, Hormuz-free crude |
| FANG | Upstream E&P | US | high | researching | Delaware sub-basin, high oil beta |
| LIN | Industrial Gas | US | high | researching | Helium oligopoly, semiconductor exposure |
| APD | Industrial Gas | US | high | researching | 15-25yr take-or-pay contracts |
| CF | Fertilizer | US | high | researching | North American nitrogen, 33.5% margin |
| MOS | Fertilizer | US | medium | researching | Potash/phosphate, soybean demand shift |
| LMT | Defense | US | high | researching | $194B backlog, F-35 production doubling |
| RTX | Defense | US | high | researching | Patriot air defense, NATO demand |
| GD | Defense | US | medium | researching | Navy support ships, $65.8B contract |
| SHEL | Integrated Energy | UK | medium | researching | Global LNG dominant, 70+ countries |
| CVX | Integrated Energy | US | medium | researching | 3.9% yield, Libya entry, US footprint |
| BP | Integrated Energy | UK | medium | researching | 8.77 P/E, 75% EPS growth |

Key criteria (from Hormuz doc synthesis):
- North American asset density (avoid Gulf exposure)
- Pricing power in irreplaceable commodities
- Non-interdicted supply chains

- [ ] **R03.1:** Seed 12 Hormuz-recommended stocks with research linkage
- [ ] **R03.2:** Set `research_doc: 'hormuz-2026-05-14'` for all entries
- [ ] **R03.3:** Set `last_research_update: '2026-05-14'` for all entries
- [ ] **R03.4:** Retire or flag the 8 stale entries (GOOGL, META, AMZN, ASML, SAP, ARM, BTC, SOL) — either archive or require a research doc to stay active

### R04: Research Coverage View

CLI + dashboard view showing watchlist coverage by research doc.

```bash
trading research coverage

# Output:
# hormuz-2026-05-14 | 12 tickers | last updated: 2026-05-14
#   ┣ high priority:  COP, FANG, LIN, APD, CF, LMT, RTX
#   ┣ medium priority: MOS, SHEL, CVX, BP, GD
#   ┗ stale (no research): GOOGL, META, AMZN (flagged)
```

- [ ] **R04.1:** CLI `trading research coverage` command
- [ ] **R04.2:** Dashboard "Research Coverage" panel on Prospects tab
- [ ] **R04.3:** Staleness indicator: entries with `last_research_update > 90 days` flagged amber

---

## How to Verify

```bash
# Check watchlist after seeding
sqlite3 portfolio.db "SELECT ticker, research_doc, last_research_update FROM watchlist ORDER BY research_doc;"

# Run coverage
trading research coverage

# Verify Hormuz stocks in dashboard
open http://localhost:3000/prospects
```

---

## Dependencies

- `src/server/lib/schema.sql` — R02 schema change
- `src/server/lib/prospects-data.ts` — R02.4 field exposure
- `src/cli/commands/watchlist.ts` — extend for coverage command
- `docs/research-registry.md` — new file
- `docs/Hormuz Bottleneck_ Recovery Stock Analysis.md` — source of truth for tickers

---

## Exit Criteria

- Research registry document exists and is indexed
- Watchlist entries link to research docs via `research_doc` column
- All 12 Hormuz stocks seeded with proper linkage and timestamps
- Stale watchlist entries flagged or archived
- Research coverage view works in CLI and dashboard

---

## Not in Scope

- Automated research doc ingestion (manual indexing only)
- Enrichment of seeded stocks (deferred to WATCH-001 screening run)
- Deletion of stale watchlist entries (flag only, user decides)
- Research doc scraping or AI summarisation

---

## Opinion

**WATCH-001 built the machine. RESEARCH-001 puts fuel in it.**

The Hormuz doc is substantive — 35KB with sector analysis, valuation data, and a clear investment thesis. The 12 stocks it identifies (upstream E&P, industrial gas, fertilizer, defense, integrated energy) are coherent and thematically linked. This is a legitimate research corpus, not noise.

The current watchlist (GOOGL, META, etc.) predates the Hormuz research and has no linkage to it. Flagging these as "stale" (no research doc) is the right call — it forces a decision: either link them to a research source or archive them. Don't let the watchlist become a graveyard of undisciplined picks.

**Sequence:** Seed the 12 Hormuz stocks → build coverage view → run screening engine (WATCH-001 R03) → watchlist is live.