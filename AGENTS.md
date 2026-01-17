# Repository Guidelines

## Project Structure & Module Organization
Core package lives under `tradingagents/` with agent roles in `tradingagents/agents`, data acquisition in `tradingagents/dataflows`, and LangGraph orchestration in `tradingagents/graph`. CLI entry points sit in `cli/`; run `python -m cli.main` for the interactive workflow, and see `main.py` for a scripted example. Reference material (images, CLI captures) belongs in `assets/`, while experiment output should land in `results/`. Avoid committing local virtual environments—`tradingagents/python=3.13/` is legacy and should stay untracked. Update shared configs through `tradingagents/default_config.py` and keep per-developer overrides outside the repo.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and activate a clean Python ≥3.10 environment.
- `pip install -r requirements.txt && pip install -e .`: install runtime dependencies and link the package for local development.
- `python -m cli.main`: launch the console UI to step through ticker selection and agent runs.
- `python main.py`: execute a minimal graph run using `DEFAULT_CONFIG` for smoke-testing pipeline changes.

## Coding Style & Naming Conventions
Follow standard PEP 8: 4-space indentation, lowercase `snake_case` functions, and `CamelCase` classes. Preserve typing hints where present (`Dict[str, Any]` patterns are common) and keep docstrings focused on side effects and arguments. Prefer module-level constants for configuration keys rather than magic strings scattered across functions.

## Testing Guidelines
`test.py` currently exercises the Yahoo Finance dataflow; extend it or add new scripts under `tests/` when introducing features, keeping names aligned with the module under test (`test_<module>.py`). When you add high-impact functionality, capture CLI or graph outputs in the PR description and include deterministic test cases where possible.

## Commit & Pull Request Guidelines
Recent history uses short, present-tense summaries (“Latest changes applied”, “utf8 encoding fixed…”). Mirror that tone, lead with the primary change, and keep messages under ~70 characters when feasible. PRs should include a concise summary, configuration considerations, and before/after evidence (logs, screenshots) plus linked issue IDs where applicable.

## Security & Configuration Tips
Load API keys through the environment (`FINNHUB_API_KEY`, `OPENAI_API_KEY`) and never hard-code real secrets; scrub `DEFAULT_CONFIG` before publishing. Regenerate cached data under `tradingagents/dataflows/data_cache` rather than checking large blobs into git. If you script new agents, document required permissions and expected rate limits in the PR to help reviewers assess operational impact.
