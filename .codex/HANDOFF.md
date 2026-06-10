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
11. First workflow rehearsal.
12. Ollama preflight hardening.
13. Post-preflight command guidance.
14. Root README quick start.
15. Use-case preflight alignment.
16. Usage playbook command alignment.
17. macOS metadata ignore.
18. Ollama env-template placeholder.
19. Provider-status preflight.
20. Provider-status `.env` guidance.
21. No-overwrite env initialization.
22. First workflow status command.
23. Saved report status command.
24. Provider-aware first-run checklist alignment.
25. Workflow-status saved-report bundle readiness.
26. Auto provider preflight.
27. Use-case generated-analyze guidance.
28. Doctor workflow readiness.
29. Beginner setup generated-command alignment.
30. First-run provider readiness check.
31. Usage playbook acceptance-gate clarification.
32. Provider status configured-provider summary.
33. Workflow status provider-blocker detail.

The branch is already pushed and a draft PR is open:

- Draft PR: https://github.com/TauricResearch/TradingAgents/pull/1002
- Base: `TauricResearch/TradingAgents:main`
- Head: `tgabhawala-creator:india-market-agents`
- PR title: `Transform TradingAgents into IndiaMarketAgents research copilot foundation`

Current objective: make the GitHub repo practically usable and identify the highest-value use case. The current best use case is a first-pass India equity research pack for an NSE/BSE-listed company, using local filings where available and saved report artifacts for analyst review. This is documented in `docs/USAGE_PLAYBOOK.md`, available from `indiamarketagents use-case`, and executable through `docs/FIRST_RUN_CHECKLIST.md`.

## 2. Current repo state

Current follow-up state as of 2026-06-11:

- Latest HEAD before this workflow-status provider-blocker update: `f535c33 feat: show configured provider status`.
- Branch was clean and synced with `origin/india-market-agents` at the latest inspection before this update.
- The active goal is partly complete: the repo can now be used for no-key workflow rehearsal, saved-report review, provider readiness checks, and identification of the highest-value use case. The real LLM-backed `analyze` run remains blocked on provider configuration.
- `.codex/HANDOFF.md` was committed as `9c3347b docs: add Codex session handoff` and pushed to `origin/india-market-agents`.
- A draft PR remains open: https://github.com/TauricResearch/TradingAgents/pull/1002.
- GitHub CLI PR inspection can read PR #1002, which is open, draft, and currently reports no status checks in `statusCheckRollup`.
- GitHub PR body was updated from `docs/PR_READINESS.md` after the first-run provider-readiness update.
- `docs/USAGE_PLAYBOOK.md` is included in the usage-playbook docs phase.
- `docs/FIRST_RUN_CHECKLIST.md` is included in the first-run usability phase.
- `indiamarketagents first-run-check` is included in the first-run preflight phase.
- `indiamarketagents sample-report` is included in the offline sample-report phase.
- Offline CLI commands lazy-load `TradingAgentsGraph`, so help/doctor/preflight/sample-report do not pay analysis startup cost.
- `indiamarketagents use-case` is included in the CLI use-case guidance phase.
- The installed `indiamarketagents` console script has been used to rehearse the documented first workflow through `use-case`, `sample-report`, and `first-run-check`.
- `reports/RELIANCE.NS/2026-06-05/` now exists locally as an ignored offline sample bundle with `complete_report.md`, section files, `sources.md`, `data_quality.json`, `summary.json`, `disclaimer.md`, and `compliance.md`.
- A passing `first-run-check` now returns and prints the exact shallow `indiamarketagents analyze` command to run next, plus the expected report path.
- `README.md` now opens with an IndiaMarketAgents quick start before the retained upstream TradingAgents content.
- `docs/BEGINNER_SETUP.md` now uses `init-env`, readiness commands, and the `first-run-check` generated `analyze` command instead of manual `.env` copying or a hardcoded OpenAI command.
- `indiamarketagents use-case` now tells users to run the provider-specific `analyze` command printed by `first-run-check`, instead of hardcoding OpenAI.
- `indiamarketagents init-env` now creates a local `.env` from `.env.example.india` only when `.env` is missing and never overwrites an existing local env file.
- `indiamarketagents provider-status` now shows the local `.env` file path/status, configured provider, and OpenAI, Google, Anthropic, and Ollama readiness offline without printing secrets, echoing configured endpoint values, or calling endpoints.
- `indiamarketagents first-run-check` now auto-selects a ready provider when `--provider` is omitted, while preserving explicit provider selection.
- `indiamarketagents first-run-check` now reports no selected provider plus a single `Provider readiness` failure when no provider path is ready, before users spend on analysis.
- `indiamarketagents workflow-status` now summarizes saved-report bundle readiness, provider readiness, and first-run preflight status, then prints the next unfinished step.
- `indiamarketagents workflow-status` now includes the configured provider and missing credential/runtime detail when no provider path is ready.
- `indiamarketagents doctor` now surfaces provider readiness, saved-report bundle readiness, first-workflow readiness, and the next unfinished first-workflow step.
- `indiamarketagents report-status` now checks saved report bundle artifacts and summarizes `data_quality.json` without live calls or writes.
- `docs/USAGE_PLAYBOOK.md` now directs users to run the shallow `analyze` command printed by `first-run-check`, with a provider-aware OpenAI example.
- `docs/USAGE_PLAYBOOK.md` now separates no-key rehearsal readiness from first LLM-backed research-run readiness; provider readiness plus a passing `first-run-check` is the gate for the first real research run.
- `.gitignore` now ignores `.DS_Store` so local macOS metadata does not appear as untracked repo noise.
- `.env.example.india` now includes `OLLAMA_BASE_URL=` so the local template matches the Ollama preflight/docs path.
- The real `analyze` run is not ready yet because no LLM provider is configured: local `.env` exists but `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, and `OLLAMA_BASE_URL` are empty; `ollama` is not on PATH.

Latest local inspection commands:

- `git status --branch --short`: `## india-market-agents...origin/india-market-agents`.
- `git branch --show-current`: `india-market-agents`.
- `git log -1 --oneline`: `f535c33 feat: show configured provider status` before the workflow-status provider-blocker update.
- `python --version`: failed with `zsh:1: command not found: python`.
- `python3 --version`: `Python 3.14.5`.

Additional state:

- Local branch tracks `origin/india-market-agents`.
- Remotes:
  - `origin`: `https://github.com/tgabhawala-creator/TradingAgents_India.git`
  - `upstream`: `https://github.com/TauricResearch/TradingAgents.git`
- `origin` is the user fork with admin permission.
- `upstream` is read-only for the authenticated GitHub account.
- Draft PR `#1002` is open and draft.

`.codex/HANDOFF.md` is tracked and pushed.

Branch scope relative to `upstream/main`:

- `git rev-list --count upstream/main..HEAD`: 50 after this workflow-status provider-blocker update is committed.
- `git diff --stat upstream/main`: 78 files changed, 7534 insertions, 228 deletions after this workflow-status provider-blocker update.

Material file changes by area:

- Project docs and attribution:
  - `AGENTS.md`: future-agent rules for India-only scope, no live trading, no secrets, tests, data integrity, compliance, and handoff updates.
  - `NOTICE`: upstream attribution retained/extended.
  - `README.md`: IndiaMarketAgents quick start, fork preface, and removal of the most direct simulated-exchange execution wording.
  - `README_INDIA.md`: India-specific setup, usage, disclaimers, dashboard instructions.
  - `docs/USAGE_PLAYBOOK.md`: practical first workflow and highest-value use case for using the repo.
  - `docs/FIRST_RUN_CHECKLIST.md`: credential-safe setup, first analysis, output review, and acceptance checks.
  - `docs/BEGINNER_SETUP.md`: beginner install and first-analysis path aligned to `init-env`, readiness checks, and generated analysis commands.
  - `cli/main.py`: includes `doctor` workflow-readiness output, `first-run-check` offline provider-readiness preflight, and `sample-report` saved-report workflow rehearsal.
  - `cli/main.py`: lazy-loads `TradingAgentsGraph` so offline commands stay cheap.
  - `cli/main.py`: includes `use-case` guidance for the recommended first workflow.
  - `cli/main.py`: includes `report-status` for saved-report artifact review readiness.
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
- `.codex/HANDOFF.md` is tracked, committed, and kept current for restart-ready handoffs.

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
- Updated `docs/CODEX_HANDOFF.md` and `docs/PR_READINESS.md` to reflect the usage phase and current PR status.
- Added `docs/FIRST_RUN_CHECKLIST.md` and linked it from `README_INDIA.md`, `docs/USAGE_PLAYBOOK.md`, and `docs/BEGINNER_SETUP.md`.
- Added `indiamarketagents first-run-check` and unit tests for first-run readiness.
- Added `indiamarketagents sample-report` and unit tests for explicit sample/UNAVAILABLE saved-report bundles.
- Lazy-loaded `TradingAgentsGraph` so offline commands stay fast and do not import the full analysis graph until `analyze` runs.
- Added `indiamarketagents use-case` and unit tests for the recommended workflow guidance.
- Rehearsed the documented first workflow with installed console-script commands:
  - `indiamarketagents use-case`: passed.
  - `indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05`: passed and generated the ignored local sample report bundle.
  - `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed only because `OPENAI_API_KEY` is not configured.
- Hardened the Ollama preflight path:
  - `first-run-check --provider ollama` now requires either a local `ollama` command on `PATH` or `OLLAMA_BASE_URL`.
  - The check remains offline and does not call the Ollama endpoint or verify model availability.
  - Added unit tests for missing Ollama runtime and configured `OLLAMA_BASE_URL`.
  - Updated first-run docs and README guidance for local Ollama configuration.
- Added post-preflight command guidance:
  - `run_first_run_checks()` now returns `next_command` and `report_path` when ready.
  - `first-run-check` now prints the generated shallow `indiamarketagents analyze` command after a passing preflight.
  - Added unit tests for generated first-analysis commands.
- Added a root README quick start:
  - Routes new users to the IndiaMarketAgents workflow before the retained upstream TradingAgents content.
  - States the highest-value use case directly in the root README.
  - Updates `README_INDIA.md` to run the shallow `analyze` command printed by `first-run-check`.
- Aligned `indiamarketagents use-case` with the preflight-generated command flow:
  - `get_use_case_guidance()` now reuses `build_first_analysis_command()`.
  - Use-case notes tell users to run `analyze` only after `first-run-check` passes.
  - Added regression coverage for the provider-aware use-case command and notes.
- Aligned the usage playbook first-analysis section with the generated command flow:
  - The playbook now says to run the shallow `analyze` command printed by `first-run-check`.
  - The example includes `--provider openai` so it matches the default preflight command shape.
- Ignored macOS metadata:
  - Added `.DS_Store` to `.gitignore`.
  - Left the existing local `.DS_Store` in place; it is ignored and not tracked.
- Added Ollama env-template placeholder:
  - Added `OLLAMA_BASE_URL=` to `.env.example.india`.
  - Created ignored local `.env` from `.env.example.india`; all provider placeholders remain empty.
  - Added regression coverage so the India env template keeps the Ollama placeholder.
- Added provider-status preflight:
  - Added `indiamarketagents provider-status` to show OpenAI, Google, Anthropic, and Ollama readiness without live calls or secret values.
  - Updated `indiamarketagents use-case`, README quick starts, the usage playbook, and first-run checklist to include `provider-status` before `first-run-check`.
  - Added unit coverage for no-provider and Ollama-preferred provider-status paths.
- Added provider-status `.env` guidance:
  - `provider-status` now prints whether the local `.env` file exists and the exact path it is checking.
  - Missing-key next steps now point to that local `.env` path.
  - Configured `OLLAMA_BASE_URL` checks no longer echo the endpoint value in `provider-status` or `first-run-check`.
  - Added regression coverage for `.env` path reporting and no endpoint echoing.
- Added no-overwrite env initialization:
  - Added `indiamarketagents init-env` to create local `.env` from `.env.example.india` only when `.env` is missing.
  - Existing `.env` files are left unchanged.
  - Updated README, India README, first-run checklist, usage playbook, and `use-case` guidance to use `init-env`.
  - Added regression coverage for `.env` creation and no-overwrite behavior.
- Added first workflow status command:
  - Added `indiamarketagents workflow-status` to show ticker/date, saved-report bundle, provider, and first-run preflight status without live calls.
  - The command prints the next unfinished workflow step, or the generated shallow `analyze` command when preflight is ready.
  - Updated README, India README, first-run checklist, usage playbook, and `use-case` guidance to include `workflow-status`.
  - Added regression coverage for missing-provider and ready-Ollama workflow states.
- Added saved report status command:
  - Added `indiamarketagents report-status` to verify saved-report artifacts and summarize `data_quality.json` without live calls or writes.
  - Updated README, India README, first-run checklist, usage playbook, and `use-case` guidance to include the saved-report review checkpoint.
  - Added regression coverage for missing and complete saved-report bundles.
- Aligned first-run checklist with generated analysis command:
  - Updated `docs/FIRST_RUN_CHECKLIST.md` so the shallow OpenAI analysis example uses `indiamarketagents analyze` and includes `--provider openai`.
  - Added regression coverage so the checklist keeps the provider-aware analyze example.
- Tightened workflow status saved-report readiness:
  - `workflow-status` now checks the full saved-report bundle through the same readiness logic as `report-status`, instead of passing on `complete_report.md` alone.
  - Added regression coverage for incomplete saved-report bundles.
- Added auto provider preflight:
  - `first-run-check` now auto-selects the ready provider preferred by `provider-status` when `--provider` is omitted.
  - The recommended first workflow now uses provider-agnostic `first-run-check`; users can still pass `--provider` to force OpenAI, Google, Anthropic, or Ollama.
  - Added regression coverage for auto-selecting ready Ollama without echoing endpoint values.
- Aligned use-case guidance with generated analysis command:
  - `indiamarketagents use-case` no longer hardcodes an OpenAI `analyze` command as the final workflow step.
  - The final use-case step now points users to the provider-specific `analyze` command printed by `first-run-check`.
  - Added regression coverage so use-case guidance does not drift back to a static provider command.
- Added doctor workflow readiness:
  - `indiamarketagents doctor` now reports provider readiness, preferred provider, saved-report bundle readiness, first-workflow readiness, and the next unfinished first-workflow step.
  - Added regression coverage for missing-provider doctor output and ready-Ollama doctor output.
- Aligned beginner setup with generated analysis command:
  - `docs/BEGINNER_SETUP.md` now uses `indiamarketagents init-env` instead of manual `.env` copying.
  - The beginner first-analysis path now runs `report-status`, `provider-status`, `workflow-status`, and provider-agnostic `first-run-check`.
  - Removed the hardcoded OpenAI preflight and static `analyze` command from the beginner path.
  - Added regression coverage so beginner setup keeps the safe generated-command flow.
- Added first-run provider readiness check:
  - `first-run-check` now reports no selected provider and adds a single `Provider readiness` failure when `--provider` is omitted and no provider path is ready.
  - The failure uses the same next setup step as `provider-status`.
  - `docs/FIRST_RUN_CHECKLIST.md` now describes the provider-readiness row.
  - Added regression coverage for the no-provider-ready first-run preflight output.
- Clarified usage-playbook acceptance gates:
  - `docs/USAGE_PLAYBOOK.md` now separates no-key workflow rehearsal readiness from first LLM-backed research-run readiness.
  - The playbook says full research-run readiness requires a ready provider path and a passing `first-run-check`.
  - Added regression coverage so the playbook cannot drift back to implying that `doctor` plus ticker rejection is enough for full research readiness.
- Added configured-provider visibility to provider status:
  - `provider-status` now shows the configured provider from `TRADINGAGENTS_LLM_PROVIDER` or the default config.
  - The current local output makes the actionable blocker explicit: configured provider `openai` is missing `OPENAI_API_KEY`.
  - Added regression coverage for default-config and env-configured provider summaries.
- Added configured-provider blocker detail to workflow status:
  - `workflow-status` now carries the same configured-provider blocker in its provider row.
  - The current local output shows `openai` is configured but missing `OPENAI_API_KEY`.
  - Added regression coverage and first-run doc wording for this detail.

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
- Updated `README.md` with IndiaMarketAgents quick start, fork preface, and research-only/no-simulated-exchange wording.

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
- Root README keeps upstream content for attribution/background, but now routes users through the IndiaMarketAgents quick start first.
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
- PR #1002 is open and draft. Latest `statusCheckRollup` was empty, so no GitHub status checks were reported.
- PR body was updated from `docs/PR_READINESS.md` after the first-run provider-readiness update.
- Unknown: whether upstream maintainers want this broad fork transformation in the upstream repo; PR is draft.

## 7. Commands run and results

Important repo/env commands:

- `git status --branch --short`: `## india-market-agents...origin/india-market-agents`.
- `git branch --show-current`: `india-market-agents`.
- `git log -1 --oneline`: `d90f410 fix: clarify missing provider preflight`.
- `python --version`: failed with `zsh:1: command not found: python`.
- `python3 --version`: `Python 3.14.5`.
- `git rev-list --count upstream/main..HEAD`: `50` after this workflow-status provider-blocker update is committed.
- `git diff --stat upstream/main`: 78 files changed, 7534 insertions, 228 deletions after this workflow-status provider-blocker update.

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
- `git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order'` with handoff, PR-readiness, and test assertion files excluded: no matches.
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
- `gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,statusCheckRollup,updatedAt`: passed later; PR is open, draft, and currently has no reported status checks.
- `gh pr edit 1002 --repo TauricResearch/TradingAgents --body-file docs/PR_READINESS.md`: failed with `HTTP 401: Requires authentication`.
- `gh api repos/TauricResearch/TradingAgents/pulls/1002 -X PATCH -F body=@docs/PR_READINESS.md`: failed with `HTTP 401: Requires authentication`.
- `gh auth refresh -h github.com`: requires browser device-code reauthentication; command was stopped rather than left running.
- `gh pr edit 1002 --repo TauricResearch/TradingAgents --body-file docs/PR_READINESS.md`: later passed and updated the PR body.
- `python3 -m cli.main --help`: passed.
- `python3 -m cli.main doctor --ticker RELIANCE.NS`: passed; ticker validation returned `RELIANCE.NS`; no LLM/API keys detected.
- `python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed as expected when `OPENAI_API_KEY` was not configured.
- `OPENAI_API_KEY=test-openai-key python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: passed without live market, broker, or LLM calls.
- `python3 -m cli.main sample-report --ticker RELIANCE.NS --date 2026-06-05 --save-path /tmp/ima-sample-report.EBbwOv`: passed and generated the full saved-report bundle with sample/UNAVAILABLE markers.
- `indiamarketagents use-case`: passed and printed the highest-value workflow from the installed console script.
- `indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05`: passed and generated `reports/RELIANCE.NS/2026-06-05/complete_report.md` plus companion review artifacts.
- `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed as expected because `OPENAI_API_KEY` is not configured; ticker, date, analyst selection, and report path checks passed.
- `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider ollama`: failed as expected because neither the local `ollama` command nor `OLLAMA_BASE_URL` is configured; ticker, date, analyst selection, and report path checks passed.
- `OPENAI_API_KEY=test-openai-key python3 -c 'from cli.main import run_first_run_checks; ...'`: passed; returned `ready=True`, the generated shallow `indiamarketagents analyze` command, and the expected report path.
- `python3 -m cli.main analyze --ticker AAPL --date 2026-06-05 --no-display --no-save-prompt`: rejected `AAPL` as expected under India-only defaults.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py::test_usage_playbook_distinguishes_rehearsal_from_research_readiness -q`: 1 passed.
- `python3 -m cli.main provider-status`: passed; showed configured provider `openai` from `TRADINGAGENTS_LLM_PROVIDER` and reported `OPENAI_API_KEY` missing without printing secrets.
- `python3 -m cli.main workflow-status --ticker RELIANCE.NS --date 2026-06-05`: passed; provider row now includes configured provider `openai` and missing `OPENAI_API_KEY`.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py -q`: 20 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py tests/test_india_cli_report.py tests/test_dashboard_report_review.py -q`: 23 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py::test_user_facing_docs_do_not_advertise_order_execution tests/test_security_compliance.py::test_no_tracked_generated_reports_filings_or_bytecode -q`: 2 passed.
- `python3 -c 'from cli.main import get_use_case_guidance; ...'`: passed and printed the provider-aware shallow `indiamarketagents analyze` command plus preflight notes.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py::test_use_case_guidance_names_best_workflow_and_commands -q`: 1 passed.
- `rg -n 'First Analysis Run|--provider openai|generated by your successful|printed by `first-run-check`' docs/USAGE_PLAYBOOK.md README.md README_INDIA.md docs/FIRST_RUN_CHECKLIST.md`: passed and confirmed the generated-command wording.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py::test_user_facing_docs_do_not_advertise_order_execution -q`: 1 passed.
- `git status --branch --short`: no longer reports `.DS_Store` as untracked after the `.gitignore` update.
- `git check-ignore .DS_Store`: passed.
- `awk -F= ... .env.example.india .env`: confirmed provider placeholders are empty, including `OLLAMA_BASE_URL=`.
- `git check-ignore .env .DS_Store`: passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_ollama_base_url.py::test_india_env_example_includes_ollama_base_url -q`: 1 passed.
- `python3 -m cli.main provider-status`: passed and reported that no keyed provider is configured and neither `ollama` nor `OLLAMA_BASE_URL` is available; printed the lowest-cost Ollama setup path.
- `python3 -m cli.main use-case`: passed and included `provider-status` before `first-run-check`.
- `indiamarketagents provider-status`: passed and reported the same missing-provider state from the installed console script.
- `indiamarketagents use-case`: passed and included `provider-status` before `first-run-check`.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py::test_provider_status_reports_no_ready_provider tests/test_india_cli_report.py::test_provider_status_prefers_ready_ollama_for_low_cost tests/test_india_cli_report.py::test_use_case_guidance_names_best_workflow_and_commands -q`: 3 passed.
- `indiamarketagents provider-status`: passed and showed the local `.env` path/status while reporting the current missing-provider state.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main provider-status`: passed and reported `OLLAMA_BASE_URL is set` without echoing the endpoint value.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider ollama`: passed and printed the generated shallow `analyze` command without echoing the endpoint value.
- `indiamarketagents init-env`: passed and reported that the existing local `.env` was left unchanged.
- `indiamarketagents use-case`: passed and included `init-env` before `provider-status`.
- `python3 -m cli.main --help`: passed and listed `init-env`.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py -q`: 20 passed.
- `indiamarketagents workflow-status --ticker RELIANCE.NS --date 2026-06-05`: passed and reported provider setup as the next unfinished step.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main workflow-status --ticker RELIANCE.NS --date 2026-06-05`: passed and printed the generated shallow `analyze` command.
- `indiamarketagents report-status --ticker RELIANCE.NS --date 2026-06-05`: passed from the installed console script and showed all saved sample-report artifacts as present.
- `python3 -m cli.main --help`: passed and listed `workflow-status` and `report-status`.
- `python3 -m cli.main use-case`: passed and directed users to the `analyze` command printed by `first-run-check`.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --analysts india_market`: passed and auto-selected Ollama.
- `python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05`: failed as expected on the configured default OpenAI provider because no provider is locally ready.
- `python3 -m cli.main doctor --ticker RELIANCE.NS`: passed and reported the current provider setup blocker in first-workflow readiness.
- `indiamarketagents doctor --ticker RELIANCE.NS`: passed from the installed console script and reported the same provider setup blocker.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main doctor --ticker RELIANCE.NS`: passed and reported the generated shallow `indiamarketagents analyze` command as the first-workflow next step.
- `rg -n 'cp \.env\.example\.india \.env|first-run-check --ticker RELIANCE\.NS --date 2026-06-05 --provider openai|analyze --ticker RELIANCE\.NS --date 2026-06-05 --research-depth 1' docs/BEGINNER_SETUP.md README.md README_INDIA.md docs/USAGE_PLAYBOOK.md docs/FIRST_RUN_CHECKLIST.md`: no matches after the beginner setup alignment update.
- `python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05`: failed as expected, showed no selected provider, and included only `Provider readiness` for the provider setup blocker.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --analysts india_market`: passed and printed the generated shallow `indiamarketagents analyze` command.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py -q`: 30 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py::test_user_facing_docs_do_not_advertise_order_execution tests/test_security_compliance.py::test_no_tracked_generated_reports_filings_or_bytecode -q`: 2 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -m "not integration" -q`: 397 passed, 1 deselected, 7 warnings, 75 subtests passed.

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
- `9be81c3 docs: add IndiaMarketAgents usage playbook`
- `035f8a3 docs: refresh IndiaMarketAgents PR status`
- `5798077 docs: note GitHub PR body auth blocker`
- `5e7d693 docs: add first-run research checklist`
- `dabde63 docs: confirm PR body refresh`
- `5bd0c30 feat: add first-run readiness check`
- `ab6c095 feat: add offline sample report workflow`
- `2354073 perf: lazy load analysis graph for offline CLI`
- `c35415e feat: add use-case guidance command`
- `c756028 docs: record first workflow rehearsal`
- `d2d9c22 fix: validate Ollama runtime in first-run check`
- `3e8e81f feat: print next analysis command after preflight`
- `2c08eb0 docs: add IndiaMarketAgents root quick start`
- `d88eb94 fix: align use-case command with preflight flow`
- `327ea4f docs: align usage playbook with preflight command`
- `a6c463c chore: ignore macOS metadata`
- `dc7676a chore: add Ollama endpoint placeholder`
- `b2723a0 feat: add provider readiness status`
- `21a94dc docs: refresh provider status handoff`
- `988cb62 fix: clarify provider env setup`
- `3b2b032 feat: add no-overwrite env initialization`
- `74bd87a docs: refresh init-env handoff`
- `ef78289 feat: add first workflow status`
- `55b58b3 feat: add saved report status`
- `6953e86 docs: align first-run analyze command`
- `17ea5f4 fix: require complete report bundle in workflow status`
- `97d7bfc feat: auto-select ready provider in preflight`

## 8. How to verify the work

Run from `/Users/tanaygabhawala/Documents/Github_Indian stocks trading`:

1. Check branch and cleanliness:

```bash
git status --branch --short
git rev-parse --short HEAD
```

Expected:

- Branch is `india-market-agents`.
- Head is this handoff/status refresh commit, with `d90f410` as the latest implementation commit before the refresh.
- Worktree should be clean after this handoff/status refresh is committed.

2. Check formatting/whitespace:

```bash
git diff --check
```

Expected: no output and exit code 0.

3. Run offline tests:

```bash
python3 -m pytest -m "not integration" -q
```

Expected after the workflow-status provider-blocker update: 397 passed, 1 deselected, 7 warnings, 75 subtests passed.

4. Run security/compliance scans:

```bash
git grep -n -I -E 'sk-[A-Za-z0-9_-]{8,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY' -- . ':(exclude).env.example' ':(exclude).env.example.india' ':(exclude).env.enterprise.example'
git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order' -- README.md README_INDIA.md dashboard cli tradingagents docs tests ':(exclude)docs/CODEX_HANDOFF.md' ':(exclude)docs/PR_READINESS.md' ':(exclude)tests/test_security_compliance.py'
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

1. Run `indiamarketagents provider-status` to confirm the current provider blocker and recommended setup path.
2. Configure an LLM provider: add an API key for a keyed provider or configure Ollama with a local `ollama` command or `OLLAMA_BASE_URL`.
3. Run `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider <provider>` after the provider is configured.
4. Run the generated shallow `indiamarketagents analyze` command after preflight passes.
5. Inspect PR #1002 again if GitHub status checks or reviewer feedback appear.
6. If continuing implementation, do not add new data sources or broker integrations casually.
   - Next code work should likely be official-source review for NSE/BSE only after source/legal/access review, or README cleanup to route users to `README_INDIA.md`.
7. Optional: verify dashboard runtime after installing `.[dashboard]`.
8. Optional: update `docs/PR_READINESS.md` if PR CI or review feedback adds new validation evidence or risks.
9. Keep all generated reports under ignored `reports/` and local filings under ignored `data/india/filings/`.

## 10. Files the next session should read first

1. `.codex/HANDOFF.md`
2. `docs/CODEX_HANDOFF.md`
3. `docs/PR_READINESS.md`
4. `docs/USAGE_PLAYBOOK.md`
5. `docs/FIRST_RUN_CHECKLIST.md`
6. `AGENTS.md`
7. `README_INDIA.md`
8. `README.md`
9. `cli/main.py`
10. `tradingagents/default_config.py`
11. `tradingagents/dataflows/india/symbols.py`
12. `tradingagents/dataflows/india/quality.py`
13. `tradingagents/graph/analyst_execution.py`
14. `dashboard/report_review.py`
15. `tests/test_security_compliance.py`
16. `tests/test_india_cli_report.py`
17. `tests/test_dashboard_report_review.py`

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

Current likely next step: configure an LLM provider by adding an API key for a keyed provider or configuring Ollama with a local `ollama` command or `OLLAMA_BASE_URL`, rerun `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider <provider>`, then run the generated shallow `indiamarketagents analyze` command once preflight passes. If CI or review feedback appears, summarize failures before patching. Keep all changes small, offline-testable, India-only by default, research-only, and compliant with the project rules in `AGENTS.md`.
```
