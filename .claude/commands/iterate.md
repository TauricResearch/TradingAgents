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
Load each file and extract all recommendations. These are mature enough to
have played out — analyze them regardless of `status` field value.
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
- Group by `strategy_match` (scanner). Compute per-scanner: how many
  recommendations were made, what was the average final_score, and whether
  `status` fields suggest positive or negative outcomes.
- Flag scanners where final_score > 80 but outcomes appear poor — overconfident.
- Flag scanners where final_score < 65 but outcomes appear good — undervalued.
- Note patterns: do high-confidence (9-10) picks outperform low-confidence (6-7)?

## Step 4: Write Learnings

For each scanner that appeared in the analysis, update its domain file in
`docs/iterations/scanners/<scanner_name>.md`:

1. **Append to Evidence Log**: Add a dated entry with your specific observations.
   Use this format:
   ```
   ### YYYY-MM-DD — <run date or "P&L review">
   - What was observed
   - What it implies
   - Confidence: low / medium / high
   ```
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

If one exists: push to that branch and update the PR description with your findings appended.
If none exists: create branch `iterate/current`, push, open PR against `main`.
