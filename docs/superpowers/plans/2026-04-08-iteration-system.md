# Iteration System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-improving iteration system with two Claude Code commands (`/iterate`, `/research-strategy`) backed by a versioned knowledge base and two GitHub Actions workflows that run them daily/weekly and open rolling PRs.

**Architecture:** A `docs/iterations/` knowledge base stores per-scanner learnings in domain files. Two `.claude/commands/` files define the skill behavior. Two GitHub Actions workflows invoke Claude non-interactively, then handle branch/PR management externally so Claude's job is analysis + file writing only.

**Tech Stack:** Claude Code CLI (`claude -p`), GitHub Actions, `gh` CLI, Python (existing), Markdown knowledge base

---

## File Map

**Create:**
- `docs/iterations/LEARNINGS.md` — master index tracking last-analyzed run per scanner
- `docs/iterations/scanners/options_flow.md` — options flow scanner learnings
- `docs/iterations/scanners/insider_buying.md` — insider buying scanner learnings
- `docs/iterations/scanners/volume_accumulation.md` — volume accumulation scanner learnings
- `docs/iterations/scanners/reddit_dd.md` — reddit DD scanner learnings
- `docs/iterations/scanners/reddit_trending.md` — reddit trending scanner learnings
- `docs/iterations/scanners/semantic_news.md` — semantic news scanner learnings
- `docs/iterations/scanners/market_movers.md` — market movers scanner learnings
- `docs/iterations/scanners/earnings_calendar.md` — earnings calendar scanner learnings
- `docs/iterations/scanners/analyst_upgrades.md` — analyst upgrades scanner learnings
- `docs/iterations/scanners/technical_breakout.md` — technical breakout scanner learnings
- `docs/iterations/scanners/sector_rotation.md` — sector rotation scanner learnings
- `docs/iterations/scanners/ml_signal.md` — ML signal scanner learnings
- `docs/iterations/scanners/minervini.md` — Minervini scanner learnings
- `docs/iterations/pipeline/scoring.md` — LLM scoring and ranking learnings
- `.claude/commands/iterate.md` — `/iterate` Claude Code command
- `.claude/commands/research-strategy.md` — `/research-strategy` Claude Code command
- `.github/workflows/iterate.yml` — daily cron workflow
- `.github/workflows/research-strategy.yml` — weekly cron workflow

**Modify:** none — purely additive

---

## Task 1: Create Knowledge Base Folder Structure

**Files:**
- Create: `docs/iterations/LEARNINGS.md`
- Create: `docs/iterations/scanners/*.md` (13 files)
- Create: `docs/iterations/pipeline/scoring.md`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p docs/iterations/scanners docs/iterations/pipeline docs/iterations/research
```

- [ ] **Step 2: Create LEARNINGS.md**

```bash
cat > docs/iterations/LEARNINGS.md << 'EOF'
# Learnings Index

**Last analyzed run:** _(none yet — will be set by first /iterate run)_

| Domain | File | Last Updated | One-line Summary |
|--------|------|--------------|-----------------|
| options_flow | scanners/options_flow.md | — | No data yet |
| insider_buying | scanners/insider_buying.md | — | No data yet |
| volume_accumulation | scanners/volume_accumulation.md | — | No data yet |
| reddit_dd | scanners/reddit_dd.md | — | No data yet |
| reddit_trending | scanners/reddit_trending.md | — | No data yet |
| semantic_news | scanners/semantic_news.md | — | No data yet |
| market_movers | scanners/market_movers.md | — | No data yet |
| earnings_calendar | scanners/earnings_calendar.md | — | No data yet |
| analyst_upgrades | scanners/analyst_upgrades.md | — | No data yet |
| technical_breakout | scanners/technical_breakout.md | — | No data yet |
| sector_rotation | scanners/sector_rotation.md | — | No data yet |
| ml_signal | scanners/ml_signal.md | — | No data yet |
| minervini | scanners/minervini.md | — | No data yet |
| pipeline/scoring | pipeline/scoring.md | — | No data yet |
EOF
```

- [ ] **Step 3: Create scanner domain files**

Create each of the 13 scanner files using this template. Fill in the "Current Understanding" section with what is already known from prior work. Run this for each scanner:

**`docs/iterations/scanners/options_flow.md`:**
```markdown
# Options Flow Scanner

## Current Understanding
Scans for unusual options volume relative to open interest using Tradier API.
Call/put volume ratio below 0.1 is a reliable bullish signal when combined with
premium >$25K. The premium filter is configured but must be explicitly applied.
Scanning only the nearest expiration misses institutional positioning in 30+ DTE
contracts — scanning up to 3 expirations improves signal quality.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does scanning 3 expirations vs 1 meaningfully change hit rate?
- [ ] Is moneyness (ITM vs OTM) a useful signal filter?
```

**`docs/iterations/scanners/insider_buying.md`:**
```markdown
# Insider Buying Scanner

## Current Understanding
Scrapes SEC Form 4 filings. CEO/CFO purchases >$100K are the most reliable signal.
Cluster detection (2+ insiders buying within 14 days) historically a high-conviction
setup. Transaction details (name, title, value) must be preserved from scraper output
and included in candidate context — dropping them loses signal clarity.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does cluster detection (2+ insiders in 14 days) outperform single-insider signals?
- [ ] Is there a minimum transaction size below which signal quality degrades sharply?
```

**`docs/iterations/scanners/volume_accumulation.md`:**
```markdown
# Volume Accumulation Scanner

## Current Understanding
Detects stocks with volume >2x average. Key weakness: cannot distinguish buying from
selling — high volume on a down day is distribution, not accumulation. Multi-day mode
(3 of last 5 days >1.5x) is more reliable than single-day spikes. Price-change filter
(<3% absolute move) isolates quiet accumulation from momentum chasing.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does adding a price-direction filter (volume + flat/up price) improve hit rate?
- [ ] Is 3-of-5-day accumulation a stronger signal than single-day 2x volume?
```

**`docs/iterations/scanners/reddit_dd.md`:**
```markdown
# Reddit DD Scanner

## Current Understanding
Scans r/investing, r/stocks, r/wallstreetbets for DD posts. LLM quality score is
computed but not used for filtering — using it (80+ = HIGH, 60-79 = MEDIUM, <60 = skip)
would reduce noise. Subreddit weighting matters: r/investing posts are more reliable
than r/pennystocks. Post title and LLM score should appear in candidate context.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does filtering by LLM quality score >60 meaningfully reduce false positives?
- [ ] Does subreddit weighting change hit rates?
```

**`docs/iterations/scanners/reddit_trending.md`:**
```markdown
# Reddit Trending Scanner

## Current Understanding
Tracks mention velocity across subreddits. 50+ mentions in 6 hours = HIGH priority.
20-49 = MEDIUM. Mention count should appear in context ("47 mentions in 6hrs").
Signal is early-indicator oriented — catches momentum before price moves.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does mention velocity (rate of increase) outperform raw mention count?
```

**`docs/iterations/scanners/semantic_news.md`:**
```markdown
# Semantic News Scanner

## Current Understanding
Currently regex-based extraction, not semantic. Headline text is not included in
candidate context — the context just says "Mentioned in recent market news" which
is not informative. Catalyst classification from headline keywords (upgrade/FDA/
acquisition/earnings) would improve LLM scoring quality significantly.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Would embedding-based semantic matching outperform keyword regex?
- [ ] Does catalyst classification (FDA vs earnings vs acquisition) affect hit rate?
```

**`docs/iterations/scanners/market_movers.md`:**
```markdown
# Market Movers Scanner

## Current Understanding
Finds stocks that have already moved significantly. This is a reactive scanner —
it identifies momentum after it starts rather than predicting it. Useful for
continuation plays but not for early-stage entry. Best combined with volume
confirmation to distinguish breakouts from spikes.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Is a volume confirmation filter (>1.5x average) useful for filtering out noise?
```

**`docs/iterations/scanners/earnings_calendar.md`:**
```markdown
# Earnings Calendar Scanner

## Current Understanding
Identifies stocks with earnings announcements in the next N days. Pre-earnings
setups work best when combined with options flow (IV expansion) or insider activity.
Standalone earnings calendar signal is too broad — nearly every stock has earnings
quarterly.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does requiring options confirmation alongside earnings improve signal quality?
```

**`docs/iterations/scanners/analyst_upgrades.md`:**
```markdown
# Analyst Upgrades Scanner

## Current Understanding
Detects analyst upgrades/price target increases. Most reliable when upgrade comes
from a top-tier firm (Goldman, Morgan Stanley, JPMorgan) and represents a meaningful
target increase (>15%). Short squeeze potential (high short interest) combined with
an upgrade is a historically strong setup.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does analyst tier (BB firm vs boutique) predict upgrade quality?
- [ ] Does short interest >20% combined with an upgrade produce outsized moves?
```

**`docs/iterations/scanners/technical_breakout.md`:**
```markdown
# Technical Breakout Scanner

## Current Understanding
Detects price breakouts above key resistance levels on above-average volume.
Minervini-style setups (stage 2 uptrend, tight base, volume-confirmed breakout)
tend to have the highest follow-through rate. False breakouts are common without
volume confirmation (>1.5x average on breakout day).

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does requiring volume confirmation on the breakout day reduce false positives?
```

**`docs/iterations/scanners/sector_rotation.md`:**
```markdown
# Sector Rotation Scanner

## Current Understanding
Detects money flowing between sectors using relative strength analysis. Most useful
as a macro filter rather than a primary signal — knowing which sectors are in favor
improves conviction in scanner candidates from those sectors. Standalone sector
rotation signals are too broad for individual stock selection.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Can sector rotation data be used as a multiplier on other scanner scores?
```

**`docs/iterations/scanners/ml_signal.md`:**
```markdown
# ML Signal Scanner

## Current Understanding
Uses a trained ML model to predict short-term price movement probability. Current
threshold of 35% win probability is worse than a coin flip — the model needs
retraining or the threshold needs raising to 55%+ to be useful. Signal quality
depends heavily on feature freshness; stale features degrade performance.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does raising the threshold to 55%+ improve precision at the cost of recall?
- [ ] Would retraining on the last 90 days of recommendations improve accuracy?
```

**`docs/iterations/scanners/minervini.md`:**
```markdown
# Minervini Scanner

## Current Understanding
Implements Mark Minervini's SEPA (Specific Entry Point Analysis) criteria: stage 2
uptrend, price above 50/150/200 SMA in the right order, 52-week high proximity,
RS line at new highs. Historically one of the highest-conviction scanner setups.
Works best in bull market conditions; underperforms in choppy/bear markets.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Does adding a market condition filter (S&P 500 above 200 SMA) improve hit rate?
```

- [ ] **Step 4: Create pipeline/scoring.md**

```bash
cat > docs/iterations/pipeline/scoring.md << 'EOF'
# Pipeline Scoring & Ranking

## Current Understanding
LLM assigns a final_score (0-100) and confidence (1-10) to each candidate.
Score and confidence are correlated but not identical — a speculative setup
can score 80 with confidence 6. The ranker uses final_score as primary sort key.
No evidence yet on whether confidence or score is a better predictor of outcomes.

## Evidence Log
_(populated by /iterate runs)_

## Pending Hypotheses
- [ ] Is confidence a better outcome predictor than final_score?
- [ ] Does score threshold (e.g. only surface candidates >70) improve hit rate?
EOF
```

- [ ] **Step 5: Verify structure**

```bash
find docs/iterations -type f | sort
```

Expected output: 16 files (LEARNINGS.md + 13 scanner files + scoring.md + research dir exists)

- [ ] **Step 6: Commit**

```bash
git add docs/iterations/
git commit -m "feat(iteration-system): add knowledge base folder structure with seeded scanner files"
```

---

## Task 2: Write the `/iterate` Command

**Files:**
- Create: `.claude/commands/iterate.md`

- [ ] **Step 1: Create `.claude/commands/` directory**

```bash
mkdir -p .claude/commands
```

- [ ] **Step 2: Write iterate.md**

Create `.claude/commands/iterate.md` with this exact content:

```markdown
# /iterate

Analyze recent discovery runs and P&L outcomes, update learning files in
`docs/iterations/`, implement concrete code improvements in `tradingagents/`,
then commit everything. In CI (`CI=true`), stop before git operations — the
workflow handles branching and PR creation.

---

## Step 1: Determine What to Analyze

Read `docs/iterations/LEARNINGS.md` to find the **Last analyzed run** date.

Then scan `results/discovery/` for all run directories with dates AFTER the
last analyzed date. Each run directory contains `discovery_result.json` and
`tool_execution_logs.json`. Collect all unanalyzed runs.

Also scan `data/recommendations/` for JSON files dated 5 or more days ago.
Load each file and extract recommendations where `status != "open"` OR where
`discovery_date` is 5+ days in the past (these have had time to play out).
For P&L analysis you need: `ticker`, `strategy_match`, `final_score`,
`confidence`, `discovery_date`, `entry_price`, `status`.

Set your analysis mode:
- If unanalyzed runs exist → include **fast-loop** (output quality analysis)
- If mature recommendations exist → include **P&L loop** (outcome analysis)
- If neither → print "No new data to analyze since last run." and exit.

## Step 2: Load Domain Context

For each scanner that appears in the unanalyzed runs (check `strategy_match`
field in discovery results), read the corresponding file from
`docs/iterations/scanners/<scanner_name>.md`.

Also read `docs/iterations/pipeline/scoring.md`.
Also read `docs/iterations/LEARNINGS.md` for full index awareness.

## Step 3: Analyze

### Fast-Loop Analysis (output quality)
For each unanalyzed run's `discovery_result.json`:
- **Signal specificity**: Does each candidate have a concrete, specific thesis
  or a generic one? Flag candidates with vague context.
- **Scanner noise rate**: How many candidates per scanner? Scanners producing
  10+ candidates with low scores (<65) are noisy.
- **Confidence calibration**: Is confidence (1-10) consistent with score (0-100)?
  A score of 85 with confidence 5 suggests miscalibration.
- **Duplicate candidates**: Same ticker appearing from 2+ scanners — note as
  confluence (positive) or redundancy (negative, if identical thesis).

### P&L Loop Analysis (outcome analysis)
For each mature recommendation:
- Group by `strategy_match` (scanner). Compute per-scanner: hit rate (status
  reflects outcome — check what non-"open" statuses mean in the data).
- Flag scanners where final_score > 80 but outcomes are poor — overconfident.
- Flag scanners where final_score < 65 but outcomes are good — undervalued.
- Note patterns: do high-confidence (9-10) picks outperform low-confidence (6-7)?

## Step 4: Write Learnings

For each scanner that appeared in the analysis, update its domain file in
`docs/iterations/scanners/<scanner_name>.md`:

1. **Append to Evidence Log**: Add a dated entry with your specific observations.
   Include: what was observed, what it implies, confidence (low/medium/high).
2. **Update Current Understanding**: If your new evidence is medium or high
   confidence AND contradicts or meaningfully extends the current understanding,
   rewrite that section. Otherwise leave it unchanged.
3. **Update Pending Hypotheses**: Check off any hypotheses that are now answered.
   Add new ones that your analysis surfaced.

Update `docs/iterations/LEARNINGS.md`:
- Set **Last analyzed run** to today's date
- Update the one-line summary and Last Updated date for each scanner you touched

## Step 5: Implement Code Changes

Based on your learnings, identify concrete improvements. For each improvement:

**Translate one learning → one code change.** Examples:
- "ML signal threshold is worse than a coin flip" → raise threshold in
  `tradingagents/dataflows/discovery/scanners/ml_signal.py`
- "Options flow premium filter is configured but not applied" → add the check
- "Reddit DD LLM score computed but unused" → use it for priority assignment

For each change:
1. Read the relevant scanner file to understand current implementation
2. Make the minimal change that encodes the learning
3. Do not refactor surrounding code — change only what the learning motivates

Implement all changes before committing.

## Step 6: Commit (skip if CI=true)

If the environment variable `CI` is set, stop here. The workflow handles git.

Otherwise:
```bash
git add docs/iterations/ tradingagents/
git commit -m "learn(iterate): $(date +%Y-%m-%d) — <one-line summary of key findings>"
```

Then check for an existing open PR on branch `iterate/current`:
```bash
EXISTING=$(gh pr list --head iterate/current --state open --json number --jq '.[0].number // empty')
```

If one exists: push to that branch and update its description with your findings.
If none exists: create branch `iterate/current`, push, open PR against `main`.
```
```

- [ ] **Step 3: Verify the command is discoverable**

```bash
ls .claude/commands/
```

Expected: `iterate.md`

- [ ] **Step 4: Smoke-test the command manually**

In a Claude Code session in this project, type `/iterate` and verify Claude reads
the command and starts executing Step 1 (reads LEARNINGS.md, scans results/).
You don't need to let it complete — just confirm it picks up the command file.

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/iterate.md
git commit -m "feat(iteration-system): add /iterate Claude Code command"
```

---

## Task 3: Write the `/research-strategy` Command

**Files:**
- Create: `.claude/commands/research-strategy.md`

- [ ] **Step 1: Write research-strategy.md**

Create `.claude/commands/research-strategy.md` with this exact content:

```markdown
# /research-strategy

Research new trading strategies or scanner improvements, evaluate fit against
the existing pipeline, write findings to `docs/iterations/research/`, and
implement the top-ranked finding as a new scanner if it qualifies.

Usage:
- `/research-strategy` — autonomous mode: Claude picks research topics
- `/research-strategy "topic"` — directed mode: research a specific strategy

In CI (`CI=true`), stop before git operations — the workflow handles them.

---

## Step 1: Set Research Agenda

**If a topic argument was provided** (`$ARGUMENTS` is not empty):
- Research topic = `$ARGUMENTS`
- Skip to Step 2.

**Autonomous mode** (no argument):
- Read `docs/iterations/LEARNINGS.md` and all scanner domain files in
  `docs/iterations/scanners/`
- Identify the 3-5 highest-leverage research opportunities:
  - Scanners with low-confidence current understanding
  - Pending hypotheses marked with `- [ ]`
  - Gaps: signal types with no current scanner (e.g. dark pool flow,
    short interest changes, institutional 13F filings)
- Rank by potential impact. Pick the top topic to research this run.
- Print your agenda: "Researching: <topic> — Reason: <why this was prioritized>"

## Step 2: Search

Search the following sources for the research topic. For each source, look for:
signal definition, entry/exit criteria, known statistical edge, known failure
modes, data requirements.

**Sources to search:**
- Reddit: r/algotrading, r/quant, r/investing (site:reddit.com)
- QuantifiedStrategies (site:quantifiedstrategies.com)
- Alpha Architect (site:alphaarchitect.com)
- CSS Analytics (site:cssanalytics.wordpress.com)
- Hacker News (hn.algolia.com query)
- GitHub: search "quant scanner <topic>" and "trading strategy <topic>"
- SSRN: search quantitative finance papers on the topic
- arXiv q-fin section

Use WebSearch and WebFetch to retrieve actual content. Read at least 3-5
distinct sources before forming a conclusion.

## Step 3: Cross-Reference Existing Knowledge

Check `docs/iterations/scanners/` and `docs/iterations/research/` for any
prior work on this topic. Flag explicitly if this overlaps with:
- An existing scanner (name it)
- A previously researched and discarded approach (cite the research file)
- A pending hypothesis in an existing scanner file

## Step 4: Evaluate Fit

Score the finding on four dimensions (each: ✅ pass / ⚠️ partial / ❌ fail):

1. **Data availability**: Is the required data source already integrated in
   `tradingagents/dataflows/`? Check for existing API clients.
2. **Implementation complexity**: trivial (<2 hours) / moderate (2-8 hours) /
   large (>8 hours)
3. **Signal uniqueness**: Low overlap with existing scanners = good.
   High overlap = flag as redundant.
4. **Evidence quality**: backtested with statistics / qualitative analysis /
   anecdotal only

**Auto-implement threshold** (all must pass for autonomous CI implementation):
- Data availability: ✅ (data source already integrated)
- Complexity: trivial or moderate
- Uniqueness: low overlap
- Evidence: qualitative or better

## Step 5: Write Research File

Save findings to `docs/iterations/research/$(date +%Y-%m-%d)-<topic-slug>.md`:

```markdown
# Research: <Topic>

**Date:** YYYY-MM-DD
**Mode:** directed | autonomous

## Summary
<2-3 sentences on what was found>

## Sources Reviewed
- <source 1 with key finding>
- <source 2 with key finding>
...

## Fit Evaluation
| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅/⚠️/❌ | ... |
| Complexity | trivial/moderate/large | ... |
| Signal uniqueness | low/medium/high overlap | ... |
| Evidence quality | backtested/qualitative/anecdotal | ... |

## Recommendation
Implement / Skip / Needs more data

## Proposed Scanner Spec (if recommending implementation)
- **Scanner name:** `<name>`
- **Data source:** `tradingagents/dataflows/<existing_file>.py`
- **Signal logic:** <how to detect the signal>
- **Priority rules:** CRITICAL if X, HIGH if Y, MEDIUM otherwise
- **Context format:** "<description of what to put in candidate context>"
```

Add an entry to `docs/iterations/LEARNINGS.md` under a Research section.

## Step 6: Implement (if threshold met)

If the finding meets the auto-implement threshold:

1. Read the scanner registry to understand the registration pattern:
   `tradingagents/dataflows/discovery/scanner_registry.py`
2. Read an existing simple scanner for the code pattern, e.g.:
   `tradingagents/dataflows/discovery/scanners/earnings_calendar.py`
3. Create `tradingagents/dataflows/discovery/scanners/<name>.py` following
   the same structure: class with `@SCANNER_REGISTRY.register()` decorator,
   `name`, `pipeline`, `scan()` method returning list of candidate dicts with
   keys: `ticker`, `source`, `context`, `priority`.
4. Register the scanner in `tradingagents/dataflows/discovery/scanners/__init__.py`
   if needed (check if auto-discovery is in place).

If threshold is NOT met: write the research file only. Add a `needs-review` note
at the top explaining why auto-implementation was skipped.

## Step 7: Commit (skip if CI=true)

If the environment variable `CI` is set, stop here. The workflow handles git.

Otherwise:
```bash
git add docs/iterations/research/ tradingagents/ docs/iterations/LEARNINGS.md
git commit -m "research(<topic>): <summary of finding and action taken>"
```

Check for existing open PR on `research/current`:
```bash
EXISTING=$(gh pr list --head research/current --state open --json number --jq '.[0].number // empty')
```

If exists: push to branch, update PR description.
If not: create branch `research/current`, push, open PR.
```
```

- [ ] **Step 2: Smoke-test the command manually**

In a Claude Code session, type `/research-strategy "momentum breakout"` and verify
Claude reads the command, prints its agenda, and starts searching. Let it run at
least through Step 2 to confirm web search is working.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/research-strategy.md
git commit -m "feat(iteration-system): add /research-strategy Claude Code command"
```

---

## Task 4: Write the `iterate.yml` GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/iterate.yml`

- [ ] **Step 1: Write iterate.yml**

Create `.github/workflows/iterate.yml` with this exact content:

```yaml
name: Daily Iterate

on:
  schedule:
    # 6:00 AM UTC daily — analyzes previous day's discovery run
    - cron: "0 6 * * *"
  workflow_dispatch:
    inputs:
      force:
        description: "Force iterate even if no new runs detected"
        required: false
        default: "false"
        type: choice
        options:
          - "false"
          - "true"

env:
  PYTHON_VERSION: "3.10"
  NODE_VERSION: "20"

jobs:
  iterate:
    runs-on: ubuntu-latest
    environment: TradingAgent
    timeout-minutes: 30
    permissions:
      contents: write
      pull-requests: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GH_TOKEN }}

      - name: Set up git identity
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}

      - name: Install Claude Code CLI
        run: npm install -g @anthropic-ai/claude-code

      - name: Run /iterate
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          CI: "true"
        run: |
          claude -p "/iterate" --dangerously-skip-permissions

      - name: Check for changes
        id: changes
        run: |
          git add docs/iterations/ tradingagents/ || true
          if git diff --cached --quiet; then
            echo "has_changes=false" >> "$GITHUB_OUTPUT"
            echo "No changes produced by /iterate"
          else
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Commit changes
        if: steps.changes.outputs.has_changes == 'true'
        run: |
          DATE=$(date -u +%Y-%m-%d)
          git commit -m "learn(iterate): ${DATE} — automated iteration run"

      - name: Handle rolling PR
        if: steps.changes.outputs.has_changes == 'true'
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          BRANCH="iterate/current"
          DATE=$(date -u +%Y-%m-%d)

          # Check for existing open PR on this branch
          EXISTING_PR=$(gh pr list \
            --head "$BRANCH" \
            --state open \
            --json number \
            --jq '.[0].number // empty')

          if [ -n "$EXISTING_PR" ]; then
            # Push onto existing branch and update PR
            git push origin HEAD:"$BRANCH" --force-with-lease 2>/dev/null || \
              git push origin HEAD:"$BRANCH"
            gh pr edit "$EXISTING_PR" \
              --body "$(cat docs/iterations/LEARNINGS.md)

---
*Last updated: ${DATE} by automated iterate workflow*"
            echo "Updated existing PR #${EXISTING_PR}"
          else
            # Create new branch and open PR
            git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
            git push -u origin "$BRANCH"
            gh pr create \
              --title "learn(iterate): automated improvements — ${DATE}" \
              --body "$(cat docs/iterations/LEARNINGS.md)

---
*Opened: ${DATE} by automated iterate workflow*
*Merge to apply learnings and reset the iteration cycle.*" \
              --label "automated,iteration" \
              --base main
            echo "Opened new PR"
          fi
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/iterate.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 3: Add required GitHub secrets**

Verify these secrets exist in the repo's `TradingAgent` environment (Settings → Environments → TradingAgent → Secrets):
- `ANTHROPIC_API_KEY` — for Claude Code
- `GH_TOKEN` — PAT with `repo` scope (needed for PR creation; the default `GITHUB_TOKEN` cannot create PRs that trigger other workflows)

Check existing secrets:
```bash
gh secret list --env TradingAgent
```

If `GH_TOKEN` is missing, the user must add it manually via GitHub UI (PAT with `repo` scope).

- [ ] **Step 4: Trigger manually to test**

```bash
gh workflow run iterate.yml
sleep 10
gh run list --workflow=iterate.yml --limit=1
```

Watch the run in GitHub Actions UI. Verify:
- Claude Code installs successfully
- `/iterate` runs without crashing
- If changes produced: a PR is created or updated on `iterate/current`
- If no changes: workflow exits cleanly with "No changes produced" message

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/iterate.yml
git commit -m "feat(iteration-system): add daily iterate GitHub Actions workflow"
```

---

## Task 5: Write the `research-strategy.yml` GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/research-strategy.yml`

- [ ] **Step 1: Write research-strategy.yml**

Create `.github/workflows/research-strategy.yml` with this exact content:

```yaml
name: Weekly Research Strategy

on:
  schedule:
    # 7:00 AM UTC every Monday — runs after iterate (6:00 AM)
    - cron: "0 7 * * 1"
  workflow_dispatch:
    inputs:
      topic:
        description: "Research topic (blank = autonomous mode)"
        required: false
        default: ""

env:
  NODE_VERSION: "20"

jobs:
  research:
    runs-on: ubuntu-latest
    environment: TradingAgent
    timeout-minutes: 45
    permissions:
      contents: write
      pull-requests: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GH_TOKEN }}

      - name: Set up git identity
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}

      - name: Install Claude Code CLI
        run: npm install -g @anthropic-ai/claude-code

      - name: Build research prompt
        id: prompt
        run: |
          TOPIC="${{ github.event.inputs.topic }}"
          if [ -n "$TOPIC" ]; then
            echo "prompt=/research-strategy \"${TOPIC}\"" >> "$GITHUB_OUTPUT"
          else
            echo "prompt=/research-strategy" >> "$GITHUB_OUTPUT"
          fi

      - name: Run /research-strategy
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          CI: "true"
        run: |
          claude -p "${{ steps.prompt.outputs.prompt }}" --dangerously-skip-permissions

      - name: Check for changes
        id: changes
        run: |
          git add docs/iterations/research/ tradingagents/ docs/iterations/LEARNINGS.md || true
          if git diff --cached --quiet; then
            echo "has_changes=false" >> "$GITHUB_OUTPUT"
            echo "No changes produced by /research-strategy"
          else
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Commit changes
        if: steps.changes.outputs.has_changes == 'true'
        run: |
          DATE=$(date -u +%Y-%m-%d)
          TOPIC="${{ github.event.inputs.topic }}"
          if [ -n "$TOPIC" ]; then
            MSG="research(${TOPIC}): ${DATE} — automated research run"
          else
            MSG="research(autonomous): ${DATE} — automated research run"
          fi
          git commit -m "$MSG"

      - name: Handle rolling PR
        if: steps.changes.outputs.has_changes == 'true'
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: |
          BRANCH="research/current"
          DATE=$(date -u +%Y-%m-%d)

          # Summarise new research files for PR body
          NEW_FILES=$(git diff HEAD~1 --name-only -- docs/iterations/research/ | head -5)
          PR_BODY="## Research Findings — ${DATE}

New research files:
${NEW_FILES}

$(cat docs/iterations/LEARNINGS.md | head -30)

---
*Last updated: ${DATE} by automated research-strategy workflow*
*Merge to apply new scanner implementations and reset the research cycle.*"

          EXISTING_PR=$(gh pr list \
            --head "$BRANCH" \
            --state open \
            --json number \
            --jq '.[0].number // empty')

          if [ -n "$EXISTING_PR" ]; then
            git push origin HEAD:"$BRANCH" --force-with-lease 2>/dev/null || \
              git push origin HEAD:"$BRANCH"
            gh pr edit "$EXISTING_PR" --body "$PR_BODY"
            echo "Updated existing PR #${EXISTING_PR}"
          else
            git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
            git push -u origin "$BRANCH"
            gh pr create \
              --title "research: new strategy findings — ${DATE}" \
              --body "$PR_BODY" \
              --label "automated,research" \
              --base main
            echo "Opened new PR"
          fi
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/research-strategy.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 3: Trigger manually to test**

```bash
gh workflow run research-strategy.yml --field topic="momentum breakout"
sleep 10
gh run list --workflow=research-strategy.yml --limit=1
```

Watch in GitHub Actions UI. Verify:
- `/research-strategy "momentum breakout"` runs (directed mode)
- Research file written to `docs/iterations/research/`
- PR created or updated on `research/current`

- [ ] **Step 4: Test autonomous mode**

```bash
gh workflow run research-strategy.yml
sleep 10
gh run list --workflow=research-strategy.yml --limit=1
```

Verify Claude picks a topic from the knowledge base weak spots rather than erroring.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/research-strategy.yml
git commit -m "feat(iteration-system): add weekly research-strategy GitHub Actions workflow"
```

---

## Completion Checklist

- [ ] `docs/iterations/` has 16 files (LEARNINGS.md + 13 scanner files + scoring.md)
- [ ] `/iterate` command loads in Claude Code session
- [ ] `/research-strategy` command loads in Claude Code session
- [ ] `iterate.yml` workflow runs cleanly (manual trigger)
- [ ] `research-strategy.yml` workflow runs cleanly (manual trigger, directed mode)
- [ ] `research-strategy.yml` autonomous mode picks a topic from knowledge base
- [ ] Rolling PR logic verified: second workflow run updates existing PR, not creates a new one
- [ ] `GH_TOKEN` secret exists in `TradingAgent` environment
