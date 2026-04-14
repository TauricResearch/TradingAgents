# /backtest-hypothesis

Test a hypothesis about a scanner improvement using branch-per-hypothesis isolation.

**Usage:** `/backtest-hypothesis "<description of the hypothesis>"`

**Example:** `/backtest-hypothesis "options_flow: scan 3 expirations instead of 1 to capture institutional 30+ DTE positioning"`

---

## Step 1: Read Current Registry

Read `docs/iterations/hypotheses/active.json`. Note:
- How many hypotheses currently have `status: "running"`
- The `max_active` limit (default 5)
- Any existing `pending` entries

Also read `docs/iterations/LEARNINGS.md` and the relevant scanner domain file in
`docs/iterations/scanners/` to understand the current baseline.

## Step 2: Classify the Hypothesis

Determine whether this is:

**Statistical** — answerable from existing data in `data/recommendations/performance_database.json`
without any code change. Examples:
- "Does high confidence (≥8) predict better 30d returns?"
- "Are options_flow picks that are ITM outperforming OTM ones?"

**Implementation** — requires a code change and forward-testing period. Examples:
- "Scan 3 expirations instead of 1"
- "Apply a premium filter of $50K instead of $25K"

## Step 3a: Statistical Path

If statistical: run the analysis now against `data/recommendations/performance_database.json`.
Write the finding to the relevant scanner domain file under **Evidence Log**. Print a summary.

Then register the hypothesis in `docs/iterations/hypotheses/active.json` as `status: "pending"`
so the runner picks it up on the next cycle and attaches LLM analysis to the report:

```json
{
  "id": "<scanner>-<slug>",
  "scanner": "<scanner>",
  "title": "<title>",
  "description": "<description>",
  "branch": null,
  "pr_number": null,
  "status": "pending",
  "priority": 0,
  "expected_impact": "low",
  "hypothesis_type": "statistical",
  "created_at": "<YYYY-MM-DD>",
  "min_days": 0,
  "days_elapsed": 0,
  "picks_log": [],
  "baseline_scanner": "<scanner>",
  "conclusion": null
}
```

Commit and push the updated `active.json` to `main`. Done — no branch or worktree needed.

## Step 3b: Implementation Path

### 3b-i: Capacity check

Count running hypotheses where `hypothesis_type == "implementation"` from `active.json`.
Statistical hypotheses do not consume runner slots and are excluded from this count.

If fewer than `max_active` implementation hypotheses are running, proceed.
If at capacity: add the new hypothesis as `status: "pending"` — running experiments are NEVER
paused mid-streak. Inform the user which slot it is queued behind and when it will likely start.

### 3b-ii: Score the hypothesis

Assign a `priority` score (1–9) using these factors:

| Factor | Score |
|---|---|
| Scanner 30d win rate < 40% | +3 |
| Change touches 1 file, 1 parameter | +2 |
| Directly addresses a weak spot in LEARNINGS.md | +2 |
| Scanner generates ≥2 picks/day (data accrues fast) | +1 |
| Supported by external research (arXiv, Alpha Architect, etc.) | +1 |
| Contradictory evidence or unclear direction | −2 |

### 3b-iii: Determine min_days

Set `min_days` based on the scanner's typical picks-per-day rate:
- ≥2 picks/day → 10 days
- 1 pick/day → 14 days
- <1 pick/day → 21 days

### 3b-iv: Create the branch and implement the code change

```bash
BRANCH="hypothesis/<scanner>-<slug>"
git checkout -b "$BRANCH"
```

Make the minimal code change that implements the hypothesis. Read the scanner file first.
Only change what the hypothesis requires — do not refactor surrounding code.

```bash
git add tradingagents/
git commit -m "hypothesis(<scanner>): <title>"
```

### 3b-v: Create picks tracking file on the branch

Create `docs/iterations/hypotheses/<id>/picks.json` on the hypothesis branch:

```json
{
  "hypothesis_id": "<id>",
  "scanner": "<scanner>",
  "picks": []
}
```

```bash
mkdir -p docs/iterations/hypotheses/<id>
git add docs/iterations/hypotheses/<id>/picks.json
git commit -m "hypothesis(<scanner>): add picks tracker"
git push -u origin "$BRANCH"
```

### 3b-vi: Open a draft PR

```bash
gh pr create \
  --title "hypothesis(<scanner>): <title>" \
  --body "**Hypothesis:** <description>

**Expected impact:** <high/medium/low>
**Min days:** <N>
**Priority:** <score>/9

*This is an automated hypothesis experiment. It will be auto-concluded after ${MIN_DAYS} days of data.*" \
  --draft \
  --base main
```

Note the PR number from the output.

### 3b-vii: Update active.json on main

Check out `main`, then update `docs/iterations/hypotheses/active.json` to add the new entry:

```json
{
  "id": "<scanner>-<slug>",
  "scanner": "<scanner>",
  "title": "<title>",
  "description": "<description>",
  "branch": "hypothesis/<scanner>-<slug>",
  "pr_number": <N>,
  "status": "running",
  "priority": <score>,
  "expected_impact": "<high|medium|low>",
  "hypothesis_type": "implementation",
  "created_at": "<YYYY-MM-DD>",
  "min_days": <N>,
  "days_elapsed": 0,
  "picks_log": [],
  "baseline_scanner": "<scanner>",
  "conclusion": null
}
```

```bash
git checkout main
git add docs/iterations/hypotheses/active.json
git commit -m "feat(hypotheses): register hypothesis <id>"
git push origin main
```

## Step 4: Print Summary

Print a confirmation:
- Hypothesis ID and branch name
- Status: running or pending
- Expected conclusion date (created_at + min_days)
- PR link (if running)
- Priority score and why
