# Iteration System Design

**Date:** 2026-04-07  
**Status:** Approved  
**Scope:** Generic iteration system — skills + folder structure for learn-improve-repeat cycles. Demonstrated with trading agent discovery mode but applicable to any iterative system.

---

## Problem

Improving the discovery pipeline requires three distinct feedback loops running at different cadences:

1. **Fast loop** — output quality: does the latest run produce specific, well-reasoned candidates?
2. **Slow loop** — P&L outcomes: did the picks actually work after 5–10+ trading days?
3. **Research loop** — strategy sourcing: are there techniques we haven't tried yet that could improve signal quality?

Currently there is no structured way to capture learnings across runs, trace code changes back to evidence, or proactively search for improvements. Knowledge lives in one-off plan docs and in memory.

---

## Solution

Two Claude Code skills + a versioned knowledge base in `docs/iterations/` + two GitHub Actions workflows that run the skills on a schedule and open PRs for review.

---

## Folder Structure

```
docs/iterations/
├── LEARNINGS.md                        ← master index, one-line per domain entry
├── scanners/
│   ├── options_flow.md
│   ├── insider_buying.md
│   ├── volume_accumulation.md
│   ├── reddit_dd.md
│   ├── reddit_trending.md
│   ├── semantic_news.md
│   ├── market_movers.md
│   ├── earnings_calendar.md
│   ├── analyst_upgrades.md
│   ├── technical_breakout.md
│   ├── sector_rotation.md
│   ├── ml_signal.md
│   ├── minervini.md
│   └── ... (one file per scanner)
├── pipeline/
│   └── scoring.md                      ← LLM scoring, confidence calibration, ranking
└── research/
    └── YYYY-MM-DD-<topic>.md           ← web research findings (append-only, dated)
```

Each scanner file captures both the implementation learnings and the underlying market thesis — no separate strategies folder since scanners and strategies are currently 1:1.

### Domain File Schema

Each file in `scanners/`, `strategies/`, and `pipeline/` follows this structure:

```markdown
# <Domain Name>

## Current Understanding
<!-- Best-current-knowledge summary. Updated in place when evidence is strong. -->

## Evidence Log
<!-- Append-only. Each entry dated. -->

### YYYY-MM-DD — <run or event>
- What was observed
- What it implies
- Confidence: low / medium / high

## Pending Hypotheses
<!-- Things to test in the next iteration. -->
- [ ] Hypothesis description
```

### LEARNINGS.md Schema

```markdown
# Learnings Index

| Domain | File | Last Updated | One-line Summary |
|--------|------|--------------|-----------------|
| options_flow | scanners/options_flow.md | 2026-04-07 | Call/put ratio <0.1 is reliable; premium filter working |
| ... | | | |
```

---

## Skill 1: `/iterate`

**Location:** project-local `.claude/skills/iterate.md`

### Trigger
- **Automated:** GitHub Actions cron, daily at 06:00 UTC (after overnight discovery runs settle)
- **Manual:** invoke `/iterate` at any time for an on-demand iteration cycle

### Steps

1. **Detect mode**
   - Scans `results/discovery/` for runs not yet reflected in learning files
   - Checks `data/positions/` for positions ≥5 days old with outcome data
   - Sets mode: `fast` (output quality only), `pl` (P&L outcomes), or `both`

2. **Load domain context**
   - Identifies which scanners produced candidates in the target runs
   - Reads the corresponding `docs/iterations/scanners/*.md` files
   - Reads `docs/iterations/LEARNINGS.md` for full index awareness

3. **Analyze**
   - *Fast mode:* scores signal quality — specificity of thesis, scanner noise rate, LLM confidence calibration, duplicate/redundant candidates
   - *P&L mode:* compares predicted outcome vs actual per scanner; flags scanners over/underperforming their stated confidence; computes hit rate per scanner

4. **Write learnings**
   - Appends to the evidence log in each relevant domain file
   - Updates "Current Understanding" section if confidence in the new evidence is medium or higher
   - Updates `LEARNINGS.md` index with new last-updated date and revised one-liner

5. **Implement changes**
   - Translates learnings into concrete code changes: scanner thresholds, priority logic, LLM prompt wording, scanner enable/disable
   - In automated mode: implements without confirmation gate
   - In manual mode: presents diff for approval before writing

6. **Commit + rolling PR**
   - Checks for an existing open PR with branch prefix `iterate/current`
   - If one exists: pushes new commits onto that branch, updates PR description with the latest findings appended
   - If none exists: creates branch `iterate/current`, opens a new PR against `main`
   - Commit message format: `learn(iterate): <date> — <one-line summary of key finding>`
   - In manual mode: commits directly to current branch (no PR unless on `main`)
   - On merge: next run automatically opens a fresh PR

### Output
At most one open `iterate/current` PR at any time. It accumulates daily learnings until merged. Merging resets the cycle.

Human reviews PR, merges or closes. No code reaches `main` unreviewed.

---

## Skill 2: `/research-strategy`

**Location:** project-local `.claude/skills/research-strategy.md`

### Trigger
- **Automated:** GitHub Actions cron, weekly on Monday at 07:00 UTC
- **Manual:** `/research-strategy` (autonomous) or `/research-strategy "<topic>"` (directed)

### Two Modes

#### Directed mode: `/research-strategy "<topic>"`
User names the topic. Skill goes deep on that specific strategy.

#### Autonomous mode: `/research-strategy`
No topic given. Skill drives its own research agenda based on current weak spots.

### Steps

1. **Set agenda**
   - *Directed:* topic is given
   - *Autonomous:* reads `LEARNINGS.md` + domain files to identify: low-confidence scanners, pending hypotheses marked for research, gaps in pipeline coverage. Generates 3–5 research topics ranked by potential impact.

2. **Search**
   Searches across the default source list:
   - **Reddit:** r/algotrading, r/quant, r/investing
   - **Blogs:** QuantifiedStrategies, Hacker News (hn.algolia.com), CSS Analytics, Alpha Architect
   - **GitHub:** search for quant/scanner/screener repos with recent activity
   - **Academic:** SSRN quantitative finance, arXiv q-fin
   - **Archives:** Quantopian community notebooks (via GitHub mirrors)

   For each source: looks for signal definition, entry/exit criteria, known edge, known failure modes, data requirements.

3. **Cross-reference**
   - Checks existing `docs/iterations/` files for overlap with already-implemented or already-discarded approaches
   - Flags redundancy explicitly ("this is a variant of our existing volume_accumulation scanner")

4. **Evaluate fit**
   Scores each finding on four dimensions:
   - **Data availability** — do we already have the required data source?
   - **Implementation complexity** — hours estimate: trivial / moderate / large
   - **Signal uniqueness** — how much does it overlap with existing scanners?
   - **Evidence quality** — backtested with stats / qualitative analysis / anecdotal

5. **Write research files**
   - Saves findings to `docs/iterations/research/YYYY-MM-DD-<topic>.md` for all findings
   - Adds entries to `LEARNINGS.md`

6. **Implement and rolling PR**
   - In automated mode: implements the top-ranked finding automatically (score threshold: data availability = present, evidence quality ≥ qualitative, complexity ≤ moderate)
   - In manual directed mode: presents ranked findings, implements user-selected one
   - Checks for an existing open PR with branch prefix `research/current`
   - If one exists: pushes new commits onto that branch, updates PR description with new findings appended
   - If none exists: creates branch `research/current`, opens a new PR against `main`
   - Commits: `research(<topic>): add <scanner-name> scanner — <one-line rationale>`
   - On merge: next run automatically opens a fresh PR

### Safety threshold for autonomous implementation
Only auto-implement if ALL of:
- Required data source already integrated (no new API keys needed)
- Complexity estimate: trivial or moderate
- Signal uniqueness score: low overlap with existing scanners
Otherwise: commits research files only, opens PR flagged `needs-review` with explanation of why auto-implementation was skipped.

---

## Generic Applicability

The skill logic is domain-agnostic. To apply this system to a non-trading iterative project:

1. Replace `results/discovery/` with the project's run output directory
2. Replace `data/positions/` with whatever measures outcome quality
3. Replace the scanner domain files with the project's equivalent components
4. Replace the research source list with domain-appropriate sources

The folder structure and skill steps are unchanged.

---

## GitHub Actions Workflows

### `.github/workflows/iterate.yml`
```
schedule: cron '0 6 * * *'   # daily at 06:00 UTC
```
- Checks out repo
- Runs Claude Code with `/iterate` skill non-interactively
- Uses `ANTHROPIC_API_KEY` secret
- Creates branch `iterate/YYYY-MM-DD`, commits, opens PR

### `.github/workflows/research-strategy.yml`
```
schedule: cron '0 7 * * 1'   # weekly, Monday at 07:00 UTC
```
- Same setup as above, runs `/research-strategy` (autonomous mode)
- Creates branch `research/YYYY-MM-DD`, commits, opens PR
- If safety threshold not met: opens PR with `needs-review` label, no code changes

### Required secrets
- `ANTHROPIC_API_KEY` — Claude API access
- `GH_TOKEN` — PAT with `repo` scope for branch creation and PR opening

---

## Non-Goals

- No auto-merge — all PRs require human review before reaching `main`
- No dashboard or UI — all output is markdown + git commits
- No cross-project knowledge sharing — each project's `docs/iterations/` is independent
