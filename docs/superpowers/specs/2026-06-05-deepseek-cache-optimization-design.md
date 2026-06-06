# DeepSeek Cache Optimization Design

Date: 2026-06-05
Status: Draft for user review
Scope: TradingAgents investment-team prompts and DeepSeek official API usage only

## Summary

The TradingAgents investment team currently gets limited DeepSeek context-cache benefit because several expensive LLM calls do not preserve a byte-stable prompt prefix. The main issue is not that DeepSeek caching is disabled; DeepSeek official API context caching is automatic. The issue is prompt shape: ticker, date, asset-type wording, fetched market/news/social data, prior memory, and debate history often appear before or inside long instruction blocks, causing repeated calls to diverge early.

This design keeps the current graph architecture and agent roles intact, but makes the LLM request shape cache-first:

1. Static system instructions first.
2. Tool definitions and schemas in deterministic order.
3. Fixed background instructions and output contracts.
4. Dynamic run data only at the user-tail.
5. Existing conversation/tool history only after static prefix content.

The implementation will focus on DeepSeek official API behavior: automatic overlapping-prefix caching and the existing `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` usage telemetry. Gateway-only controls such as `prompt_cache_key` and `X-Session-ID` are explicitly out of scope for this first pass.

## Sources

- DeepSeek Context Caching docs: https://api-docs.deepseek.com/guides/kv_cache
- DeepSeek Chat Completion usage fields: https://api-docs.deepseek.com/api/create-chat-completion/
- OpenAI prompt-caching docs, used only as general prompt-structure guidance: https://developers.openai.com/api/docs/guides/prompt-caching

## Current Architecture

The main graph lives in `tradingagents/graph/setup.py` and runs:

1. Market analyst with tool loop.
2. Sentiment analyst.
3. News analyst with tool loop.
4. Fundamentals analyst with tool loop.
5. Derivatives analyst with tool loop.
6. Bull and bear investment debate.
7. Research manager.
8. Trader.
9. Aggressive, conservative, and neutral risk debate.
10. Portfolio manager final synthesis.
11. Run recorder.

DeepSeek clients are created in `tradingagents/graph/trading_graph.py` through `tradingagents/llm_clients/openai_client.py`. The code already captures DeepSeek cache usage in `tradingagents/graph/cost_callback.py` and persists it in `costs.cache_hit_tokens` and `costs.cache_miss_tokens` through `tradingagents/graph/run_recorder.py` and `tradingagents/persistence/store.py`.

The current architecture therefore has a useful measurement base, but the prompt layer is uneven:

- Analyst tool-loop prompts use `ChatPromptTemplate`, but date and instrument context are sometimes mixed near the front of the message sequence.
- `sentiment_analyst.py` builds a large dynamic prompt containing ticker, date range, news, StockTwits, and Reddit blocks. This sacrifices cache reuse on one of the largest non-tool prompts.
- `derivative_analyst.py` places date and instrument context in the system message template rather than a separate user-tail message.
- Bull, bear, risk, manager, trader, and portfolio prompts mostly use system plus user messages, but some system prompts vary by asset type or persona and dynamic tails are not consistently ordered.
- Report and debate history growth increases miss-token volume even after prefix fixes.

## Goals

1. Improve DeepSeek cache-hit ratio for repeated TradingAgents runs that share the same agent/persona/model configuration.
2. Reduce prompt-cache miss tokens by moving dynamic data to the tail and bounding dynamic context.
3. Preserve current graph order, agent responsibilities, output fields, structured-output behavior, and persisted artifacts.
4. Add tests that catch prompt-prefix regressions before they reach production.
5. Make cache-hit ratio visible enough to validate whether the redesign worked.
6. Add a release warm-up script for representative DeepSeek official API requests.

## Non-Goals

- Do not implement `prompt_cache_key`, `X-Session-ID`, sticky routing headers, or gateway-specific request controls.
- Do not add semantic answer caching to the core investment decision pipeline. Market decisions are date-, data-, and ticker-sensitive, so direct answer reuse is too risky here.
- Do not change the LangGraph node order or remove analyst roles.
- Do not change the DeepSeek reasoning-content roundtrip behavior.
- Do not introduce a new external vector database.

## Design Decisions

### D1: Static Prompt Constants

Each investment-team agent gets module-level static prompt constants for its role, instructions, and output contract. These constants must not include ticker, trade date, fetched data, debate history, prior analysis packs, or memory lessons.

For tool-loop agents, the static system message should remain the first message. Tool definitions are provided by LangChain via `bind_tools`; tool lists must keep deterministic order.

For structured agents, the schema binding remains unchanged, but the user-visible prompt still follows static system first, dynamic user tail second.

### D2: Dynamic Tail Builder

Add `tradingagents/agents/utils/prompt_cache.py` with small helpers:

- `stable_join_sections(sections)`: joins named sections in deterministic order, skipping empty values without changing the order of present sections.
- `build_dynamic_context(...)`: renders ticker, asset type, trade date, reports, debate history, prior packs, and memory lessons only in user-tail content.
- `trim_context_block(text, max_chars, label)`: trims dynamic blocks deterministically from the middle or oldest side, with an explicit truncation marker.
- `prompt_prefix_fingerprint(messages, dynamic_start_marker)`: returns a stable hash of the static prefix for tests.

The helpers should be intentionally boring. They should not hide agent-specific semantics; they only standardize section ordering, tail placement, and deterministic trimming.

### D3: Prompt Layout

All investment-team calls should use this shape:

```text
system:
  <static role instructions>
  <static output contract>
  <static persona fragment if configured>

user:
  <dynamic marker>
  trade_date
  instrument_context
  event_context
  market_snapshot
  analyst reports
  debate history
  prior analysis pack
  memory lessons
  current task

messages/tool history:
  existing LangGraph MessagesPlaceholder or assistant/tool messages
```

The persona fragment remains in the system prefix because persona-specific runs are separate cache families. The fragment must be deterministic for a given persona file. If committee mode runs multiple personas, each persona should have its own stable prefix rather than sharing a prefix across personas.

Asset-type differences should move out of system prompts when possible. Instead of interpolating "stock" or "asset" in role instructions, static prompts should use neutral terms such as "instrument" and place stock/crypto caveats in the user-tail instrument context.

### D4: Sentiment Analyst Restructure

`sentiment_analyst.py` is the highest-priority prompt fix.

Current behavior:

- Fetches news, StockTwits, and Reddit before the LLM call.
- Builds a large prompt body with ticker, date range, and all fetched source text.
- Places that generated body near the beginning of the request.

New behavior:

- Keep a static sentiment-analysis system prompt with data-source methodology and output contract.
- Put the ticker, date range, news block, StockTwits block, and Reddit block in a deterministic user-tail section.
- Keep the single-call no-tool design, because avoiding tool loops is still valuable. The optimization is placement, not reintroducing tools.

### D5: Derivatives and Analyst Tool Prompts

`derivative_analyst.py` should move `current_date` and `instrument_context` out of the system message and into the human message, matching the other tool-loop analysts.

Market, news, and fundamentals prompts should keep static instructions in system messages and dynamic context in human messages. Any imported `get_config` that is unused can be removed during implementation, but that is incidental cleanup.

### D6: Debate and Synthesis Prompts

Bull, bear, aggressive, conservative, neutral, research manager, trader, and portfolio manager prompts should:

- Use static system constants.
- Use neutral "instrument" language in system instructions.
- Put all reports, history, last response, prior packs, and memory lessons in deterministic user-tail sections.
- Preserve existing output renderers and structured-output schemas.

Debate history is dynamic by nature. The goal is not to cache it; the goal is to keep it from appearing before reusable instructions and to cap its growth.

### D7: Dynamic Context Budgets

Add config defaults:

- `prompt_cache_dynamic_budget_chars`: default 24000.
- `prompt_cache_report_budget_chars`: default 5000 per report.
- `prompt_cache_debate_budget_chars`: default 8000 per debate history.
- `prompt_cache_prior_pack_budget_chars`: default 8000.
- `prompt_cache_memory_budget_chars`: default 6000.

Budgets should trim only dynamic tail content. Static prompts must never be trimmed. Truncation markers must be stable, for example:

```text
[truncated: kept most recent 8000 chars]
```

This reduces miss tokens without changing the beginning of the prompt.

### D8: Warm-Up Script

Add `scripts/warm_deepseek_prompt_cache.py`.

The script should:

- Use the configured DeepSeek quick and deep models.
- Build representative prompts for major investment-team agent families.
- Send tiny deterministic dynamic tails, for example ticker `CACHE-WARMUP`, trade date `2000-01-01`, and empty report placeholders.
- Log model, prompt tokens, cache-hit tokens, cache-miss tokens, and cache-hit ratio from the API response.
- Support `--dry-run` to print planned warm-up families without making API calls.

The script should not depend on gateway routing. It only relies on DeepSeek official API automatic context caching.

### D9: Measurement and Reporting

Keep the current token capture path. Extend visibility:

- Add `cache_hit_tokens`, `cache_miss_tokens`, and `cache_hit_ratio` to `dashboard/panels/costs.py`.
- Add unit tests for daily/model aggregation.
- Optionally add a CLI summary later if dashboard visibility is not enough.

Success should be measured by:

- Per-model cache-hit ratio over the last N days.
- Prompt-cache miss tokens per completed run.
- Total USD estimate per run.
- Completion success rate, to ensure trimming did not break output quality.

### D10: Prefix Regression Tests

Add tests that inspect constructed prompts without calling the network:

- Same agent, same persona, different ticker/date should produce identical static-prefix fingerprints.
- Sentiment analyst with different fetched blocks should produce identical static-prefix fingerprints.
- Derivatives analyst system message should not contain date or ticker.
- Dynamic sections should appear after a marker such as `## Dynamic Run Context`.
- Tool names should remain in deterministic order.

These tests should be unit tests using mocked LLMs or prompt builders. They should not require `DEEPSEEK_API_KEY`.

## Implementation Boundaries

The first implementation plan should edit only:

- `tradingagents/agents/utils/prompt_cache.py` or equivalent new helper.
- Investment-team agent modules under `tradingagents/agents/analysts/`, `researchers/`, `risk_mgmt/`, `managers/`, and `trader/`.
- `tradingagents/default_config.py` for budget defaults.
- `tradingagents/dashboard/panels/costs.py` and tests for cache-ratio reporting.
- `scripts/warm_deepseek_prompt_cache.py`.
- Unit tests for prompt determinism and budget behavior.

Avoid unrelated refactors, model catalog changes, persistence schema changes, or semantic caching in this pass.

## Risks and Mitigations

### R1: Trimming Removes Material Evidence

Mitigation: make budgets conservative, trim oldest debate/history first, keep truncation markers visible, and preserve complete source artifacts on disk.

### R2: Prompt Refactor Changes Agent Behavior

Mitigation: preserve role instructions and output contracts verbatim where possible; test existing structured-agent outputs; run existing unit tests for structured agents, memory log injection, and graph cache telemetry.

### R3: Persona Fragment Still Splits Cache Families

Mitigation: accept this as correct behavior. Persona differences intentionally change the system prefix. Cache comparisons should be grouped by model and persona.

### R4: Warm-Up Costs Money

Mitigation: provide `--dry-run`, keep dynamic tails tiny, and document that warm-up is optional before release or after instance/model churn.

### R5: DeepSeek Cache Behavior Can Still Miss

Mitigation: the official API controls cache matching automatically. The app can maximize overlap but cannot force backend routing. Measurement must remain the source of truth.

## Acceptance Criteria

1. Prompt determinism tests pass for changed agents.
2. Existing structured-output and memory-log tests continue to pass.
3. `pytest tests/graph/test_cache_token_capture.py tests/graph/test_cache_ratio_metrics.py` passes.
4. Costs panel aggregation includes cache-hit ratio when cache fields exist.
5. Warm-up script has dry-run coverage and does not require network in unit tests.
6. No DeepSeek official API request includes unsupported gateway-only cache parameters.

## Open Questions

None for the first implementation pass. The user has selected DeepSeek official API only, so gateway routing controls are intentionally deferred.
