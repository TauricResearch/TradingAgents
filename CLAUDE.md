# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

Install (editable):
```bash
pip install -e .
```

Run the interactive CLI (entry point `cli.main:app`, a Typer app):
```bash
tradingagents               # installed script
python -m cli.main          # equivalent
python main.py              # minimal Python-API example (NVDA)
```

Tests use pytest with custom markers (`unit`, `integration`, `smoke`) and `-ra --strict-markers`. `tests/conftest.py` autouses a fixture that injects placeholder values for every provider API key, so the suite runs offline:
```bash
pytest                                          # full suite
pytest tests/test_signal_processing.py          # single file
pytest tests/test_model_validation.py::test_x   # single test
pytest -m unit                                  # by marker
```

End-to-end provider smoke (calls a real LLM — costs money):
```bash
OPENAI_API_KEY=... python scripts/smoke_structured_output.py openai
```
This exercises only the three structured-output agents (Research Manager, Trader, Portfolio Manager) plus `SignalProcessor`. It does **not** call `propagate()` — keep it that way to bound cost.

Docker:
```bash
docker compose run --rm tradingagents
docker compose --profile ollama run --rm tradingagents-ollama
```

Checkpoint resume (opt-in; per-ticker SQLite under `~/.tradingagents/cache/checkpoints/`):
```bash
tradingagents analyze --checkpoint
tradingagents analyze --clear-checkpoints
```

Non-interactive analyze (skip the wizard; flags must accompany `--yes`/`-y`, otherwise they're ignored and the wizard runs):
```bash
tradingagents analyze -y \
  -t SPY -d 2026-05-08 -a market \
  --depth shallow -p mlx \
  -m mlx-community/Qwen3.5-9B-OptiQ-4bit
```
Required with `-y`: `--ticker`, `--date`, `--analysts`, `--depth`, `--provider`, and either `--model` (single) or both `--quick-model` + `--deep-model`. Defaults: `--depth shallow|medium|deep` → 1/3/5; `--analysts` accepts `market,social,news,fundamentals`. `--backend-url` falls back to the per-provider default from `cli/utils.DEFAULT_BACKEND_URL_BY_PROVIDER` when omitted. For `mlx`, `verify_mlx_server_reachable()` runs before the dashboard takes over so a missing server or `401` from oMLX produces a single-panel error instead of a LangGraph traceback.

MLX/oMLX provider notes. The `mlx` provider routes through `OpenAIClient` with `provider="mlx"` and a default base URL of `http://localhost:8000/v1`. Auth env var is `OMLX_API_KEY`; if unset we fall back to a placeholder bearer (`"local"`) so stock `mlx_lm.server` (no auth) keeps working. The CLI's "Custom MLX model ID" prompt autocompletes from the local HuggingFace cache (`HF_HUB_CACHE` or `HF_HOME` honoured).

## Architecture

TradingAgents is a LangGraph pipeline that orchestrates ~10 LLM-powered agents through a fixed workflow. The orchestration entry point is `TradingAgentsGraph.propagate(ticker, date)` in `tradingagents/graph/trading_graph.py`.

**Pipeline order** (built in `graph/setup.py`): selected analysts (market / social / news / fundamentals, in user-supplied order, each with its own ToolNode and a "Msg Clear" node) → Bull/Bear Researcher debate (looped via `ConditionalLogic.should_continue_debate` for `max_debate_rounds`) → Research Manager → Trader → Aggressive/Conservative/Neutral risk debate (looped for `max_risk_discuss_rounds`) → Portfolio Manager → END.

**Two LLMs, not one.** `quick_thinking_llm` runs analysts, researchers, trader, risk debators, and `SignalProcessor`/`Reflector`. `deep_thinking_llm` runs Research Manager and Portfolio Manager. Both are constructed via `tradingagents/llm_clients/factory.py::create_llm_client`, which lazily imports the provider client (so test collection doesn't pull in heavy SDKs). OpenAI-compatible providers (`openai`, `xai`, `deepseek`, `qwen`, `glm`, `ollama`, `openrouter`, `mlx`) all share `OpenAIClient` with a `provider=` discriminator; Anthropic, Google, and Azure have their own client classes.

**Provider-specific thinking knobs** flow through `_get_provider_kwargs`: `google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort`. `backend_url` defaults to `None` so each client uses its native endpoint — never re-introduce a hardcoded OpenAI URL as the default (it leaks into Gemini/etc. and produces malformed request URLs; see CHANGELOG 0.2.4).

**Structured-output agents.** Research Manager, Trader, and Portfolio Manager call `llm.with_structured_output(Schema)` and return typed Pydantic instances (schemas in `tradingagents/agents/schemas.py`); render helpers convert these back to the markdown shape the rest of the pipeline expects. `SignalProcessor` then extracts the rating from that rendered markdown via a deterministic heuristic — **no extra LLM call**. Don't add one.

**Rating scales are intentionally split**: 5-tier (Buy / Overweight / Hold / Underweight / Sell) for Research Manager, Portfolio Manager, signal processor, and the memory log; 3-tier (Buy / Hold / Sell) for the Trader (transaction direction is naturally ternary).

**Data vendors are pluggable per category.** `tradingagents/dataflows/interface.py` routes each tool through `config["data_vendors"]` (category default) and `config["tool_vendors"]` (per-tool override). Supported vendors are `yfinance` (default, no key needed) and `alpha_vantage` (needs `ALPHA_VANTAGE_API_KEY`). When adding a new tool, register it in the appropriate `TOOLS_CATEGORIES` bucket and wire both vendors.

**Tool date params are clamped to the as-of trade_date.** Tool wrappers (`tradingagents/agents/utils/{core_stock,fundamental_data,news_data,technical_indicators}_tools.py`) are bound once into static `ToolNode`s, so per-run date enforcement runs through a `ContextVar` set in `propagate()` (see `agents/utils/_date_clamp.py`). Any LLM-supplied date later than `trade_date` is capped to it before `route_to_vendor`, and a one-line "Note: …" prefix tells the agent the window was shortened. Tools without a date param (e.g. `get_insider_transactions`) read the contextvar themselves and pass `as_of=` to the vendor for downstream filtering. **When adding a new tool that takes any date, run every LLM-supplied date through `clamp(...)` and prepend `maybe_note(...)` to the result** — otherwise analysts can read post-trade-date data and silently look-ahead-bias the report.

**Persistence** lives at `~/.tradingagents/` (override base via `TRADINGAGENTS_CACHE_DIR`, results via `TRADINGAGENTS_RESULTS_DIR`, memory via `TRADINGAGENTS_MEMORY_LOG_PATH`):
- `memory/trading_memory.md` — always-on persistent decision log managed by `TradingMemoryLog` (`agents/utils/memory.py`). Each `propagate()` appends a pending entry; the next same-ticker run calls `_resolve_pending_entries`, which fetches realised return + alpha vs SPY via yfinance, generates a one-paragraph reflection through `Reflector`, and batches the updates atomically. Only same-ticker entries resolve per run — cross-ticker entries accumulate. The Portfolio Manager prompt is the **only** consumer of memory context (via `get_past_context`); never feed it to other agents.
- `cache/checkpoints/<TICKER>.db` — opt-in LangGraph SqliteSaver. `propagate()` recompiles the graph with the saver, uses `thread_id(ticker, date)` so same ticker+date resumes and a different date starts fresh, and clears the checkpoint on successful completion.
- `logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json` — full final state. Ticker is sanitised through `safe_ticker_component` to prevent path escape.

**File I/O must pass `encoding="utf-8"` explicitly** — Windows users on cp1252 hit `UnicodeEncodeError` otherwise (regression history; CHANGELOG 0.2.4).

## CLI

The CLI (`cli/main.py`) is a single Typer app that wraps `TradingAgentsGraph` with a `rich`-based live dashboard. `MessageBuffer` is the central state holder for the UI: it tracks `agent_status`, `report_sections`, and a deque of recent messages/tool calls; `init_for_analysis(selected_analysts)` rebuilds it dynamically from the user's analyst selection so non-selected analysts don't appear in the progress table. `StatsCallbackHandler` (`cli/stats_handler.py`) is passed to LLMs as a LangChain callback and accumulates token/tool stats for the footer.

## Tests

`tests/conftest.py` makes the suite hermetic: dummy API keys for every provider, plus a `mock_llm_client` fixture that patches `factory.create_llm_client`. New tests that exercise the graph or any agent should use this fixture rather than instantiating real clients.
