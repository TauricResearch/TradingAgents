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
- Hacker News: search hn.algolia.com for the topic
- GitHub: search for "quant scanner <topic>" and "trading strategy <topic>"
- SSRN: search quantitative finance papers on the topic
- arXiv q-fin section

Use WebSearch and WebFetch to retrieve actual content. Read at least 3-5
distinct sources before forming a conclusion.

## Step 3: Cross-Reference Existing Knowledge

Check `docs/iterations/scanners/` and `docs/iterations/research/` for any
prior work on this topic. Flag explicitly if this overlaps with:
- An existing scanner (name it and the file)
- A previously researched and discarded approach (cite the research file)
- A pending hypothesis in an existing scanner file (cite it)

## Step 4: Evaluate Fit

Score the finding on four dimensions (each: ✅ pass / ⚠️ partial / ❌ fail):

1. **Data availability**: Is the required data source already integrated in
   `tradingagents/dataflows/`? Check for existing API clients there.
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

Save findings to `docs/iterations/research/` using filename format:
`YYYY-MM-DD-<topic-slug>.md` where topic-slug is the topic lowercased with
spaces replaced by hyphens.

Use this template:

```
# Research: <Topic>

**Date:** YYYY-MM-DD
**Mode:** directed | autonomous

## Summary
<2-3 sentences on what was found>

## Sources Reviewed
- <source 1>: <key finding from this source>
- <source 2>: <key finding from this source>
...

## Fit Evaluation
| Dimension | Score | Notes |
|-----------|-------|-------|
| Data availability | ✅/⚠️/❌ | ... |
| Complexity | trivial/moderate/large | ... |
| Signal uniqueness | low/medium/high overlap | ... |
| Evidence quality | backtested/qualitative/anecdotal | ... |

## Recommendation
Implement / Skip / Needs more data — <reason>

## Proposed Scanner Spec (if recommending implementation)
- **Scanner name:** `<name>`
- **Data source:** `tradingagents/dataflows/<existing_file>.py`
- **Signal logic:** <how to detect the signal, specific thresholds>
- **Priority rules:** CRITICAL if X, HIGH if Y, MEDIUM otherwise
- **Context format:** "<what to include in the candidate context string>"
```

Add an entry to `docs/iterations/LEARNINGS.md` under a `## Research` section
(create the section if it doesn't exist):
```
| research/<filename> | research/<filename>.md | YYYY-MM-DD | <one-line summary> |
```

## Step 6: Implement (if threshold met)

If the finding meets the auto-implement threshold from Step 4:

1. Read `tradingagents/dataflows/discovery/scanner_registry.py` to understand
   the `@SCANNER_REGISTRY.register()` registration pattern.
2. Read an existing simple scanner for the code pattern:
   `tradingagents/dataflows/discovery/scanners/earnings_calendar.py`
3. Create `tradingagents/dataflows/discovery/scanners/<name>.py` following
   the same structure:
   - Class decorated with `@SCANNER_REGISTRY.register()`
   - `name` and `pipeline` class attributes
   - `scan(self, state)` method returning `List[Dict]`
   - Each dict must have keys: `ticker`, `source`, `context`, `priority`
   - Priority values: `"CRITICAL"`, `"HIGH"`, `"MEDIUM"`, `"LOW"`
4. Check `tradingagents/dataflows/discovery/scanners/__init__.py` — if it
   imports scanners explicitly, add an import for the new one.

If threshold is NOT met: write the research file only. Add this note at the
top of the research file:
```
> **Auto-implementation skipped:** <reason — which threshold failed>
```

## Step 7: Commit (skip if CI=true)

If the environment variable `CI` is set, stop here. The workflow handles git.

Otherwise:
```bash
git add docs/iterations/research/ tradingagents/ docs/iterations/LEARNINGS.md
```

Run `git commit` with a message in the format:
`research(<topic>): YYYY-MM-DD — <one-sentence summary of finding and action>`

Then check for an existing open PR on branch `research/current`:
```bash
EXISTING=$(gh pr list --head research/current --state open --json number --jq '.[0].number // empty')
```

If one exists: push to that branch and update PR description with new findings.
If none exists:
```bash
git checkout -b research/current
git push -u origin research/current
gh pr create \
  --title "research: new strategy findings — $(date +%Y-%m-%d)" \
  --body "$(cat docs/iterations/LEARNINGS.md | head -30)" \
  --label "automated,research" \
  --base main
```
