---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [config, env-vars, dotenv]
related_files: [tradingagents/default_config.py, .env.example, pyproject.toml]
---

## Context

`DEFAULT_CONFIG` hardcoded all values. Users had to edit `default_config.py` to change any setting. The `load_dotenv()` call in `cli/main.py` ran *after* `DEFAULT_CONFIG` was already evaluated at import time, so env vars had no effect.

## The Decision

1. **Module-level `.env` loading**: `default_config.py` calls `load_dotenv()` at the top of the module, before `DEFAULT_CONFIG` is evaluated.
2. **`_env()` / `_env_int()` helpers**: Read `TRADINGAGENTS_<KEY>` from environment. Return the hardcoded default when the env var is unset or empty.
3. **Restored top-level keys**: `llm_provider` (default: `"openai"`) and `backend_url` (default: `"https://api.openai.com/v1"`) restored as env-overridable keys.
4. **All config keys overridable**: `TRADINGAGENTS_` prefix + uppercase config key.
5. **Explicit dependency**: Added `python-dotenv>=1.0.0` to `pyproject.toml`.

## Constraints

- `llm_provider` and `backend_url` must always exist at top level — `scanner_graph.py` and `trading_graph.py` use them as fallbacks.
- Empty or unset vars preserve the hardcoded default. `None`-default fields stay `None` when unset.

## Actionable Rules

- New config keys must follow the `TRADINGAGENTS_<UPPERCASE_KEY>` pattern.
- `load_dotenv()` runs at module level in `default_config.py` — import-order-independent.
- Always check actual env var values when debugging auth issues.
