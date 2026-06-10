# Codex Handoff

## 1. Current objective

Original goal: transform the public repo `TauricResearch/TradingAgents` into `IndiaMarketAgents`, an India-first, India-only institutional-market research copilot for Indian listed equities, indices, macro, filings, flows, and compliance context.

The session progressed through scoped phases:

1. Documentation bootstrap and repo audit.
2. User-facing rebrand, India-only ticker validation, India config defaults/env overrides, report path safety, and tests.
3. Data-source layer hardening for local filings, yfinance India wrapper behavior, NSE/BSE placeholders, macro/flows unavailable responses, data-quality rendering, and offline tests.
4. India analyst prompt and downstream decision-language review for research-only wording, India context, data-quality caveats, and no live-trading language.
5. Saved report/disclaimer artifact hardening.
6. Read-only dashboard/report review.
7. Security/compliance final pass.
8. Final branch review and PR-readiness package.
9. PR creation.
10. Usage playbook and best-use-case guidance.

The branch is already pushed and a draft PR is open:

- Draft PR: https://github.com/TauricResearch/TradingAgents/pull/1002
- Base: `TauricResearch/TradingAgents:main`
- Head: `tgabhawala-creator:india-market-agents`
- PR title: `Transform TradingAgents into IndiaMarketAgents research copilot foundation`

Current objective: make the GitHub repo practically usable and identify the highest-value use case. The current best use case is a first-pass India equity research pack for an NSE/BSE-listed company, using local filings where available and saved report artifacts for analyst review. This is documented in `docs/USAGE_PLAYBOOK.md`.

## 2. Current repo state

Current follow-up state as of 2026-06-10:

- `.codex/HANDOFF.md` was committed as `9c3347b docs: add Codex session handoff` and pushed to `origin/india-market-agents`.
- A draft PR remains open: https://github.com/TauricResearch/TradingAgents/pull/1002.
- GitHub CLI PR inspection failed with `HTTP 401: Requires authentication`; run `gh auth refresh -h github.com` before checking PR status or updating the PR body.
- `docs/USAGE_PLAYBOOK.md` is included in the usage-playbook docs phase.

Latest local inspection commands:

- `git status --branch --short`: clean after pushing `9c3347b`; dirty while the usage-playbook docs were being edited.
- `git branch --show-current`: `india-market-agents`.
- `git rev-parse --short HEAD`: `9c3347b` before committing the usage-playbook docs.
- `python --version`: failed with `zsh:1: command not found: python`.
- `python3 --version`: `Python 3.14.5`.

Additional state:

- `git status --branch --short`: `## india-market-agents...origin/india-market-agents` after pushing `9c3347b`.
- Latest committed HEAD before the usage-playbook docs: `9c3347b docs: add Codex session handoff`; re-check after the usage-playbook commit.
- Local branch tracks `origin/india-market-agents`.
- Remotes:
  - `origin`: `https://github.com/tgabhawala-creator/TradingAgents_India.git`
  - `upstream`: `https://github.com/TauricResearch/TradingAgents.git`
- `origin` is the user fork with admin permission.
- `upstream` is read-only for the authenticated GitHub account.
- Draft PR `#1002` is open and draft.

`.codex/HANDOFF.md` is tracked and pushed.

Branch scope relative to `upstream/main`:

- `git rev-list --count upstream/main..HEAD`: 14 after the usage-playbook docs commit.
- `git diff --stat upstream/main..HEAD`: 74 files changed, 4362 insertions, 226 deletions.

Material file changes by area:

- Project docs and attribution:
  - `AGENTS.md`: future-agent rules for India-only scope, no live trading, no secrets, tests, data integrity, compliance, and handoff updates.
  - `NOTICE`: upstream attribution retained/extended.
  - `README.md`: IndiaMarketAgents preface and removal of the most direct simulated-exchange execution wording.
  - `README_INDIA.md`: India-specific setup, usage, disclaimers, dashboard instructions.
  - `docs/USAGE_PLAYBOOK.md`: practical first workflow and highest-value use case for using the repo.
  - `docs/CODEX_HANDOFF.md`: phase-by-phase project handoff.
  - `docs/PR_READINESS.md`: PR title/body/checklist/reviewer focus.
  - `docs/REPO_AUDIT_INDIA.md`: architecture audit and India migration plan.
  - `docs/INDIA_COMPLIANCE.md`, `docs/INDIA_DATA_SOURCES.md`, `docs/SECURITY.md`, `docs/BEGINNER_SETUP.md`, `docs/ADDING_NEW_INDIAN_AGENT.md`: India compliance, source, security, setup, and extension docs.
- Config/rebrand:
  - `pyproject.toml`: IndiaMarketAgents description, `indiamarketagents` console script while retaining `tradingagents`.
  - `.env.example.india`: India-specific env template.
  - `.gitignore`: generated reports, local filings/manual data, secrets, and Streamlit secrets ignored.
  - `config/india_market_holidays.yml`: verified India holiday override scaffold.
- CLI/reporting:
  - `cli/main.py`: India CLI behavior, doctor/analyze support, India ticker/date validation, safe report paths, report writer, disclaimers, source/data-quality artifacts.
  - `cli/models.py`, `cli/utils.py`, `cli/static/india_welcome.txt`: India analyst choices, config/display support, beginner UI copy.
- Dashboard:
  - `dashboard/app.py`: read-only Streamlit saved-report reviewer.
  - `dashboard/report_review.py`: pure helper module for report discovery/rendering and data-quality JSON formatting.
- India agents/tools/graph:
  - `tradingagents/agents/analysts/india_*.py`: India analysts for market, fundamentals, news/filings, macro/policy, flows, sentiment, compliance.
  - `tradingagents/agents/utils/india_market_tools.py`: India LangChain tool wrappers.
  - `tradingagents/agents/__init__.py`, `tradingagents/agents/utils/agent_states.py`: India agents/state fields exported and tracked.
  - `tradingagents/graph/analyst_execution.py`, `conditional_logic.py`, `setup.py`, `trading_graph.py`, `propagation.py`: India analyst sequencing, graph wiring, propagation/state behavior.
  - Downstream prompts in `tradingagents/agents/researchers/*`, `risk_mgmt/*`, `managers/*`, `trader/trader.py`, and schema/rendering in `tradingagents/agents/schemas.py` were tightened for research/model-view language.
- India dataflows:
  - `tradingagents/dataflows/india/symbols.py`: India ticker validation/normalization and path-safe ticker components.
  - `calendar.py`, `formatting.py`, `quality.py`, `filings.py`, `yfinance_india.py`, `nse.py`, `bse.py`, `macro.py`, `flows.py`, `sector_context.py`, `cache.py`: India calendars, formatting, local filings, source quality, yfinance wrapper, official-source placeholders, unavailable responses.
  - `tradingagents/dataflows/interface.py`, `tradingagents/default_config.py`: India defaults/vendor routing/config.
- Tests:
  - India tests added/updated for symbols, calendar/formatting, vendor routing, data sources, CLI/report writing, prompt language, dashboard helper rendering, security/compliance, env overrides, no-data handling, structured-agent compatibility.

Generated files or artifacts:

- No generated reports, local filing folders, PDFs, DBs, bytecode, logs, or secrets are tracked.
- Local `__pycache__` files exist from test runs but are ignored by git and were intentionally not deleted.
- `.codex/HANDOFF.md` is newly created for this handoff and is not yet committed unless the next session/user commits it.

## 3. Decisions made

- Keep the internal Python package name `tradingagents`.
  - Reason: full package rename would be high-churn and risky; user-facing branding can be handled through CLI/docs first.
- Add `indiamarketagents` as a console script while retaining `tradingagents`.
  - Reason: user-facing rebrand without breaking upstream/backward-compatible entry points.
- India-only default scope with explicit legacy/global escape hatch.
  - Reason: user requirement was India-only by default and rejection of US/global/crypto tickers unless explicitly allowed.
- Validate India ticker-derived report paths before creating output directories.
  - Reason: path safety and avoiding side effects for unsafe ticker input.
- Prefer official/user-provided data, but keep NSE/BSE official modules as defensive placeholders.
  - Reason: official public endpoints and terms/access need verification; placeholders fail closed with `UNAVAILABLE`.
- Use yfinance only as a third-party fallback with explicit source/data-quality notes.
  - Reason: yfinance is not official; output must not imply official exchange/company provenance.
- Do not enable PDF OCR by default for local filings.
  - Reason: cost and complexity; users should convert important pages to text/markdown for auditable research.
- Use explicit `UNAVAILABLE`, low-confidence, and data-quality messages instead of fabricated values.
  - Reason: user rule: do not fabricate data.
- Keep all outputs research-only and education-only.
  - Reason: product must be a decision-support copilot, not a trading bot or investment adviser.
- No live broker order execution, broker integrations, or live trading controls.
  - Reason: hard user rule; also enforced through docs, prompts, dashboard tests, and scans.
- Saved report artifacts should be standalone.
  - Reason: individual section markdown files may be reviewed outside the full report, so each carries the compliance disclaimer and writer-level artifact notes.
- Report-writer source/data-quality coverage is marker detection only.
  - Reason: writer cannot verify underlying facts; metadata is an audit aid, not certification.
- Dashboard is read-only and Streamlit remains optional.
  - Reason: dashboard should review saved reports only, and baseline tests should not require optional dashboard dependencies.
- Use pure helper modules for dashboard logic.
  - Reason: offline tests can cover report discovery/rendering without importing Streamlit.
- Neutralize fake `sk-...` values in tests.
  - Reason: reduce false-positive secret scanner hits.
- Preserve Apache 2.0 license and upstream attribution.
  - Reason: hard user rule and upstream fork hygiene.
- Commit after each phase.
  - Reason: user requested phase-level commits where possible.

## 4. Work completed

Follow-up usage work:

- Committed and pushed `.codex/HANDOFF.md`.
- Added `docs/USAGE_PLAYBOOK.md` with the highest-value use case, first recommended workflow, setup path, optional local filings path, first analysis command, saved artifacts to review, review sequence, current limits, and acceptance checks.
- Linked the playbook from `README_INDIA.md`.
- Updated `docs/CODEX_HANDOFF.md` and `docs/PR_READINESS.md` to reflect the usage phase and GitHub auth blocker.

PR/publish work:

- Pushed `india-market-agents` to `origin` (`tgabhawala-creator/TradingAgents_India`).
- Created draft PR: https://github.com/TauricResearch/TradingAgents/pull/1002.
- PR body used `docs/PR_READINESS.md`.

Documentation:

- Created/updated:
  - `AGENTS.md`
  - `README_INDIA.md`
  - `docs/CODEX_HANDOFF.md`
  - `docs/PR_READINESS.md`
  - `docs/REPO_AUDIT_INDIA.md`
  - `docs/INDIA_COMPLIANCE.md`
  - `docs/INDIA_DATA_SOURCES.md`
  - `docs/SECURITY.md`
  - `docs/BEGINNER_SETUP.md`
  - `docs/ADDING_NEW_INDIAN_AGENT.md`
- Updated `README.md` with IndiaMarketAgents preface and research-only/no-simulated-exchange wording.

Config/rebrand/validation:

- `pyproject.toml`: user-facing IndiaMarketAgents description and `indiamarketagents` script.
- `tradingagents/default_config.py`: India defaults and environment/config behavior.
- `tradingagents/dataflows/india/symbols.py`: India ticker validation, normalization, safe ticker component.
- `cli/main.py`: validates India tickers/dates in CLI paths, safe default report paths.

India data-source layer:

- `tradingagents/dataflows/india/quality.py`: `DataQuality` model and rendering helpers.
- `tradingagents/dataflows/india/filings.py`: local filing reads with data-quality notes and PDF no-OCR caveats.
- `tradingagents/dataflows/india/yfinance_india.py`: yfinance wrapper output with source/coverage/confidence warnings.
- `tradingagents/dataflows/india/nse.py`, `bse.py`, `macro.py`, `flows.py`: fail-closed unavailable responses.
- `tradingagents/dataflows/india/calendar.py`, `formatting.py`, `sector_context.py`, `cache.py`: India support utilities.

Agent/graph/CLI wiring:

- `tradingagents/agents/analysts/india_market_analyst.py`
- `tradingagents/agents/analysts/india_fundamentals_analyst.py`
- `tradingagents/agents/analysts/india_news_filings_analyst.py`
- `tradingagents/agents/analysts/india_macro_policy_analyst.py`
- `tradingagents/agents/analysts/india_flows_analyst.py`
- `tradingagents/agents/analysts/india_sentiment_analyst.py`
- `tradingagents/agents/analysts/india_compliance_risk_analyst.py`
- `tradingagents/agents/utils/india_market_tools.py`
- `tradingagents/graph/analyst_execution.py`
- `tradingagents/graph/setup.py`
- `tradingagents/graph/trading_graph.py`
- `tradingagents/graph/conditional_logic.py`
- `tradingagents/graph/propagation.py`
- `cli/main.py`, `cli/models.py`, `cli/utils.py`

Prompt/decision language:

- Downstream files updated for India research-only/model-view wording:
  - `tradingagents/agents/researchers/bull_researcher.py`
  - `tradingagents/agents/researchers/bear_researcher.py`
  - `tradingagents/agents/managers/research_manager.py`
  - `tradingagents/agents/managers/portfolio_manager.py`
  - `tradingagents/agents/trader/trader.py`
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py`
  - `tradingagents/agents/risk_mgmt/conservative_debator.py`
  - `tradingagents/agents/risk_mgmt/neutral_debator.py`
  - `tradingagents/agents/schemas.py`
- `render_trader_proposal()` now renders `FINAL MODEL VIEW` rather than transaction-proposal wording.

Report/dashboard:

- `cli/main.py::save_report_to_disk()` writes:
  - `complete_report.md`
  - per-section markdown files with disclaimer and artifact notes
  - `sources.md`
  - `data_quality.json`
  - `summary.json`
  - `disclaimer.md`
  - `trader_research_view.md`
- `dashboard/app.py`: read-only saved-report dashboard shell.
- `dashboard/report_review.py`: pure helpers for report discovery, markdown rendering, and data-quality JSON formatting.

Tests:

- Added/updated offline tests:
  - `tests/test_india_symbols.py`
  - `tests/test_india_calendar_formatting.py`
  - `tests/test_env_overrides.py`
  - `tests/test_dataflows_config.py`
  - `tests/test_india_vendor_routing.py`
  - `tests/test_no_data_handling.py`
  - `tests/test_india_cli_report.py`
  - `tests/test_india_data_sources.py`
  - `tests/test_india_prompt_language.py`
  - `tests/test_structured_agents.py`
  - `tests/test_dashboard_report_review.py`
  - `tests/test_security_compliance.py`
  - `tests/test_api_key_env.py`

## 5. Work in progress

Nothing is actively in progress in code. The branch was pushed and a draft PR is open.

Items intentionally left for future work:

- Optional dashboard runtime/browser verification after installing `python3 -m pip install -e ".[dashboard]"`.
- Official NSE/BSE source workflows after legal/source/access review.
- Cleaner user-facing README routing to `README_INDIA.md`; `README.md` still contains much upstream content.
- Possible full package rename from `tradingagents` to `indiamarketagents`, if explicitly requested later.
- Review/update PR #1002 after upstream CI or reviewer feedback, if any.

## 6. Known issues / risks

- No known current test failures. Latest full offline run passed.
- `python` is not on PATH in this environment. Use `python3`.
- Streamlit is not installed in the baseline environment; `python3 dashboard/app.py` reaches optional Streamlit import and fails with `ModuleNotFoundError: No module named 'streamlit'`.
- Dashboard browser/runtime behavior was not manually verified.
- NSE/BSE official data modules are placeholders and fail closed with unavailable responses.
- yfinance remains third-party fallback, not official source data.
- `sources.md` and `data_quality.json` use writer-level marker detection and can produce false positives/negatives; they do not verify factual accuracy.
- Some internal schema/class names such as `TraderAction`, `TraderProposal.action`, and `final_trade_decision` remain for compatibility, even though user-facing text now uses model/research-view language.
- Some legacy/global prompt text outside the IndiaMarketAgents path may still contain transaction-oriented vocabulary; India/default path and downstream India behavior were tightened.
- Local ignored `__pycache__` files exist from test runs. They are not tracked and were not deleted.
- Unknown: GitHub PR CI status after PR creation. It was not inspected after opening the draft PR.
- Current blocker for PR inspection: `gh pr view` returned `HTTP 401: Requires authentication`.
- Unknown: whether upstream maintainers want this broad fork transformation in the upstream repo; PR is draft.

## 7. Commands run and results

Important repo/env commands:

- `git status --short`: initially clean before `.codex/HANDOFF.md`; no output.
- `git status --branch --short`: `## india-market-agents...origin/india-market-agents`.
- `git branch --show-current`: `india-market-agents`.
- `git rev-parse --short HEAD`: `3bab168`.
- `git diff --stat`: no working-tree diff before this handoff.
- `git diff --name-only`: no working-tree diff before this handoff.
- `python --version`: failed with `zsh:1: command not found: python`.
- `python3 --version`: `Python 3.14.5`.
- `git rev-list --count upstream/main..HEAD`: `12`.
- `git log --oneline --reverse upstream/main..HEAD`: listed 12 phase commits from `17f9f1d` through `3bab168`.
- `git diff --stat upstream/main..HEAD`: 74 files changed, 4362 insertions, 226 deletions.

Important focused tests run during the session:

- `python3 -m pytest tests/test_india_prompt_language.py tests/test_structured_agents.py -q`: 36 passed.
- `python3 -m pytest tests/test_india_cli_report.py -q`: 7 passed.
- `python3 -m pytest tests/test_dashboard_report_review.py -q`: 5 passed.
- `python3 -m pytest tests/test_security_compliance.py tests/test_india_cli_report.py -q`: 11 passed.
- `python3 -m pytest tests/test_api_key_env.py tests/test_security_compliance.py tests/test_india_cli_report.py -q`: 34 passed.

Full offline test runs:

- `python3 -m pytest -m "not integration" -q` after report phase: 364 passed, 1 deselected, 7 warnings, 75 subtests passed.
- `python3 -m pytest -m "not integration" -q` after dashboard phase: 369 passed, 1 deselected, 7 warnings, 75 subtests passed.
- `python3 -m pytest -m "not integration" -q` after security/final PR-readiness: 373 passed, 1 deselected, 7 warnings, 75 subtests passed.

Other verification/scans:

- `git diff --check`: passed repeatedly; final run passed.
- `git grep -n -I -E 'sk-[A-Za-z0-9_-]{8,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY' -- .` with `.env.example*` templates excluded: no matches.
- `git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order'` with `docs/CODEX_HANDOFF.md` and `tests/test_security_compliance.py` excluded: no matches.
- `git ls-files | rg '(^reports/|^data/india/filings/|^data/india/manual/|\\.pdf$|__pycache__|\\.pyc$|\\.db$|\\.sqlite$|\\.log$)'`: no matches.
- `python3 dashboard/app.py`: after import fallback, reached optional `streamlit` import and failed with `ModuleNotFoundError: No module named 'streamlit'`.

GitHub/PR commands:

- `gh --version`: `gh version 2.93.0`.
- `gh auth status`: authenticated as `tgabhawala-creator`; token scopes included `repo` and `workflow`. Token value was masked by `gh` output and is not recorded here.
- `gh repo view TauricResearch/TradingAgents --json nameWithOwner,defaultBranchRef,viewerPermission,url`: upstream default branch `main`, permission `READ`.
- `gh repo fork --remote --remote-name origin --default-branch-only`: reported existing fork-like repo `tgabhawala-creator/TradingAgents_India` and added `origin`.
- `gh repo view tgabhawala-creator/TradingAgents_India --json nameWithOwner,defaultBranchRef,viewerPermission,url,parent`: repo exists, permission `ADMIN`, parent `TauricResearch/TradingAgents`.
- `git push -u origin india-market-agents`: passed; branch pushed and set to track `origin/india-market-agents`.
- `gh pr create --repo TauricResearch/TradingAgents --head tgabhawala-creator:india-market-agents --base main --draft --title "Transform TradingAgents into IndiaMarketAgents research copilot foundation" --body-file docs/PR_READINESS.md`: passed; created https://github.com/TauricResearch/TradingAgents/pull/1002.
- `gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,author`: PR is open, draft, base `main`, head `tgabhawala-creator:india-market-agents`.
- `git push`: pushed `9c3347b docs: add Codex session handoff` to `origin/india-market-agents`.
- `gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,author,statusCheckRollup`: failed with `HTTP 401: Requires authentication`.
- `python3 -m cli.main --help`: passed.
- `python3 -m cli.main doctor --ticker RELIANCE.NS`: passed; ticker validation returned `RELIANCE.NS`; no LLM/API keys detected.
- `python3 -m cli.main analyze --ticker AAPL --date 2026-06-05 --no-display --no-save-prompt`: rejected `AAPL` as expected under India-only defaults.
- `python3 -m pytest tests/test_security_compliance.py tests/test_india_cli_report.py tests/test_dashboard_report_review.py -q`: 16 passed.

Commits created in this session/branch:

- `17f9f1d docs: add IndiaMarketAgents bootstrap guidance`
- `fdf2256 feat: add India market dataflow profile`
- `bca383e feat: wire IndiaMarketAgents agents and CLI`
- `52e6286 test: cover IndiaMarketAgents validation and reports`
- `ffbdcae docs: add IndiaMarketAgents audit and Codex handoff`
- `6d2603c test: lock IndiaMarketAgents rebrand and ticker scope`
- `c20c7ba test: harden India data source fallbacks`
- `ec1cacb chore: tighten India research prompt language`
- `b3be4b7 feat: harden India report artifacts`
- `8449735 feat: make India dashboard report review read-only`
- `4b8803a chore: complete India security compliance pass`
- `3bab168 docs: add IndiaMarketAgents PR readiness package`
- `9c3347b docs: add Codex session handoff`

## 8. How to verify the work

Run from `/Users/tanaygabhawala/Documents/Github_Indian stocks trading`:

1. Check branch and cleanliness:

```bash
git status --branch --short
git rev-parse --short HEAD
```

Expected:

- Branch is `india-market-agents`.
- Head is `9c3347b` before committing the usage-playbook docs.
- Worktree should be clean after the usage-playbook docs are committed.

2. Check formatting/whitespace:

```bash
git diff --check
```

Expected: no output and exit code 0.

3. Run offline tests:

```bash
python3 -m pytest -m "not integration" -q
```

Expected at commit `3bab168`: 373 passed, 1 deselected, 7 warnings, 75 subtests passed.

4. Run security/compliance scans:

```bash
git grep -n -I -E 'sk-[A-Za-z0-9_-]{8,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY' -- . ':(exclude).env.example' ':(exclude).env.example.india' ':(exclude).env.enterprise.example'
git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order' -- README.md README_INDIA.md dashboard cli tradingagents docs tests ':(exclude)docs/CODEX_HANDOFF.md' ':(exclude)tests/test_security_compliance.py'
git ls-files | rg '(^reports/|^data/india/filings/|^data/india/manual/|\.pdf$|__pycache__|\.pyc$|\.db$|\.sqlite$|\.log$)'
```

Expected:

- All three commands return no matches. Note `git grep` exits 1 when no matches are found; that is expected.

5. Check PR:

```bash
gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,author
```

Expected:

- URL: `https://github.com/TauricResearch/TradingAgents/pull/1002`
- `state`: `OPEN`
- `isDraft`: `true`
- `baseRefName`: `main`
- `headRefName`: `india-market-agents`
- `headRepositoryOwner.login`: `tgabhawala-creator`

6. Optional dashboard runtime verification:

```bash
python3 -m pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

Expected:

- Streamlit app starts and displays read-only saved report review if `reports/<SYMBOL>/<DATE>/` exists.
- No broker/order controls should appear.

## 9. Next recommended steps

1. Refresh GitHub CLI authentication:
   ```bash
   gh auth refresh -h github.com
   ```
2. Inspect draft PR #1002 on GitHub.
   - Check whether CI ran.
   - If CI failed, inspect logs before changing code.
   - If no CI is configured or PR is too broad for upstream, decide whether to keep it as a draft or use it as a private fork milestone.
3. If continuing implementation, do not add new data sources or broker integrations casually.
   - Next code work should likely be official-source review for NSE/BSE only after source/legal/access review, or README cleanup to route users to `README_INDIA.md`.
4. Optional: verify dashboard runtime after installing `.[dashboard]`.
5. Optional: update `docs/PR_READINESS.md` or PR body if PR CI or review feedback adds new validation evidence or risks.
6. Keep all generated reports under ignored `reports/` and local filings under ignored `data/india/filings/`.

## 10. Files the next session should read first

1. `.codex/HANDOFF.md`
2. `docs/CODEX_HANDOFF.md`
3. `docs/PR_READINESS.md`
4. `docs/USAGE_PLAYBOOK.md`
5. `AGENTS.md`
6. `README_INDIA.md`
7. `README.md`
8. `cli/main.py`
9. `tradingagents/default_config.py`
10. `tradingagents/dataflows/india/symbols.py`
11. `tradingagents/dataflows/india/quality.py`
12. `tradingagents/graph/analyst_execution.py`
13. `dashboard/report_review.py`
14. `tests/test_security_compliance.py`
15. `tests/test_india_cli_report.py`
16. `tests/test_dashboard_report_review.py`

## 11. Prompt for the next Codex chat

Paste this into a fresh Codex chat:

```text
You are continuing work in `/Users/tanaygabhawala/Documents/Github_Indian stocks trading`.

First read `.codex/HANDOFF.md`, then inspect the live repo state with:
- `git status --branch --short`
- `git rev-parse --short HEAD`
- `git remote -v`
- `gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,author`

Verify the assumptions in the handoff before making changes. Do not add data sources, agent prompts, dashboard features, broker integrations, or live trading controls unless I explicitly ask.

Current likely next step: refresh GitHub CLI auth with `gh auth refresh -h github.com`, inspect draft PR #1002 and any CI/review status, and decide whether to update the PR body with the usage-playbook evidence. If CI is failing, summarize failures before patching. Keep all changes small, offline-testable, India-only by default, research-only, and compliant with the project rules in `AGENTS.md`.
```
