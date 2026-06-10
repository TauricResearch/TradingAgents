# Codex Handoff

Date: 2026-06-11
Branch: `india-market-agents`
Latest phase: Provider-status `.env` guidance

## Project Goal

Transform `TauricResearch/TradingAgents` into `IndiaMarketAgents`: an India-first, India-only institutional market research copilot for Indian listed equities, Indian indices, Indian macro context, Indian filings, Indian market flows, and Indian regulatory/compliance context.

The product is research and decision support only. It must not become a live trading or broker execution system.

## Current Status

- The repo is on branch `india-market-agents`.
- The branch is ahead of `upstream/main`.
- Apache 2.0 license text is present in `LICENSE`.
- Upstream attribution is present in `NOTICE`.
- Branch review confirms `india-market-agents` is clean and 33 commits ahead of `upstream/main` after the provider-status `.env` guidance commit.
- `.codex/HANDOFF.md` was committed and pushed to `origin/india-market-agents`.
- `docs/USAGE_PLAYBOOK.md` now documents the recommended first workflow and highest-value practical use case.
- `docs/FIRST_RUN_CHECKLIST.md` now documents credential-safe setup and acceptance checks for the first `RELIANCE.NS` research pack.
- `indiamarketagents first-run-check` now verifies first-run readiness without live market, broker, or LLM calls.
- `indiamarketagents sample-report` now creates explicit sample/UNAVAILABLE saved-report bundles without live market, broker, or LLM calls.
- Offline commands now lazy-load the heavy graph class, so help/doctor/preflight/sample-report do not pay analysis startup cost.
- `indiamarketagents use-case` now prints the recommended highest-value use case and first workflow commands.
- The documented first workflow has been rehearsed with the installed `indiamarketagents` console script through `use-case`, `sample-report`, and `first-run-check`.
- `indiamarketagents first-run-check --provider ollama` now verifies local Ollama runtime configuration instead of passing solely because no API key is required.
- A passing `first-run-check` now returns and prints the exact shallow `indiamarketagents analyze` command to run next, plus the expected report path.
- `README.md` now has an IndiaMarketAgents quick-start section before the retained upstream TradingAgents README content.
- `indiamarketagents use-case` now reuses the preflight command builder and tells users to run analysis only after `first-run-check` passes.
- `indiamarketagents provider-status` now shows the local `.env` path/status and checks OpenAI, Google, Anthropic, and Ollama readiness offline without printing secrets, echoing configured endpoint values, or calling endpoints.
- `docs/USAGE_PLAYBOOK.md` now directs users to run the shallow `analyze` command printed by `first-run-check`, with a provider-aware OpenAI example.
- `.gitignore` now ignores `.DS_Store` so local macOS metadata does not appear as untracked repo noise.
- `.env.example.india` now includes `OLLAMA_BASE_URL=` so the local template matches the Ollama preflight/docs path.
- PR #1002 is open and draft; `statusCheckRollup` is currently empty.
- `docs/PR_READINESS.md` now contains a PR title, summary, completed-work list, validation evidence, remaining risks, reviewer focus areas, and checklist.
- Final verification passed with the offline unit suite and targeted security/compliance scans.
- No data-source, agent prompt, dashboard feature, or broker code changes were made in this phase.

## Completed Phases

1. Documentation bootstrap and audit:
   - Updated future-agent operating rules.
   - Created/updated handoff and audit docs.
   - Kept scope limited to documentation; no heavy refactors.
2. Rebrand, India-only validation, India config, and tests:
   - Rebranded package metadata description and README_INDIA install path.
   - Added regression coverage for default India config, console script aliases, legacy ticker escape hatch, report path safety, and non-interactive report path generation.
   - Kept scope limited to rebrand/config/ticker/report-path behavior; no data-source, agent, or dashboard changes.
3. Data-source layer hardening:
   - Added current-run data-quality rendering helpers.
   - Hardened local filing output with source coverage, read warnings, and PDF no-OCR caveats.
   - Added yfinance India source notes to make third-party fallback provenance explicit.
   - Added offline tests using temp files and monkeypatched vendors.
4. India analyst prompt and decision-language review:
   - Tightened India analyst prompts for research-only output, India-market scope, data-quality caveats, unavailable-source handling, and no fabrication.
   - Revised downstream Researcher, Trader, Risk, and Portfolio prompts where needed to avoid live-trading wording and order-placement instructions.
   - Updated structured Trader schema/rendering terminology from transaction proposal to model research view.
   - Added offline prompt-language tests and isolated legacy structured-agent tests from India-only ticker validation.
5. Report/disclaimer and saved-artifact review:
   - Added compliance disclaimers to every standalone saved section file.
   - Added writer-generated source/data-quality coverage tables in `complete_report.md`, `sources.md`, and `data_quality.json`.
   - Added a standalone `trader_research_view.md` artifact while keeping the existing portfolio filename for compatibility.
   - Added offline tests for disclaimer placement, artifact notes, source coverage indexing, unavailable-section handling, and summary metadata.
6. Read-only dashboard/report review:
   - Refactored dashboard report discovery/rendering into pure helpers that do not import Streamlit.
   - Expanded the dashboard tabs to show all saved report-review artifacts, including `sources.md` and formatted `data_quality.json`.
   - Kept the dashboard explicitly read-only with visible research-only/no-live-trading language.
   - Added offline tests for saved-report discovery, companion compliance rendering, data-quality formatting, optional Streamlit import behavior, and absence of live-trading controls.
7. Security/compliance final pass:
   - Scanned tracked files for secret-like values, generated artifacts, local filing material, broker/live-trading affordances, unsafe report writes, and user-facing execution wording.
   - Removed simulated-exchange execution language from the user-facing README.
   - Moved report-writer India ticker validation ahead of output-directory creation.
   - Added offline security/compliance regression tests and neutralized fake API-key prefixes in tests.
8. Final branch review and PR-readiness package:
   - Reviewed branch status, commit history, changed-file scope, and remaining risks.
   - Added a concise PR-readiness package for reviewers.
   - Re-ran final offline validation and targeted security/compliance scans.
   - Kept scope limited to documentation and branch-readiness review.
9. Usage playbook and best-use-case guidance:
   - Pushed the committed `.codex/HANDOFF.md` to `origin/india-market-agents`.
   - Added `docs/USAGE_PLAYBOOK.md` with the best first use case, setup path, expected report artifacts, review workflow, and current limits.
   - Linked the playbook from `README_INDIA.md`.
   - Kept scope limited to documentation and cheap local CLI validation.
10. PR status refresh:
   - Confirmed GitHub CLI auth is working again.
   - Confirmed draft PR #1002 is open and has no reported status checks.
   - Refreshed `docs/PR_READINESS.md` so the PR body can be updated with current usage-playbook evidence.
   - Attempted to update draft PR #1002 body from `docs/PR_READINESS.md`, but GitHub returned `HTTP 401`.
   - `gh auth refresh -h github.com` requires browser device-code reauthentication before PR body updates can be retried.
11. First-run checklist:
   - Added `docs/FIRST_RUN_CHECKLIST.md` with exact install, credential, local-input, first-analysis, output-review, and acceptance steps.
   - Linked the checklist from `README_INDIA.md`, `docs/USAGE_PLAYBOOK.md`, and `docs/BEGINNER_SETUP.md`.
12. PR body refresh:
   - Updated draft PR #1002 body from `docs/PR_READINESS.md` after the first-run checklist update.
13. First-run preflight command:
   - Added `run_first_run_checks()` and `indiamarketagents first-run-check`.
   - Added unit tests for missing-key and ready states.
   - Updated first-run docs to use the preflight before `analyze`.
14. Offline sample-report workflow:
   - Added `generate_sample_report()` and `indiamarketagents sample-report`.
   - Added unit tests for explicit sample/UNAVAILABLE saved-report bundles.
   - Updated first-run docs so users can rehearse report and dashboard review before adding an LLM key.
15. Offline CLI startup improvement:
   - Lazy-loaded `TradingAgentsGraph` so offline commands stay cheap and fast.
   - Preserved `analyze` behavior by loading the graph only when analysis starts.
16. CLI use-case guidance:
   - Added `get_use_case_guidance()` and `indiamarketagents use-case`.
   - Linked the command from `README_INDIA.md`, `docs/FIRST_RUN_CHECKLIST.md`, `docs/USAGE_PLAYBOOK.md`, and `docs/BEGINNER_SETUP.md`.
17. First workflow rehearsal:
   - Ran `indiamarketagents use-case` from the installed console script.
   - Ran `indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05`, generating the ignored sample bundle at `reports/RELIANCE.NS/2026-06-05/`.
   - Ran `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`; ticker/date/analyst/report-path checks passed and the only failed check was missing `OPENAI_API_KEY`.
18. Ollama preflight hardening:
   - Updated `first-run-check --provider ollama` to require either a local `ollama` command on `PATH` or `OLLAMA_BASE_URL`.
   - Kept the check offline; it does not call the Ollama endpoint or verify model availability.
   - Added regression tests for missing Ollama runtime and configured `OLLAMA_BASE_URL`.
   - Updated first-run docs and India README with the Ollama runtime requirement.
19. Post-preflight command guidance:
   - Added `build_first_analysis_command()` and included `next_command`/`report_path` in `run_first_run_checks()`.
   - Updated the `first-run-check` CLI output so a passing preflight prints the next shallow analysis command.
   - Added regression coverage for generated first-analysis commands.
20. Root README quick start:
   - Added an IndiaMarketAgents quick-start block to `README.md` before the upstream TradingAgents content.
   - Made `README_INDIA.md` direct users to run the shallow `analyze` command printed by `first-run-check`.
   - Kept the upstream README content for attribution and framework background.
21. Use-case preflight alignment:
   - Updated `get_use_case_guidance()` to reuse `build_first_analysis_command()`.
   - Added use-case notes that the `analyze` command should run only after `first-run-check` passes and that other providers should use the command printed by preflight.
   - Added regression coverage for the provider-aware use-case command and notes.
22. Usage playbook command alignment:
   - Updated the playbook first-analysis section to use the preflight-generated command as source of truth.
   - Added `--provider openai` to the orientation example so it matches the shallow command builder.
23. macOS metadata ignore:
   - Added `.DS_Store` to `.gitignore`.
   - Left the existing local `.DS_Store` file in place; it is ignored and not tracked.
24. Ollama env-template placeholder:
   - Added `OLLAMA_BASE_URL=` to `.env.example.india`.
   - Created an ignored local `.env` from `.env.example.india`; all provider values remain empty.
   - Added regression coverage so the India env template keeps the Ollama placeholder.
25. Provider-status preflight:
   - Added `indiamarketagents provider-status` to report OpenAI, Google, Anthropic, and Ollama readiness without live calls or secret values.
   - Updated `indiamarketagents use-case`, README quick starts, `docs/USAGE_PLAYBOOK.md`, and `docs/FIRST_RUN_CHECKLIST.md` to include `provider-status` before `first-run-check`.
   - Added regression coverage for missing-provider and Ollama-preferred readiness paths.
26. Provider-status `.env` guidance:
   - `provider-status` now reports whether the local `.env` file exists and shows the exact path it is checking.
   - Missing-key next steps now point to that local `.env` path.
   - Configured `OLLAMA_BASE_URL` checks no longer echo the endpoint value in `provider-status` or `first-run-check`.
   - Added regression coverage for `.env` path reporting and no endpoint echoing.

Prior local commits indicate earlier IndiaMarketAgents work already exists:

- `feat: add India market dataflow profile`
- `feat: wire IndiaMarketAgents agents and CLI`
- `test: cover IndiaMarketAgents validation and reports`

## Files Touched In Latest Phase

- `.codex/HANDOFF.md`
- `cli/main.py`
- `docs/USAGE_PLAYBOOK.md`
- `docs/FIRST_RUN_CHECKLIST.md`
- `docs/BEGINNER_SETUP.md`
- `README_INDIA.md`
- `docs/CODEX_HANDOFF.md`
- `docs/PR_READINESS.md`
- `tests/test_india_cli_report.py`

## Important Design Decisions

- Keep the internal Python package name `tradingagents` for now to avoid high-risk import churn.
- Use `indiamarketagents` as the user-facing CLI alias.
- Keep default config India-only with explicit escape hatch through config for legacy behavior.
- Keep legacy `tradingagents` console script for compatibility while adding IndiaMarketAgents branding.
- Third-party yfinance outputs must carry data-quality notes; official/user-provided sources remain preferred.
- PDF extraction stays disabled by default to avoid expensive/OCR-heavy behavior; users should convert key pages to text notes.
- Prompts should describe outputs as research views, model views, or research plans rather than live trading decisions.
- The final structured Trader marker is now `FINAL MODEL VIEW`; preserve this wording for IndiaMarketAgents report and downstream parsing work.
- Legacy/global structured-agent tests should opt into global scope explicitly when they exercise non-India tickers.
- Saved report artifacts should be usable as standalone files, so section markdown files carry the compliance disclaimer.
- Report-writer source/data-quality coverage flags are marker-detection metadata only; they must not be treated as data verification.
- Keep the existing `9_portfolio_decision.md` filename for compatibility, but title the content as a portfolio research view.
- Keep dashboard logic read-only and report-focused; do not add order buttons, broker controls, chat trading controls, or live execution affordances.
- Keep Streamlit optional. Put testable dashboard logic in non-Streamlit helper modules so offline tests run without installing dashboard extras.
- Validate ticker-derived report paths before creating output directories.
- Use neutral placeholder strings in tests instead of fake values that resemble real provider secret prefixes.
- Tracked `.env.example*` files are intentionally template files; real `.env` files must remain untracked.
- Keep PR-readiness notes concise and evidence-backed; do not use them to introduce new scope.
- Treat the best first workflow as a single-company India equity research pack, not live trading or real-time market monitoring.
- Do not add broker execution or broker integrations.
- Prefer official/user-provided data and explicit unavailable responses over fabricated values.
- Keep live exchange/network tests out of the default test suite.
- Update this file after every phase before committing.

## Baseline Inspection Notes

- `git status` showed a clean worktree before edits.
- `python --version` failed because `python` is not on PATH in this environment.
- Use `python3` for local commands in this workspace unless the environment changes.

## Validation

- `python --version`: failed; `python` is not on PATH.
- `python3 --version`: Python 3.14.5.
- `git status --branch --short`: `india-market-agents...origin/india-market-agents [ahead 1]` before pushing `.codex/HANDOFF.md`; clean after push and before usage-playbook edits.
- `git rev-list --count upstream/main..HEAD`: 33 after the provider-status `.env` guidance commit.
- `git push`: pushed `9c3347b docs: add Codex session handoff` to `origin/india-market-agents`.
- `gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,statusCheckRollup,updatedAt`: passed; PR is open, draft, and currently has no reported status checks.
- `gh pr edit 1002 --repo TauricResearch/TradingAgents --body-file docs/PR_READINESS.md`: failed with `HTTP 401: Requires authentication`.
- `gh api repos/TauricResearch/TradingAgents/pulls/1002 -X PATCH -F body=@docs/PR_READINESS.md`: failed with `HTTP 401: Requires authentication`.
- `gh auth refresh -h github.com`: requires browser device-code reauthentication; command was stopped rather than left running.
- `gh pr edit 1002 --repo TauricResearch/TradingAgents --body-file docs/PR_READINESS.md`: later passed and updated the PR body.
- `python3 -m cli.main --help`: passed.
- `python3 -m cli.main doctor --ticker RELIANCE.NS`: passed; package import and ticker validation were OK; no LLM/API keys detected.
- `python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed as expected when `OPENAI_API_KEY` was not configured.
- `OPENAI_API_KEY=test-openai-key python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: passed without live market, broker, or LLM calls.
- `python3 -m cli.main sample-report --ticker RELIANCE.NS --date 2026-06-05 --save-path /tmp/ima-sample-report.EBbwOv`: passed and generated the full saved-report bundle with sample/UNAVAILABLE markers.
- `python3 -m cli.main --help`, `doctor`, `first-run-check`, and `sample-report`: returned promptly after lazy graph import.
- `python3 -m cli.main use-case`: passed and printed the highest-value workflow.
- `indiamarketagents use-case`: passed and printed the highest-value workflow from the installed console script.
- `indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05`: passed and generated `reports/RELIANCE.NS/2026-06-05/complete_report.md` plus companion review artifacts.
- `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed as expected because `OPENAI_API_KEY` is not configured; ticker, date, analyst selection, and report path checks passed.
- `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider ollama`: failed as expected because neither the local `ollama` command nor `OLLAMA_BASE_URL` is configured; ticker, date, analyst selection, and report path checks passed.
- `OPENAI_API_KEY=test-openai-key python3 -c 'from cli.main import run_first_run_checks; ...'`: passed; returned `ready=True`, the generated shallow `indiamarketagents analyze` command, and the expected report path.
- `python3 -m cli.main analyze --ticker AAPL --date 2026-06-05 --no-display --no-save-prompt`: rejected `AAPL` as expected under India-only defaults.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py -q`: 16 passed.
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
- `git diff --check`: passed.
- `git grep -n -I -E 'sk-[A-Za-z0-9_-]{8,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY' -- .` with `.env.example*` templates excluded: no matches.
- `git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order'` with audit/test assertion files excluded: no matches.
- `git ls-files | rg '(^reports/|^data/india/filings/|^data/india/manual/|\\.pdf$|__pycache__|\\.pyc$|\\.db$|\\.sqlite$|\\.log$)'`: no matches.
- `python3 -m pytest -m "not integration" -q`: 373 passed, 1 deselected, 7 warnings, 75 subtests passed.

## Known Risks And Blockers

- `README.md` still retains the upstream TradingAgents body for attribution/background, but the first user-facing path now routes through the IndiaMarketAgents quick start and India docs.
- NSE/BSE official-source modules are still placeholders; they fail closed and need verified endpoints or local-file workflows before use as live sources.
- NSE/BSE public endpoints can block automation or change response formats.
- yfinance remains third-party fallback data, not an official source.
- Some legacy/global prompt text outside the IndiaMarketAgents path may still use transaction-oriented vocabulary; this phase only changed India analyst prompts and downstream prompts needed for India research-only behavior.
- Some schema field names such as `TraderAction` and `TraderProposal.action` remain for compatibility, even though user-facing language now renders as a model view.
- The saved-report source/data-quality coverage index uses simple marker detection and can produce false positives or false negatives; it is an audit aid, not factual validation.
- `sources.md` does not scrape or retrieve new sources; it indexes coverage markers already present in generated section text.
- Streamlit is an optional dashboard dependency and is not installed in the baseline test environment; dashboard runtime was not browser-verified in this phase.
- Dashboard report discovery reads local `reports/<SYMBOL>/<DATE>/` folders only and does not validate generated report facts.
- `reports/RELIANCE.NS/2026-06-05/` now exists locally as an ignored offline sample bundle from the first workflow rehearsal.
- No LLM provider is ready in this environment yet: local `.env` exists but `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, and `OLLAMA_BASE_URL` are empty; `ollama` is not on PATH.
- Local `__pycache__` files exist from test runs but are ignored by git and were not deleted because deletion was not requested.
- Full package rename would be disruptive and should remain out of scope unless explicitly requested.
- `python` remains unavailable on PATH; use `python3` in this workspace.
- PR #1002 is open and draft, with no reported GitHub status checks at the latest inspection.
- PR body has been updated from `docs/PR_READINESS.md`.

## Next Recommended Prompt

Configure an LLM provider by adding a keyed provider API key or setting up Ollama, rerun `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider <provider>`, then run the generated shallow `indiamarketagents analyze` command. Keep code changes out of scope unless CI or reviewer feedback identifies a specific issue.
