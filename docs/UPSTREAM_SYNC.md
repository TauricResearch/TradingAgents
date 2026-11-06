# Upstream sync (TauricResearch → this fork)

This fork tracks [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
and also carries workspace-only work (HTTP `/decide` service, Indian news/sentiment,
MCX commodities, 1-day gap prompts, structured mode, external-signal prior, etc.).

**Never** use GitHub's "Sync fork" / `gh repo sync --force`. Those overwrite fork files.

## One command (local)

From the repo root:

```bash
python scripts/sync_upstream.py
```

That fetches `upstream`, creates `sync/upstream-YYYYMMDD` from `origin/main`,
merges `upstream/main`, and either:

- prints "clean merge — open a PR", or
- lists conflict files and stops so they can be resolved with the policy below.

## Automatic weekly PR

`.github/workflows/sync-upstream.yml` runs Monday 06:00 UTC and on
`workflow_dispatch`. It opens a PR when `upstream/main` is ahead. It does
**not** auto-merge: overlapping files almost always need a keep-both resolution.

## Conflict policy

| File class | Rule |
|---|---|
| Fork-only (`scripts/decide.py`, `scripts/service.py`, `indian_news.py`, Docker/deploy, retro scripts, holding-recommendation, external-signal, structured mode, commodity asset type) | Keep ours. Upstream has no equivalent. |
| Shared agents / dataflows / graph | Keep **both**: fork prompts/fields/callers **and** the upstream fix. |
| Tests | Keep both suites. |
| `pyproject.toml` / README / CHANGELOG | Take upstream version/docs, keep our extra deps (`fastapi`, `uvicorn`). |

Recurring overlap (resolve by combining, never by `-X ours` / `-X theirs`).
Paths are as of the v0.7.1 sync (2026-11-07), after upstream reorganised the
package (`agents/utils/*` → `agents/{context,state,structured,rating,tools}.py`,
`dataflows/*` → `dataflows/vendors/*`, `interface.py` → `router.py`):

- `agents/trader/trader.py` — 1-day horizon + debate ablation (`debate_enabled=False` branch) + external signal **and** upstream's absolute-price rule, portfolio context and `## Output` shape (applied to both branches)
- `agents/managers/{research,portfolio}_manager.py` — fresh-entry prompts + external signal + holding recommendation **and** "conflict alone is not a reason to Hold", `{portfolio_context}`, `## Output` shape (keep our Holding lines in the PM's output list, or the label-only holding parser reads free-text fallbacks as Data-Dependent)
- `agents/rating.py` — upstream's label-only rating parser; our `parse_holding_recommendation` lives at the bottom and follows the same rules (label only, NFKC, disagreeing labels → default)
- `agents/context.py` — external-signal helpers + commodity label **and** upstream's point-in-time identity rules
- `agents/state.py` / `graph/propagation.py` / `graph/trading_graph.py` — `external_signal_*` and structured-mode fields **and** upstream's `final_rating` / `portfolio_context` / `memory_note`; the external signal is part of the checkpoint run signature
- `graph/setup.py` — `decision_mode` / `debate_first_speaker` node selection **and** upstream's parallel analysts; the analysts' fan-in edge goes to the decision layer's entry node, not hard-coded "Bull Researcher"
- `dataflows/vendors/yahoo/fundamentals.py` — upstream withholds the live profile and period-dated statements from past runs; ours adds announcement-dated Yahoo statements (earnings calendar) on top, for NSE/BSE listings SEC EDGAR does not cover (#21)
- `dataflows/vendors/{reddit,stocktwits}.py` — Indian subreddits via `subreddits_for()` / `.NS`→`.NSE` **and** upstream's combined feed and screening
- `dataflows/vendors/indian_news.py` — follows upstream's vendor contract: `VendorUnavailableError` on outage or empty feed, `date_window.coverage_gap` for an unobserved past window
- `dataflows/symbols.py` — `&` in `_TICKER_PATH_RE` (M&M.NS, TFR-215)
- `agents/schemas.py` — `HoldingRecommendation` is required on `PortfolioDecision`, so upstream tests that build one need `holding_recommendation`/`holding_rationale` added

After resolving: run `pytest -q` and open a PR. Do not push straight to `main`.

**Merge the PR with a merge commit, never squash.** `main` allows merge commits
(linear history is off) so the merge-base moves to the current `upstream/main`.
Squashing (#33) left the tree correct but the merge-base at v0.3.1, so the next
sync re-saw the same 27 commits and the same conflicts.
