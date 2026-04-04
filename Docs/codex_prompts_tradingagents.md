# Codex 작업 프롬프트 모음

## 프롬프트 1 — 구현 메인 프롬프트

You are working inside the local TradingAgents repository.

Goal:
Implement a new LLM provider named `codex` so TradingAgents can use the local Codex CLI/app-server authenticated with ChatGPT/Codex login instead of an OpenAI API key.

High-level constraints:
1. Do NOT build an OpenAI-compatible HTTP proxy.
2. Do NOT call raw OAuth endpoints yourself.
3. Do NOT depend on Codex dynamicTools for TradingAgents tool execution.
4. Keep TradingAgents’ existing LangGraph / ToolNode flow intact.
5. The integration must work for both:
   - analyst nodes that use `prompt | llm.bind_tools(tools)`
   - non-tool nodes that call `llm.invoke(...)` directly
6. Prefer minimal, coherent changes over broad refactors.
7. Add tests and documentation.
8. No unrelated cleanup.

Architecture to implement:
- Add a new provider `codex` in `tradingagents/llm_clients/factory.py`.
- Add a `CodexClient` implementing the existing BaseLLMClient contract.
- Add a custom LangChain chat model that talks to `codex app-server` over stdio JSONL.
- Reuse a long-lived app-server process per model instance, but create a fresh Codex thread per model invocation to avoid context bleed across agents.
- After each invocation, `thread/unsubscribe`.
- Use `initialize` / `initialized` on startup.
- Add a preflight helper that checks:
  - `codex` binary exists
  - app-server starts
  - `account/read` succeeds
  - requested models are available from `model/list`
- Do not require API keys for the `codex` provider.

Authentication assumptions:
- The supported user path is `codex login` or `codex login --device-auth`.
- If file-backed auth is used, Codex-managed credentials may be stored in `~/.codex/auth.json`.
- Do not implement direct OAuth token refresh.
- If auth is missing, fail with a clear actionable message telling the user to run `codex login`.

Important implementation choice:
Do NOT use app-server dynamic tools.
Instead, emulate tool calling at the model boundary with strict structured output:
- For plain non-tool calls, request JSON schema: `{ "answer": string }`
- For tool-capable calls, request a root `oneOf` schema:
  - final:
    `{ "mode": "final", "content": string, "tool_calls": [] }`
  - tool batch:
    `{ "mode": "tool_calls", "content": string, "tool_calls": [ ... ] }`
- For `tool_calls[].items`, use `oneOf` with one branch per tool so each tool name has its own exact arguments JSON schema.
- This is required so TradingAgents’ ToolNode can execute the selected tool calls after receiving an `AIMessage.tool_calls`.

Files to add:
- `tradingagents/llm_clients/codex_client.py`
- `tradingagents/llm_clients/codex_chat_model.py`
- `tradingagents/llm_clients/codex_app_server.py`
- `tradingagents/llm_clients/codex_schema.py`
- `tradingagents/llm_clients/codex_message_codec.py`
- `tradingagents/llm_clients/codex_preflight.py`

Files to modify:
- `tradingagents/llm_clients/factory.py`
- `tradingagents/default_config.py`
- `tradingagents/llm_clients/__init__.py`
- CLI / UI config surfaces if present
- README and/or docs

Model behavior requirements:
- Normalize input from:
  - `str`
  - LangChain `BaseMessage` sequences
  - OpenAI-style dict message sequences
- The custom model must support `bind_tools()`.
- `bind_tools()` should preserve LangChain semantics by binding tool schemas into `_generate(...)`.
- Return `AIMessage` objects.
- If tool calls are requested, populate `AIMessage.tool_calls` with stable ids like `call_<uuid>`.

Safety / hardening requirements:
- Default to a neutral dedicated workspace directory for Codex, not the repo root.
- Add config knobs for:
  - `codex_binary`
  - `codex_reasoning_effort`
  - `codex_summary`
  - `codex_personality`
  - `codex_workspace_dir`
  - `codex_request_timeout`
  - `codex_max_retries`
  - `codex_cleanup_threads`
- Document a recommended `.codex/config.toml` with:
  - `approval_policy = "never"`
  - `sandbox_mode = "read-only"`
  - `web_search = "disabled"`
  - `personality = "none"`
  - `cli_auth_credentials_store = "file"`

Testing requirements:
1. Unit tests for message normalization.
2. Unit tests for output schema construction.
3. Unit tests for plain final response parsing.
4. Unit tests for tool-call response parsing.
5. Unit tests for malformed JSON retry / error reporting.
6. Integration smoke test for provider `codex`.
7. Preflight test for missing auth / missing binary.

Acceptance criteria:
- `llm_provider="codex"` works without API keys after `codex login`.
- At least one analyst node using `bind_tools()` works.
- At least one non-tool node using `llm.invoke(...)` works.
- A minimal smoke run can produce a final report / final decision.
- Documentation explains installation, auth, usage, and limitations.

Implementation style:
- Read the existing code first and align with project style.
- Make the smallest set of clean, composable changes.
- Include comments only where they add real value.
- Avoid speculative abstractions.
- Keep the code production-oriented and debuggable.

Working method:
1. Inspect the current LLM client factory and how agents call `bind_tools()` vs `invoke()`.
2. Implement the connection layer.
3. Implement the chat model.
4. Wire the provider.
5. Add preflight + docs.
6. Add tests.
7. Run the relevant tests / smoke checks.
8. Summarize exactly what changed and any limitations that remain.

Do the work now.

---

## 프롬프트 2 — 검증/수정 프롬프트

Review the `codex` provider implementation you just added to TradingAgents.

Your job:
1. Find correctness bugs, interface mismatches, race conditions, and integration gaps.
2. Pay special attention to:
   - LangChain `bind_tools()` semantics
   - `AIMessage.tool_calls` structure
   - support for `llm.invoke(str)`, `llm.invoke(list[BaseMessage])`, and `llm.invoke(list[dict])`
   - app-server request/response matching
   - thread cleanup with `thread/unsubscribe`
   - malformed JSON retries
   - missing auth / missing binary / missing model diagnostics
3. Run or update tests as needed.
4. Fix only what is necessary; do not refactor unrelated code.
5. Update docs if behavior changed.

Definition of done:
- the provider is internally consistent,
- tests pass,
- smoke run works,
- error messages are actionable,
- no obvious context-bleed or tool-calling contract issues remain.

Return:
- a concise changelog,
- exact files modified,
- exact commands/tests run,
- any remaining known limitations.