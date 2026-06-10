# PR Readiness Package

Date: 2026-06-11
Branch: `india-market-agents`
Base: `upstream/main`
Branch state: 52 commits ahead of `upstream/main` after this dashboard runtime verification update is committed.
PR status: open draft PR #1002; GitHub currently reports no status checks in `statusCheckRollup`.
PR body: updated from this file after this dashboard runtime verification update.

## PR Title

Transform TradingAgents into IndiaMarketAgents research copilot foundation

## PR Summary

This branch turns the upstream TradingAgents codebase into the first IndiaMarketAgents foundation: an India-first, India-only research and decision-support copilot for Indian listed equities. It adds India ticker validation, India default configuration, India analyst wiring, defensive data-source placeholders, saved-report hardening, read-only dashboard report review, compliance disclaimers, and offline regression coverage.

The branch explicitly does not add live broker execution, broker integrations, or live trading controls. Missing or unsupported market data is handled through explicit `UNAVAILABLE` and low-confidence paths rather than fabricated values.

## Completed Work

- Added IndiaMarketAgents project docs, handoff, audit, setup, security, compliance, and data-source guidance while preserving Apache 2.0 license and upstream attribution.
- Added India-only ticker validation, India config defaults, CLI rebrand aliases, report path safety, and tests.
- Added India dataflow modules for symbols, calendar, formatting, local filings, yfinance India wrapper behavior, quality metadata, and NSE/BSE/macro/flows unavailable responses.
- Wired India analysts, India tool wrappers, graph execution, CLI defaults, and India report writing.
- Tightened India analyst and downstream Researcher/Trader/Risk/Portfolio language for research-only output, data-quality caveats, and no order-placement wording.
- Hardened saved report artifacts with disclaimers, `sources.md`, `data_quality.json`, standalone section files, and writer-level coverage notes.
- Made the dashboard a read-only saved-report reviewer with optional Streamlit dependency and offline-testable helpers.
- Added security/compliance regressions for tracked generated artifacts, report path validation, fake secret prefixes, and user-facing no-execution wording.
- Added a practical usage playbook that identifies the best first use case and a repeatable analyst workflow.
- Added a credential-safe first-run checklist for getting from local setup to a `RELIANCE.NS` research pack.
- Added an offline `first-run-check` CLI command so users can verify first-run readiness before spending on LLM calls.
- Added an offline `sample-report` CLI command so users can verify saved-report and dashboard workflow without LLM credentials.
- Lazy-loaded the heavy graph class so offline CLI commands do not pay graph startup cost.
- Added an offline `use-case` CLI command that states the highest-value use case and first workflow commands.
- Rehearsed the first workflow through the installed `indiamarketagents` console script.
- Hardened `first-run-check --provider ollama` so it requires either a local `ollama` command or `OLLAMA_BASE_URL` instead of passing solely because no API key is needed.
- Added post-preflight command guidance so a passing `first-run-check` prints the exact shallow `analyze` command to run next.
- Added a root README quick start that routes new users to the IndiaMarketAgents workflow before the retained upstream TradingAgents content.
- Aligned `indiamarketagents use-case` with the preflight-generated command flow and provider-aware shallow run.
- Aligned the usage playbook first-analysis section with the preflight-generated command flow.
- Ignored `.DS_Store` so local macOS metadata does not show as untracked repo noise.
- Added `OLLAMA_BASE_URL=` to `.env.example.india` so the template matches the Ollama preflight/docs path.
- Added an offline `provider-status` CLI command so users can see OpenAI, Google, Anthropic, and Ollama readiness without live calls or secret values.
- Updated `provider-status` to show the local `.env` path/status and avoid echoing configured `OLLAMA_BASE_URL` values.
- Added `init-env` so fresh users can create local `.env` from `.env.example.india` without overwriting an existing env file.
- Added `workflow-status` so users can see saved-report bundle, provider, and first-run preflight status plus the next unfinished step.
- Added `report-status` so users can verify saved-report artifacts and review `data_quality.json` before analyst review.
- Browser-verified the optional Streamlit dashboard runtime against the local `RELIANCE.NS` sample report bundle after installing `.[dashboard]`.
- Aligned the first-run checklist's shallow OpenAI analysis example with the generated provider-aware preflight command.
- Tightened `workflow-status` so incomplete saved-report bundles cannot pass readiness just because `complete_report.md` exists.
- Updated `first-run-check` to auto-select a ready provider when `--provider` is omitted, while preserving explicit provider overrides.
- Updated `use-case` so the final workflow step points to the provider-specific `analyze` command printed by `first-run-check`.
- Updated `doctor` so the general health check surfaces provider readiness, saved-report bundle readiness, first-workflow readiness, and the next unfinished first-workflow step.
- Updated beginner setup so fresh users use `init-env`, readiness checks, and the generated `analyze` command instead of manual `.env` copying or a hardcoded OpenAI run path.
- Updated `first-run-check` so the default no-provider-ready path shows no selected provider plus a single `Provider readiness` failure and setup next step.
- Refreshed handoff and PR-readiness status against the current branch, PR, provider-status, workflow-status, doctor, and non-India rejection smoke evidence.
- Split `docs/USAGE_PLAYBOOK.md` acceptance checks into no-key workflow rehearsal readiness and first LLM-backed research-run readiness, with provider readiness plus passing `first-run-check` as the full-use gate.
- Added a non-secret configured-provider summary to `provider-status`, so the current local blocker clearly shows configured provider `openai` and missing `OPENAI_API_KEY`.
- Updated `workflow-status` so its provider row also shows the configured provider and missing credential/runtime detail when no provider path is ready.
- Updated `first-run-check` so its `Provider readiness` row also shows the configured provider and missing credential/runtime detail when no provider path is ready.

## Validation

- `git status --branch --short`: clean, `india-market-agents...origin/india-market-agents` at `405feb1` before this dashboard runtime verification update.
- `git log -1 --oneline`: `405feb1 feat: clarify first-run provider blocker`.
- `git rev-list --count upstream/main..HEAD`: 52 after this dashboard runtime verification update is committed.
- `python --version`: failed because `python` is not on PATH.
- `python3 --version`: Python 3.14.5.
- `git diff --check`: passed.
- `python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed as expected when `OPENAI_API_KEY` was not configured.
- `OPENAI_API_KEY=test-openai-key python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: passed without live market, broker, or LLM calls.
- `python3 -m cli.main sample-report --ticker RELIANCE.NS --date 2026-06-05 --save-path /tmp/ima-sample-report.EBbwOv`: passed and generated the full saved-report bundle with sample/UNAVAILABLE markers.
- `python3 -m cli.main --help`, `doctor`, `first-run-check`, `sample-report`, and `use-case` returned promptly after lazy graph import.
- `python3 -m cli.main use-case`: passed and printed the highest-value workflow.
- `indiamarketagents use-case`: passed and printed the highest-value workflow from the installed console script.
- `indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05`: passed and generated `reports/RELIANCE.NS/2026-06-05/complete_report.md` plus companion review artifacts.
- `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai`: failed as expected because `OPENAI_API_KEY` is not configured; ticker, date, analyst selection, and report path checks passed.
- `indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider ollama`: failed as expected because neither the local `ollama` command nor `OLLAMA_BASE_URL` is configured; ticker, date, analyst selection, and report path checks passed.
- `OPENAI_API_KEY=test-openai-key python3 -c 'from cli.main import run_first_run_checks; ...'`: passed; returned `ready=True`, the generated shallow `indiamarketagents analyze` command, and the expected report path.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py -q`: 20 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py tests/test_india_cli_report.py tests/test_dashboard_report_review.py -q`: 23 passed after the post-preflight command guidance update.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py::test_user_facing_docs_do_not_advertise_order_execution tests/test_security_compliance.py::test_no_tracked_generated_reports_filings_or_bytecode -q`: 2 passed after the root README quick-start update.
- `python3 -c 'from cli.main import get_use_case_guidance; ...'`: passed and printed the provider-aware shallow `indiamarketagents analyze` command plus preflight notes.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py::test_use_case_guidance_names_best_workflow_and_commands -q`: 1 passed after the use-case preflight alignment update.
- `rg -n 'First Analysis Run|--provider openai|generated by your successful|printed by `first-run-check`' docs/USAGE_PLAYBOOK.md README.md README_INDIA.md docs/FIRST_RUN_CHECKLIST.md`: passed and confirmed the generated-command wording.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py::test_user_facing_docs_do_not_advertise_order_execution -q`: 1 passed after the usage playbook command alignment update.
- `git check-ignore .DS_Store`: passed after the macOS metadata ignore update.
- `awk -F= ... .env.example.india .env`: confirmed provider placeholders are empty, including `OLLAMA_BASE_URL=`.
- `git check-ignore .env .DS_Store`: passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_ollama_base_url.py::test_india_env_example_includes_ollama_base_url -q`: 1 passed after the Ollama env-template placeholder update.
- `python3 -m cli.main provider-status`: passed and reported that no keyed provider is configured and neither `ollama` nor `OLLAMA_BASE_URL` is available; printed the lowest-cost Ollama setup path.
- `python3 -m cli.main use-case`: passed and included `provider-status` before `first-run-check`.
- `indiamarketagents provider-status`: passed and reported the same missing-provider state from the installed console script.
- `indiamarketagents use-case`: passed and included `provider-status` before `first-run-check`.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py::test_provider_status_reports_no_ready_provider tests/test_india_cli_report.py::test_provider_status_prefers_ready_ollama_for_low_cost tests/test_india_cli_report.py::test_use_case_guidance_names_best_workflow_and_commands -q`: 3 passed after the provider-status preflight update.
- `indiamarketagents provider-status`: passed and showed the local `.env` path/status while reporting the current missing-provider state.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main provider-status`: passed and reported `OLLAMA_BASE_URL is set` without echoing the endpoint value.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider ollama`: passed and printed the generated shallow `analyze` command without echoing the endpoint value.
- `indiamarketagents init-env`: passed and reported that the existing local `.env` was left unchanged.
- `indiamarketagents use-case`: passed and included `init-env` before `provider-status`.
- `python3 -m cli.main --help`: passed and listed `init-env`.
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
- `python3 -m cli.main workflow-status --ticker RELIANCE.NS --date 2026-06-05`: passed; saved report bundle is present and provider setup is the next unfinished step.
- `python3 -m cli.main report-status --ticker RELIANCE.NS --date 2026-06-05`: passed; all expected saved sample-report artifacts are present.
- `python3 -m cli.main provider-status`: passed; showed configured provider `openai` from `TRADINGAGENTS_LLM_PROVIDER` and reported `OPENAI_API_KEY` missing without printing secrets.
- `python3 -m cli.main workflow-status --ticker RELIANCE.NS --date 2026-06-05`: passed; provider row now includes configured provider `openai` and missing `OPENAI_API_KEY`.
- `python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05`: failed as expected; `Provider readiness` row now includes configured provider `openai` and missing `OPENAI_API_KEY`.
- `python3 -m pip install -e ".[dashboard]"`: passed; installed optional dashboard dependencies in the current Python 3.14 environment.
- `streamlit run dashboard/app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false`: passed and was stopped after browser verification.
- Browser verification at `http://localhost:8501`: passed; rendered `IndiaMarketAgents`, ticker `RELIANCE.NS`, date `2026-06-05`, saved-report tabs, research-only disclaimer, data-quality content, no browser console errors, and no broker/order action controls.
- `python3 -m cli.main doctor --ticker RELIANCE.NS`: passed; first-workflow readiness is false because no provider path is ready.
- `python3 -m cli.main analyze --ticker AAPL --date 2026-06-05 --no-display --no-save-prompt`: rejected `AAPL` as expected under India-only defaults.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py::test_usage_playbook_distinguishes_rehearsal_from_research_readiness -q`: 1 passed.
- `OLLAMA_BASE_URL=http://localhost:11434/v1 python3 -m cli.main first-run-check --ticker RELIANCE.NS --date 2026-06-05 --analysts india_market`: passed and printed the generated shallow `indiamarketagents analyze` command.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_india_cli_report.py -q`: 30 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/test_security_compliance.py::test_user_facing_docs_do_not_advertise_order_execution tests/test_security_compliance.py::test_no_tracked_generated_reports_filings_or_bytecode -q`: 2 passed.
- `gh pr view 1002 --repo TauricResearch/TradingAgents --json url,title,state,isDraft,baseRefName,headRefName,headRepositoryOwner,statusCheckRollup,updatedAt`: passed; PR is open, draft, and currently has no reported status checks.
- `git grep -n -I -E 'sk-[A-Za-z0-9_-]{8,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY' -- .` with `.env.example*` templates excluded: no matches.
- `git grep -n -I -E 'sent to the simulated exchange|KiteConnect|place_order'` with handoff, PR-readiness, and test assertion files excluded: no matches.
- `git ls-files | rg '(^reports/|^data/india/filings/|^data/india/manual/|\\.pdf$|__pycache__|\\.pyc$|\\.db$|\\.sqlite$|\\.log$)'`: no matches.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -m "not integration" -q`: 397 passed, 1 deselected, 7 warnings, 75 subtests passed.

## Remaining Risks

- NSE/BSE official-source modules are still defensive placeholders. They fail closed and need verified public-source workflows before live use.
- yfinance remains a third-party fallback, not an official source.
- README still retains the upstream TradingAgents body for attribution/background, but the first user-facing path now routes through the IndiaMarketAgents quick start and India docs.
- Streamlit remains optional and was installed in the current environment only to browser-verify the saved-report dashboard runtime.
- `reports/RELIANCE.NS/2026-06-05/` now exists locally as an ignored offline sample bundle; it is not tracked and contains no live market, broker, filing, or LLM output.
- No LLM provider is ready in this environment yet: local `.env` exists but `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, and `OLLAMA_BASE_URL` are empty; `ollama` is not on PATH.
- The internal Python package name remains `tradingagents` to avoid disruptive import churn.
- PR #1002 is still draft and currently has no GitHub status checks reported.
- PR body was updated from this file after the dashboard runtime verification update.

## PR Checklist

- [x] India-only default scope is enforced and tested.
- [x] Legacy/global behavior requires an explicit config escape hatch.
- [x] No broker execution or broker integration was added.
- [x] User-facing report/dashboard language is research-only.
- [x] Missing data paths return explicit unavailable/low-confidence messaging.
- [x] Saved report artifacts include compliance disclaimers and data-quality/source coverage.
- [x] Generated reports, local filings, PDFs, caches, and secrets are ignored and not tracked.
- [x] Offline unit tests pass without API keys or live exchange access.
- [x] Recommended first workflow and best-use-case guidance is documented.
- [x] Credential-safe first-run checklist is documented.
- [x] First-run preflight is available without live market, broker, or LLM calls.
- [x] Sample saved-report generation is available without live market, broker, or LLM calls.
- [x] Offline CLI commands avoid importing the full graph until analysis is requested.
- [x] Highest-value use case is available from the CLI.
- [x] Provider readiness status is available from the CLI without live calls or secret output.
- [x] Local env initialization is available from the CLI without overwriting existing `.env`.
- [x] First workflow status is available from the CLI without live calls.
- [x] Saved report status is available from the CLI without live calls or writes.
- [x] First-run checklist analyze example matches the provider-aware generated command.
- [x] Workflow status validates full saved-report bundle readiness.
- [x] First-run preflight auto-selects a ready provider when `--provider` is omitted.
- [x] Use-case guidance points to the generated provider-specific analyze command.
- [x] Doctor health check surfaces first-workflow readiness and next step.
- [x] Beginner setup uses the no-overwrite env init and generated analysis command flow.
- [x] First-run preflight reports provider readiness before users spend on analysis.
- [x] Root README routes new users to the IndiaMarketAgents quick start.
- [x] Usage playbook separates no-key rehearsal readiness from first LLM-backed research-run readiness.
- [x] Provider status shows the configured provider without printing secrets.
- [x] Workflow status surfaces the configured-provider blocker when no provider path is ready.
- [x] First-run check surfaces the configured-provider blocker when no provider path is ready.
- [x] Optional dashboard runtime was browser-verified after installing `.[dashboard]`.
- [ ] Official NSE/BSE data-source behavior should be implemented only after source/legal/access review.

## Suggested Reviewer Focus

- Confirm India ticker validation and report path safety behavior.
- Review compliance wording in README, README_INDIA, dashboard, CLI reports, and generated artifacts.
- Review unavailable-response and data-quality treatment in India dataflows.
- Review saved-report artifact readiness and `data_quality.json` summary behavior.
- Review that no live broker/order execution affordance exists.
- Review test coverage around India defaults, report artifacts, dashboard helpers, and security/compliance scans.
