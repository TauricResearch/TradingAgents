# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Requires Python >= 3.10 (CI runs 3.10–3.13).

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"          # add ".[dev,bedrock]" to run the Bedrock tests

pytest -q                           # full suite, ~5s, no network
pytest tests/test_vendor_routing.py                 # one file
pytest tests/test_backtest.py::test_name            # one test
pytest -k lookahead                                 # by keyword
ruff check .                        # lint; CI runs this on the whole repo and it must stay clean

tradingagents                       # interactive CLI (same as: python -m cli.main)
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
python main.py                      # programmatic example: propagate("NVDA", ...)
```

Do not run `ruff format` across the repo. Adopting the formatter is deliberately on hold until the backlog of open PRs clears. E501 is ignored.

CI also installs the package without dev extras and imports `tradingagents` and `cli.main`. Runtime imports must therefore be declared in `pyproject.toml` `dependencies`, not only in `dev`.

## Test harness behavior (tests/conftest.py)

- **No network.** An autouse fixture makes `socket.connect` raise. A test that really needs the network must be marked `@pytest.mark.integration`. Mock vendors instead of reaching them.
- **`TRADINGAGENTS_*` variables are blanked** before the package is imported. Your own `.env` therefore can't change the defaults the tests assert on.
- **Provider API keys are set to `"placeholder"`.**
- **The global dataflows config is reset around every test.**
- **CI runs one job with `TZ=America/New_York`.** Date logic must not assume UTC.

Some tests are structural and parse source code with `ast`. They fail if you break an invariant rather than behavior:
- `test_layering.py`: only `tradingagents/dataflows/` may import `yfinance`.
- `test_i18n_coverage.py`: every report-producing agent must call `get_language_instruction()`. Its `REPORT_AGENTS` list must include any new one.
- `test_prompt_integrity.py`: analyst `system_message` values must be strings, not tuples.

## Architecture

LangGraph multi-agent pipeline. The input is a ticker and date. The output is a five-tier rating (`Buy/Overweight/Hold/Underweight/Sell`), or `REVIEW` when no rating can be parsed.

### Run lifecycle (`tradingagents/graph/trading_graph.py`)

`TradingAgentsGraph.propagate()` runs these steps in order:

1. `create_run_state()`:
   - settles this ticker's pending past decisions;
   - injects past-decision lessons, instrument identity and portfolio context into the initial state.
2. Invokes the graph.
3. `_log_state()`, then `record_decision()` (appends to the decision log).
4. `process_signal()` → `parse_rating()`.

**The CLI (`cli/run.py`) does not call `propagate()`.** It streams the graph itself, calling the same public steps (`create_run_state`, `begin_checkpoint` / `checkpoint_input` / `end_checkpoint`, `record_decision`, `clear_checkpoint_on_success`). A change to the run flow must go into those shared methods, or the CLI and the Python API will diverge.

### Graph topology (`graph/setup.py`, `graph/conditional_logic.py`, `graph/analyst_execution.py`)

- **Analysts** run sequentially, in the order selected. The keys are `market`, `social`, `news`, `fundamentals`.
  - Each analyst is an agent node, a `ToolNode` loop, and a "Msg Clear" node that wipes `messages` before the next analyst.
  - Specs live in `ANALYST_NODE_SPECS`. Each analyst module exports a `TOOLS` tuple that is used both for `bind_tools` and for its tool node.
  - The Sentiment analyst (`social`) has **no tools**. It pre-fetches news, StockTwits and Reddit, and puts them into the prompt.
- **Research debate:** Bull and Bear alternate until `count >= 2 * max_debate_rounds`. Then the Research Manager writes the investment plan.
- **Trader.**
- **Risk debate:** Aggressive → Conservative → Neutral, until `count >= 3 * max_risk_discuss_rounds`. Then the Portfolio Manager writes `final_trade_decision`.
- The routers choose the next speaker by **string prefix** (`current_response.startswith("Bull")`, `latest_speaker.startswith("Aggressive")`). Keep the speaker labels agents write (e.g. `"Bull Analyst: ..."`) in sync with these checks.
- Every conditional edge maps every possible router target (`DEBATE_PATH_MAP`, `RISK_ANALYSIS_PATH_MAP`), so a fall-through can't crash LangGraph.
- Only the Research Manager and Portfolio Manager use `deep_think_llm`. Every other agent, and the Reflector, uses `quick_think_llm`.
- Internal debate stays in English. Only report-producing agents apply `output_language`.

### Structured output (`agents/structured.py`, `agents/schemas.py`)

- The Research Manager, Trader, Portfolio Manager and Sentiment analyst use `bind_structured()` + `invoke_structured_or_freetext()`.
- The Pydantic schema is rendered back to markdown by a `render_*` function, so state, reports and the decision log always hold markdown.
- If the structured call fails for any reason, it falls back once to plain free text.
- `agents/rating.py` is the single parser for the rating vocabulary. Unparseable output becomes `REVIEW`; it is never coerced to Hold.

### Configuration: two layers

- `default_config.py`
  - Builds `DEFAULT_CONFIG` **at import time** and applies the `_ENV_OVERRIDES` table. Env strings are coerced to the type of the default, and invalid values raise.
  - To expose a new key via env, add a row to that table.
  - `.env` and `.env.enterprise` are loaded in `tradingagents/__init__.py` on import.
- `dataflows/config.py` has two scopes:
  - a process-wide config (`set_config`);
  - a per-run `ContextVar` (`run_config(...)`, entered by `propagate`), so several graphs in one process each read their own vendors.
  - Code in the data layer must read settings through `get_config()`, never from `DEFAULT_CONFIG` directly.

### Data layer (`tradingagents/dataflows/`)

The call path is: agent tool (`agents/tools.py`, LangChain `@tool`) → `router.route_to_vendor(method, ...)` → the vendor function in `VENDOR_METHODS`.

- **The configured vendor list is the whole chain.** Values look like `"yfinance"` or `"sec_edgar,yfinance"`, set per category in `data_vendors` or per tool in `tool_vendors`. There is no silent fallback to vendors the user didn't list. Only the unset `"default"` uses all vendors.
- **Vendors signal failure with the `dataflows/errors.py` hierarchy**, and the router reacts by type:
  - `NoMarketDataError`: empty or stale data.
  - `VendorRateLimitError`: skip to the next vendor.
  - `VendorNotConfiguredError`: missing API key or config.
- **When no vendor succeeds, the router returns a text sentinel to the LLM** (`NO_DATA_AVAILABLE: ...` / `DATA_UNAVAILABLE: ...`), telling it not to fabricate values. Categories in `OPTIONAL_CATEGORIES` (macro, prediction markets) degrade instead of raising.
- **To add a vendor function:** register it in `VENDOR_METHODS`, and add the tool to `TOOLS_CATEGORIES` if it is new.

### Point-in-time integrity (core invariant)

A run dated in the past must never see information published after its `trade_date`. Many `test_*lookahead*` / `test_*pointintime*` tests enforce this.

- **Dated tools** take `trade_date` from graph state via `InjectedState`. They clamp whatever date the model asks for with `as_of()` / `as_of_window()` (`dataflows/date_window.py`).
- **Feeds** filter items with `in_window()`: half-open, in UTC, and undated items are kept only in live runs. `coverage_gap()` marks windows a feed never observed.
- **Live-only company profiles** are withheld in historical runs (`withhold_live_profile`).
- **SEC EDGAR** serves statements as originally filed.
- **Past-decision lessons** are filtered to those resolved by the trade date (`_memory_as_of`).

Any new dated data path needs the same treatment.

### LLM clients (`tradingagents/llm_clients/`)

`factory.create_llm_client()` routes each provider:
- Anthropic, Google, Azure and Bedrock have native clients.
- Every other provider goes through `OPENAI_COMPATIBLE_PROVIDERS` in `openai_client.py` (one `ProviderSpec` row each; wire-format quirks go in a `chat_class` subclass).

To add a provider or model, update the relevant tables. Don't add `if model == ...` branches.
- `api_key_env.py`: the provider → env var mapping. The CLI key prompt reads it.
- `capabilities.py`: per-model quirks, such as rejecting `tool_choice`, the structured-output method, or reasoning-content round-trips.
- `model_catalog.py`: CLI picker lists and validation. An unknown model ID only warns.

`build_llm_kwargs()` maps config to client kwargs. Provider-specific knobs are `openai_reasoning_effort`, `google_thinking_level` and `anthropic_effort`. `temperature`, `llm_max_retries` and `max_tokens` apply to every provider.

### Persistence

Everything is stored under `~/.tradingagents/` by default:
- `logs/`: the JSON state per run, and the markdown report tree.
- `cache/`: data cache, plus `checkpoints/<TICKER>.db`.
- `memory/trading_memory.md`: the decision log.

**Decision log** (`decision_log.py`):
- An append-only markdown file. Entries are separated by `<!-- ENTRY_END -->`. Each starts with a tag line `[date | ticker | rating | pending]`.
- One entry per ticker and date (idempotent).
- The next run for the same ticker settles pending entries (`graph/settlement.py`). It computes raw return and alpha against a regional benchmark over `holding_period_days`, and the Reflector writes a 2–4 sentence lesson.
- Lessons are injected only into the Portfolio Manager prompt.

**Checkpoints:**
- Opt-in, using LangGraph's `SqliteSaver`.
- The thread ID includes `_run_signature()` (analysts, rounds, asset type, portfolio fingerprint), so a changed run shape starts fresh.
- Resume by invoking with `None`, not the initial state.

**Backtest** (`backtest.py`):
- Writes to its own decision log under `results_dir/backtest/<run_id>/` and never touches the live one.
- Its docstring says explicitly that it evaluates decision quality and is not a portfolio or execution simulator; don't add order or fill modelling there.

User-supplied values used as path segments (tickers, run IDs) must go through `dataflows.symbols.safe_ticker_component`.

## Conventions

- Comments explain *why* and cite the GitHub issue that motivated the code (e.g. `(#1249)`). Follow that style when fixing a reported bug.
- `CHANGELOG.md` follows Keep a Changelog. Breaking import-path moves go in an "Upgrading from X" section at the top of the release.
