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

1. **Single config builder**: `default_config.py` owns config resolution via `build_default_config(...)`.
2. **Explicit precedence**: hardcoded defaults -> `.env` values -> process environment.
3. **Deterministic test mode**: tests default to `TRADINGAGENTS_LOAD_DOTENV=0` so developer-local `.env` is not consumed implicitly.
4. **`_env()` / `_env_int()` helpers**: Read `TRADINGAGENTS_<KEY>` from a resolved environment snapshot. Return the hardcoded default when the env var is unset or empty.
5. **All config keys overridable**: `TRADINGAGENTS_` prefix + uppercase config key.

## Constraints

- `llm_provider` and `backend_url` must always exist at top level — `scanner_graph.py` and `trading_graph.py` use them as fallbacks.
- Empty or unset vars preserve the hardcoded default. `None`-default fields stay `None` when unset.

## Actionable Rules

- New config keys must follow the `TRADINGAGENTS_<UPPERCASE_KEY>` pattern.
- `.env` loading is centralized in `build_default_config(...)`; entrypoints must not call `load_dotenv()` directly.
- Always check actual env var values when debugging auth issues.
