# ADR 017: Per-Tier LLM Fallback for Provider Policy and Temporary Rate-Limit Errors

**Date**: 2026-03-25
**Status**: Implemented (PR#108, amended 2026-04-02)

## Context

OpenRouter and similar providers return HTTP 404 when a model is blocked by
account-level guardrail or data policy restrictions:

```
Error code: 404 - No endpoints available matching your guardrail
restrictions and data policy.
```

This caused all per-ticker pipelines to crash with a 100-line stack trace,
even though the root cause is a configuration/policy issue — not a code bug.

A second production issue appeared later: OpenAI-compatible providers could also
return temporary upstream `429` rate limits or hang long enough that a node
looked stuck. That needed a bounded timeout and a clearer fallback policy.

## Decision

Add per-tier fallback LLM support with these design choices:

**1. Detection at `chain.invoke()` level (`tool_runner.py`)**
Catch `getattr(exc, "status_code", None) == 404` and re-raise as `RuntimeError`
with the OpenRouter settings URL and fallback env var hints. No direct `openai`
import — works with any OpenAI-compatible client.

**2. Re-raise with context in `run_pipeline` (`langgraph_engine.py`)**
Wrap `astream_events` to catch policy errors and re-raise with model name,
provider, and config guidance. Separates detection from retry logic.

**3. Two-layer retry policy**
- Client-level retry (`openai_client.py`) handles transient same-model retries.
  This is for short-lived upstream/provider failures where the current model may
  succeed on another attempt.
- Engine-level fallback (`langgraph_engine.py`) handles model substitution.
  This is for provider policy failures and temporary upstream `429` conditions
  where retrying a different configured model is more likely to succeed.

The intent is escalation, not duplication:
- first, retry the same model a small number of times at the client layer
- then, if the error remains fallback-eligible, retry once with per-tier
  fallback models at the engine layer

**4. Per-tier retry in scan/pipeline execution**
Fallback is now used not only for policy/404 errors but also for temporary
rate-limit errors. The same per-tier substitution logic is applied in:
- Phase 1 scan retry in `run_auto`
- Phase 2 per-ticker deep-dive retry

**5. Per-tier timeout following existing naming convention**
```
llm_timeout
quick/mid/deep_think_llm_timeout
```
This caps hanging provider calls so a node fails explicitly instead of waiting
forever.

**6. Per-tier config following existing naming convention**
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
def _is_rate_limit_error(exc: Exception) -> bool: ...
def _is_fallback_eligible_error(exc: Exception) -> bool: ...
def _build_fallback_config(config: dict) -> dict | None: ...
def _fallback_model_summary(current_config: dict, fallback_config: dict) -> str: ...
```

## Rationale

- **Per-tier not global**: Different tiers may use different providers with
  different policies. Quick-think agents on free-tier may hit restrictions
  while deep-think agents on paid plans are fine.
- **Bounded runtime**: timeout defaults prevent “hung node” failures where the
  UI appears stuck but the provider never returns.
- **`self.config` swap pattern**: Reuses `run_pipeline` by temporarily swapping
  `self.config` inside the semaphore-protected `_run_one_ticker` async slot.
  Thread-safe; `finally` always restores original config.
- **No direct `openai` import**: Detection via `getattr(exc, "status_code")`
  works with any OpenAI-compatible client (OpenRouter, xAI, Ollama, etc.).

## Consequences

- 404 policy errors and temporary `429` upstream limits can now trigger
  per-tier fallback instead of killing the run immediately
- Hanging provider calls fail within the configured timeout instead of blocking a
  run indefinitely
- Operators can add fallback models and timeout overrides in `.env` without
  code changes
