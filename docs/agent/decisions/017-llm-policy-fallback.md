# ADR 017: Per-Tier LLM Fallback for Provider Policy Errors

**Date**: 2026-03-25
**Status**: Implemented (PR#108)

## Context

OpenRouter and similar providers return HTTP 404 when a model is blocked by
account-level guardrail or data policy restrictions:

```
Error code: 404 - No endpoints available matching your guardrail
restrictions and data policy.
```

This caused all per-ticker pipelines to crash with a 100-line stack trace,
even though the root cause is a configuration/policy issue — not a code bug.

## Decision

Add per-tier fallback LLM support with these design choices:

**1. Detection at `chain.invoke()` level (`tool_runner.py`)**
Catch `getattr(exc, "status_code", None) == 404` and re-raise as `RuntimeError`
with the OpenRouter settings URL and fallback env var hints. No direct `openai`
import — works with any OpenAI-compatible client.

**2. Re-raise with context in `run_pipeline` (`langgraph_engine.py`)**
Wrap `astream_events` to catch policy errors and re-raise with model name,
provider, and config guidance. Separates detection from retry logic.

**3. Per-tier retry in `_run_one_ticker`**
Distinguish policy errors (config issue → `logger.error`, no traceback) from
real bugs (`logger.exception` with full traceback). If per-tier fallback models
are configured, rebuild the pipeline config and retry via `_build_fallback_config`.

**4. Per-tier config following existing naming convention**
```
quick/mid/deep_think_fallback_llm
quick/mid/deep_think_fallback_llm_provider
```
Overridable via `TRADINGAGENTS_QUICK/MID/DEEP_THINK_FALLBACK_LLM[_PROVIDER]`.
No-op when unset — backwards compatible.

## Helpers Added

```python
# agent_os/backend/services/langgraph_engine.py
def _is_policy_error(exc: Exception) -> bool: ...
def _build_fallback_config(config: dict) -> dict | None: ...
```

## Rationale

- **Per-tier not global**: Different tiers may use different providers with
  different policies. Quick-think agents on free-tier may hit restrictions
  while deep-think agents on paid plans are fine.
- **`self.config` swap pattern**: Reuses `run_pipeline` by temporarily swapping
  `self.config` inside the semaphore-protected `_run_one_ticker` async slot.
  Thread-safe; `finally` always restores original config.
- **No direct `openai` import**: Detection via `getattr(exc, "status_code")`
  works with any OpenAI-compatible client (OpenRouter, xAI, Ollama, etc.).

## Consequences

- 404 policy errors no longer print 100-line tracebacks in logs
- Operators can add fallback models in `.env` without code changes
- New config keys documented in `CLAUDE.md` and `.env.example`
