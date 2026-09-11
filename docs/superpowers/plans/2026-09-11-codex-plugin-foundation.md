# Codex Plugin Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement US-001–US-004 as an installed MCP discovery runtime and small, reusable extractions of existing financial role logic.

**Architecture:** Keep the MCP adapter in `tradingagents/plugin/server.py` and financial prompts/updates in their existing role modules. API factories retain invocation, structured fallback, and LangChain message handling. This milestone does not expose analysis or evidence operations.

**Tech Stack:** Python 3.10–3.13, official `mcp==1.26.0` SDK, existing Pydantic/LangChain, stdlib argparse/logging/tempfile/importlib, pytest, Ruff.

**Spec:** [Approved foundation design](../specs/2026-09-11-codex-plugin-foundation-design.md).

## Global Constraints

- Preserve Python 3.10–3.13 and the base-install CI checks.
- Stdout is exclusively MCP protocol output.
- Default state root is `~/.tradingagents/plugin/`, with a startup override.
- Prompt preparation performs no network requests, model construction, model invocation, or persistence.
- Keep reflection's existing concise wording and behavior; do not introduce a new reflection-language policy during extraction.
- Use existing pytest and Ruff infrastructure. No new test framework or type-checking gate.
- Shared updates do not mutate caller state in place.
- Keep existing API structured-output fallbacks and renderers.
- No SQLite schema, public evidence wrappers, workflow endpoints, or plugin manifest in this milestone.
- US-003 plugin-workflow consumption remains an explicit later integration assertion, not a completed criterion here.
- Preserve the user's untracked `AGENTS.md`; stage named implementation files only.

## Dependency decision and execution assumptions

Pin `mcp==1.26.0` without its CLI extra. Its [tagged package metadata](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/pyproject.toml) declares Python `>=3.10` and classifiers through 3.13. Use its [tagged FastMCP API](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/src/mcp/server/fastmcp/server.py), not current-main/v2 examples. Metadata was checked on 2026-09-11; installation/protocol compatibility is still an execution gate, proven by Task 7. Do not claim those installations have already passed.

Run commands from the implementation checkout with its virtual environment active. Before code changes, use the worktree workflow if isolation is needed, inspect the current diff, and run the baseline suite/lint. For each task: record the intended failing regression, implement, run its focused checks, then commit named files. An unexpected baseline failure is investigated separately rather than silently attributed to this feature.

## File map and delivery order

| Story | Tasks | Files and responsibility |
|---|---|---|
| US-001 | 1, 7 | `pyproject.toml`; new `tradingagents/plugin/__init__.py`, `server.py`; new `tests/test_plugin_runtime.py`; CI, smoke script, setup documentation |
| US-002 | 2, 7 | `server.py` capability schema/registration; `tradingagents/graph/__init__.py` lazy exports; new `tests/test_plugin_capabilities.py` |
| US-003 | 3, 4 | Existing four analyst modules and language helper; new `tests/test_shared_analyst_prompts.py` |
| US-004 | 5, 6 | Existing researchers, managers, trader, risk modules, `graph/reflection.py`; new `tests/test_shared_synthesis.py` |

No new role registry or shared prompt base class. Tasks 3–6 are mechanical extractions of current financial strings and update dictionaries, not rewritten financial guidance. Exact signatures below are the shared contract.

## Task 1: Installed stdio runtime and state-root checks

**Files:** Create `tradingagents/plugin/__init__.py`, `tradingagents/plugin/server.py`, `tests/test_plugin_runtime.py`; modify `pyproject.toml` optional dependencies and scripts.

**Interfaces:**

```python
def prepare_state_root(path: str | Path) -> Path: ...
def create_server() -> FastMCP: ...
def main(argv: list[str] | None = None) -> None: ...
```

`FastMCP` is imported locally inside `create_server`; use a TYPE_CHECKING import for its annotation. `plugin/__init__.py` has only a module docstring. `create_server` initially has no tools; Task 2 registers discovery.

- [ ] Add failing state-root checks:

```python
from pathlib import Path
import pytest

def test_state_root_is_created_and_probe_removed(tmp_path):
    from tradingagents.plugin.server import prepare_state_root
    root = prepare_state_root(tmp_path / "new")
    assert root == (tmp_path / "new").resolve()
    assert list(root.iterdir()) == []

def test_state_root_rejects_file(tmp_path):
    from tradingagents.plugin.server import prepare_state_root
    root = tmp_path / "file"
    root.write_text("keep", encoding="utf-8")
    with pytest.raises(OSError):
        prepare_state_root(root)
    assert root.read_text(encoding="utf-8") == "keep"

def test_write_probe_is_required(tmp_path, monkeypatch):
    from tradingagents.plugin import server
    def denied(*args, **kwargs):
        raise PermissionError("probe denied")
    monkeypatch.setattr(server.tempfile, "TemporaryFile", denied)
    with pytest.raises(PermissionError, match="probe denied"):
        server.prepare_state_root(tmp_path)
```

- [ ] Run `pytest tests/test_plugin_runtime.py -q`; expect missing-module failures.
- [ ] Add the dependency and entry point:

```toml
# Within the existing sections, not duplicate section headers:
# [project.optional-dependencies]
plugin = ["mcp==1.26.0"]
# [project.scripts]
tradingagents-mcp = "tradingagents.plugin.server:main"
```

- [ ] Implement root validation and startup:

```python
def prepare_state_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=root) as probe:
        probe.write(b"tradingagents")
        probe.flush()
    return root

def create_server() -> FastMCP:
    from mcp.server.fastmcp import FastMCP
    return FastMCP("TradingAgents", log_level="WARNING")
```

`main` uses argparse `--state-dir`, defaulting to `TRADINGAGENTS_PLUGIN_STATE_DIR` or `~/.tradingagents/plugin/`. Configure `logging.basicConfig(stream=sys.stderr, level=logging.WARNING)` before server construction. Catch only state-root `OSError` around validation and exit 1 with `Cannot use plugin state directory <path>: <reason>. Set --state-dir to a writable directory.` Catch `ModuleNotFoundError` from server creation only when `exc.name == "mcp"`, exiting 1 with `Install the plugin runtime with: python -m pip install 'tradingagents[plugin]'`; re-raise other missing dependencies. Run `server.run(transport="stdio")`. Add `if __name__ == "__main__": main()` for subprocess tests. Do not print success banners.

- [ ] Add a `main(["--state-dir", str(root)])` test with the file-path case above, asserting exit 1, empty captured stdout, and actionable stderr. Add a unit test that intercepts the `mcp` import with `builtins.__import__` raising `ModuleNotFoundError(name="mcp")`, then asserts the installation hint. This test runs even if the extra is installed.
- [ ] Run `pytest tests/test_plugin_runtime.py -q` and `ruff check tradingagents/plugin tests/test_plugin_runtime.py`; expect pass. Task 7 proves installed protocol behavior rather than counting these unit tests as that proof.
- [ ] Commit named files with `feat(plugin): add local stdio runtime`.

## Task 2: Honest discovery without importing the runner

**Files:** Modify `tradingagents/plugin/server.py`, `tradingagents/graph/__init__.py`; create `tests/test_plugin_capabilities.py`.

**Interfaces:** `get_capabilities() -> Capabilities`; `Capabilities` is an existing-Pydantic `BaseModel` subclass defined in `server.py`. `create_server()` registers it using `server.tool()(get_capabilities)`. No required tool arguments.

Schema fields (use typed nested models in the same file, with `extra="forbid"`):

```python
class RoleCapability(BaseModel):
    key: str
    label: str
    workflow_available: bool = False

class AnalysisSettings(BaseModel):
    available: bool = False
    asset_types: list[str]
    analysts: list[str]
    debate_rounds: int = 1
    risk_rounds: int = 1
    output_language: str = "English"
    vendor_selection: str = "ordered category and per-tool overrides"

class DataSourceCapability(BaseModel):
    credential_env: str | None
    credential_present: bool | None
    note: str

class Capabilities(BaseModel):
    runtime_version: str
    schema_version: int = 1
    mcp_sdk_version: str | None
    available_tools: list[str]
    planned_data_tools: list[str]
    roles: list[RoleCapability]
    analysis_settings: AnalysisSettings
    data_sources: dict[str, DataSourceCapability]
    api_runner_settings: list[str]
    reasoning_host: str = "Codex session; API-runner settings do not configure it"
```

- [ ] Write failing capability tests:

```python
def test_credentials_are_presence_only(monkeypatch):
    from tradingagents.plugin.server import get_capabilities
    monkeypatch.setenv("FRED_API_KEY", "secret-sentinel-123")
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    result = get_capabilities()
    assert result.data_sources["fred"].credential_present is True
    assert result.data_sources["alpha_vantage"].credential_present is False
    assert "secret-sentinel-123" not in result.model_dump_json()
    assert result.available_tools == ["get_capabilities"]
    assert result.analysis_settings.available is False
    assert [r.key for r in result.roles[:4]] == ["market", "social", "news", "fundamentals"]
    assert result.roles[1].label == "Sentiment Analyst"
    assert all(not r.workflow_available for r in result.roles)
```

Delete test credentials explicitly after the repository's autouse dummy-key fixture. Add empty-string and unrelated-secret cases; never snapshot the real environment.

- [ ] Run `pytest tests/test_plugin_capabilities.py -q`; expect missing-function failure.
- [ ] Make graph exports lazy, preserving its six existing public names and cached object identities:

```python
from importlib import import_module

_EXPORTS = {
    "TradingAgentsGraph": "trading_graph",
    "ConditionalLogic": "conditional_logic",
    "GraphSetup": "setup",
    "Propagator": "propagation",
    "Reflector": "reflection",
    "SignalProcessor": "signal_processing",
}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_EXPORTS[name]}", __name__), name)
    globals()[name] = value
    return value
```

This targeted change allows `from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS` without importing `trading_graph` or `default_config`. Test all six exports against their defining modules and unknown-name `AttributeError`.

- [ ] Implement `get_capabilities` using `importlib.metadata.version("tradingagents")`; SDK version may be `None` when its distribution is absent. Build analyst rows from `ANALYST_NODE_SPECS`; append `bull`, `bear`, `research_manager`, `trader`, `aggressive`, `conservative`, `neutral`, `portfolio_manager`, `reflection` with readable labels. Do not import their factories to list them.

List these exact planned operations: `get_stock_data`, `get_indicators`, `get_verified_market_snapshot`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_news`, `get_global_news`, `get_insider_transactions`, `get_macro_indicators`, `get_prediction_markets`, `resolve_instrument_identity`, `fetch_stocktwits_messages`, `fetch_reddit_posts`, `get_decision_history`. Names beyond the existing twelve are reserved descriptions, not registered tools.

Sources are `alpha_vantage`/`ALPHA_VANTAGE_API_KEY`, `fred`/`FRED_API_KEY`, and keyless `yfinance`, `polymarket`, `stocktwits`, `reddit`. For keyed sources use `bool(os.environ.get(name))`, matching adapter presence semantics; keyless sources use `None` for both credential fields. Notes explicitly say presence is not validity, and keyless availability is not guaranteed. No network probes or global configuration imports.

`api_runner_settings` lists `llm_provider`, `deep_think_llm`, `quick_think_llm`, `backend_url`, `temperature`, `llm_max_retries`, `max_tokens`, `google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort`; no values or credentials. Analysis defaults are PRD defaults, not environment-overlaid API defaults.

- [ ] Add a fresh subprocess regression from a temporary working directory, with inherited installation but `PYTHONPATH` absent and `TRADINGAGENTS_TEMPERATURE=invalid-for-api`. Its Python snippet is:

```python
import sys
from tradingagents.plugin.server import get_capabilities
assert get_capabilities().available_tools == ["get_capabilities"]
assert "tradingagents.graph.trading_graph" not in sys.modules
assert "tradingagents.default_config" not in sys.modules
assert "tradingagents.llm_clients.factory" not in sys.modules
```

Use `subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)`. Assert exit zero and stdout empty. Fresh subprocesses avoid the repository's global config fixture concealing import coupling. Add a discovery call test with `socket.socket.connect` patched to raise and `create_llm_client` patched to raise; serialized discovery must still succeed.

- [ ] Run `pytest tests/test_plugin_runtime.py tests/test_plugin_capabilities.py tests/test_analyst_execution.py tests/test_memory_log.py -q` and targeted Ruff; expect pass.
- [ ] Commit named files with `feat(plugin): expose capability and setup discovery`.

## Task 3: Explicit language and market/news/fundamentals builders

**Files:** Modify `tradingagents/agents/utils/agent_utils.py`, `tradingagents/agents/analysts/market_analyst.py`, `news_analyst.py`, `fundamentals_analyst.py`; create `tests/test_shared_analyst_prompts.py`.

**Interfaces:** Each role module exports `build_market_prompt`, `build_news_prompt`, or `build_fundamentals_prompt`, respectively, with signature `(state: Mapping[str, Any], *, output_language: str) -> str`. Return the complete concrete system message, including tool names, date and identity, with no LangChain object. Keep conversational history outside these builders.

- [ ] Add this parameterized failing check with imports for the three named builders:

```python
@pytest.mark.parametrize("builder", [build_market_prompt, build_news_prompt, build_fundamentals_prompt])
def test_analyst_context_and_explicit_language(builder, monkeypatch):
    from tradingagents.dataflows import config
    monkeypatch.setattr(config, "get_config", lambda: pytest.fail("global config read"))
    state = {"company_of_interest": "BTC-USD", "trade_date": "2026-09-10", "asset_type": "crypto"}
    prompt = builder(state, output_language="French")
    assert isinstance(prompt, str)
    assert "BTC-USD" in prompt and "2026-09-10" in prompt
    assert "crypto" in prompt and "French" in prompt
```

- [ ] Run `pytest tests/test_shared_analyst_prompts.py -q`; expect missing-builder failures.
- [ ] Extend the language helper without breaking its old call shape:

```python
def get_language_instruction(output_language: str | None = None) -> str:
    if output_language is None:
        from tradingagents.dataflows.config import get_config
        output_language = get_config().get("output_language", "English")
    if output_language.strip().lower() == "english":
        return ""
    return f" Write your entire response in {output_language}."
```

Move current system-message construction into each builder, replacing the language call with `get_language_instruction(output_language)`. Resolve placeholders as ordinary strings so braces inside identity are never reinterpreted as templates. Preserve every financial instruction and listed tool name. Fundamentals currently constructs a one-element tuple: preserve `str((body,))` when inserting its body into the concrete system message, matching the existing template's conversion. Add a regression assertion for this legacy formatting; removing it is outside this extraction.

- [ ] Update each API factory to resolve language from `get_config().get("output_language", "English")`, call its builder, and insert the result as a partial value in the existing `ChatPromptTemplate`; retain `MessagesPlaceholder`, `bind_tools`, and report completion checks:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_message}"),
    MessagesPlaceholder(variable_name="messages"),
]).partial(system_message=build_market_prompt(state, output_language=language))
chain = prompt | llm.bind_tools(tools)
result = chain.invoke(state["messages"])
```

Use the named role's builder in each module. Supply explicit language once; no global config reads occur inside builders. Both direct and API calls receive the same complete system message, including the characterized fundamentals formatting.

- [ ] Add checks for resolved identity containing braces, non-US suffixes, English's empty suffix, `get_verified_market_snapshot` guidance, missing-data instructions, and empty report on tool-call results. Use existing fake-model patterns in `test_news_analyst_prompt.py` and `test_market_toolnode.py`. Capture factory input and compare its domain content to the direct builder, including date and identity. Patch `requests.sessions.Session.request` and identity resolution to fail during direct builder calls.
- [ ] Run `pytest tests/test_shared_analyst_prompts.py tests/test_news_analyst_prompt.py tests/test_crypto_asset_mode.py tests/test_instrument_identity.py tests/test_market_toolnode.py tests/test_structured_agent_prompts.py -q` and targeted Ruff; expect pass.
- [ ] Commit named files with `refactor(agents): extract analyst prompts with explicit language`.

## Task 4: Sentiment prompt from caller-supplied evidence

**Files:** Modify `tradingagents/agents/analysts/sentiment_analyst.py`, `tests/test_shared_analyst_prompts.py`.

**Interface:**

```python
def build_sentiment_prompt(
    state: Mapping[str, Any], *, output_language: str,
    news_block: str, stocktwits_block: str, reddit_block: str,
) -> str: ...
```

Returns the concrete system message. Compute the start date with existing `_seven_days_back(state["trade_date"])`; the caller supplies complete recorded blocks, including unavailable text.

- [ ] Add failing pure-builder regression:

```python
def test_sentiment_uses_recorded_blocks(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as module
    def forbidden(*args, **kwargs):
        pytest.fail("prompt builder fetched evidence")
    monkeypatch.setattr(module.get_news, "func", forbidden)
    monkeypatch.setattr(module, "fetch_stocktwits_messages", forbidden)
    monkeypatch.setattr(module, "fetch_reddit_posts", forbidden)
    state = {"company_of_interest": "SHOP.TO", "trade_date": "2026-09-10"}
    blocks = {"news_block": "news {verbatim}", "stocktwits_block": "<unavailable>", "reddit_block": "saved reddit"}
    prompt = module.build_sentiment_prompt(state, output_language="French", **blocks)
    assert all(block in prompt for block in blocks.values())
    assert "2026-09-03" in prompt and "2026-09-10" in prompt
    assert "SHOP.TO" in prompt and "French" in prompt
```

- [ ] Run that test; expect missing-builder failure.
- [ ] Extend existing `_build_system_message` with keyword `output_language: str | None = None` and replace its language call with the explicit helper argument. Preserve compatibility for old direct callers. `build_sentiment_prompt` passes a required explicit language, reuses this body, and prepends the existing system wrapper with instrument/date and `NO_EXTERNAL_TOOLS` text. Keep block delimiters unchanged.
- [ ] In the factory leave all three fetch calls, limits, date arguments and structured binding intact. Replace prompt construction with the builder result through a literal partial placeholder, retain `state["messages"]`, `invoke_structured_or_freetext`, `render_sentiment_report`, and `AIMessage`. Do not move fetching to a new abstraction.
- [ ] Extend the fake-factory tests to assert each source is fetched once with the existing window and the resulting model system message equals the direct builder for those blocks. Exercise unavailable blocks and structured fallback; preserve `create_social_media_analyst` alias behavior.
- [ ] Run `pytest tests/test_shared_analyst_prompts.py tests/test_structured_agents.py tests/test_social_lookahead.py tests/test_crypto_asset_mode.py -q` and targeted Ruff; expect pass.
- [ ] Commit named files with `refactor(agents): prepare sentiment from supplied evidence`.

## Task 5: Research and trader prompt/update extraction

**Files:** Modify `tradingagents/agents/researchers/bull_researcher.py`, `bear_researcher.py`, `managers/research_manager.py`, `trader/trader.py`; create `tests/test_shared_synthesis.py`.

**Interfaces:** In each respective module:

| Function | Signature / result |
|---|---|
| `build_bull_prompt`, `build_bear_prompt`, `build_research_manager_prompt` | `(state: Mapping[str, Any], *, output_language: str) -> str` |
| `build_trader_messages` | `(state: Mapping[str, Any], *, output_language: str) -> list[dict[str, str]]` |
| `apply_bull_output`, `apply_bear_output`, `apply_research_manager_output`, `apply_trader_output` | `(state: Mapping[str, Any], output: str) -> dict[str, Any]` |

- [ ] Add a failing direct update check:

```python
def test_bull_update_preserves_state():
    from copy import deepcopy
    from tradingagents.agents.researchers.bull_researcher import apply_bull_output
    state = {"investment_debate_state": {"history": "prior", "bull_history": "", "bear_history": "bear", "count": 2}}
    before = deepcopy(state)
    result = apply_bull_output(state, "new case")["investment_debate_state"]
    assert state == before
    assert result == {"history": "prior\nBull Analyst: new case", "bull_history": "\nBull Analyst: new case", "bear_history": "bear", "current_response": "Bull Analyst: new case", "count": 3}
```

- [ ] Run `pytest tests/test_shared_synthesis.py -q`; expect missing-function failure.
- [ ] Move the current state reads and prompt expressions before invocation into the named builders. Change only language acquisition to the explicit parameter. For the trader preserve both messages and the conditional technical-report branch. Move dictionary assembly after invocation into named update functions, replacing `response.content`/rendered result with `output`. Do not share bull/bear implementations through a new helper: each existing short dictionary is its role contract.

API researcher node shape:

```python
language = get_config().get("output_language", "English")
response = llm.invoke(build_bull_prompt(state, output_language=language))
return apply_bull_output(state, response.content)
```

Research manager retains its original `bind_structured` and `invoke_structured_or_freetext` call, passing the shared prompt, then calls `apply_research_manager_output`. The manager patch preserves judge decision, current response and unchanged count. Trader's domain update is:

```python
def apply_trader_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    return {"trader_investment_plan": output}
```

Its factory adds `messages: [AIMessage(content=trader_plan)]` and `sender: name` to that patch. Keep `functools.partial(..., name="Trader")` compatibility.

- [ ] Add direct tests for bear prefixes/counter, absent-opponent marker, all four report sentinel strings, crypto wording and explicit language with global lookup forbidden. Test research-manager patch fields and unchanged count. Test trader messages both with and without `market_report`, absolute-price instructions, and no empty technical-report section. For each factory compare captured invocation to its direct builder and returned domain fields to its updater; compare API-only message/sender fields separately. Reuse current structured fake models for success, unsupported binding, `None`, and invocation exception fallback.
- [ ] Run `pytest tests/test_shared_synthesis.py tests/test_debate_opening.py tests/test_structured_agents.py tests/test_structured_agent_prompts.py tests/test_crypto_asset_mode.py -q` and targeted Ruff; expect pass.
- [ ] Commit named files with `refactor(agents): share research and trader role logic`.

## Task 6: Risk, portfolio, and reflection extraction

**Files:** Modify `tradingagents/agents/risk_mgmt/aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`, `tradingagents/agents/managers/portfolio_manager.py`, `tradingagents/graph/reflection.py`, `tests/test_shared_synthesis.py`.

**Interfaces:**

- Each risk module exports `build_aggressive_prompt` / `build_conservative_prompt` / `build_neutral_prompt` with `(state: Mapping[str, Any], *, output_language: str) -> str`, and the corresponding `apply_aggressive_output` / `apply_conservative_output` / `apply_neutral_output` with `(state: Mapping[str, Any], output: str) -> dict[str, Any]`.
- Portfolio exports `build_portfolio_manager_prompt(state: Mapping[str, Any], *, output_language: str) -> str` and `apply_portfolio_manager_output(state: Mapping[str, Any], output: str) -> dict[str, Any]`.
- Reflection exports `get_log_reflection_prompt() -> str` and `build_reflection_messages(final_decision: str, raw_return: float, alpha_return: float, benchmark_name: str = "SPY", *, system_prompt: str | None = None) -> list[tuple[str, str]]`.

- [ ] Write a parameterized failing risk-update check (import the three named updaters):

```python
@pytest.mark.parametrize("key,label,apply", [("aggressive", "Aggressive", apply_aggressive_output), ("conservative", "Conservative", apply_conservative_output), ("neutral", "Neutral", apply_neutral_output)])
def test_risk_patch(key, label, apply):
    from copy import deepcopy
    debate = {"history": "prior", "count": 4, "latest_speaker": "prior"}
    for role in ("aggressive", "conservative", "neutral"):
        debate[f"{role}_history"] = f"saved {role}"
        debate[f"current_{role}_response"] = f"last {role}"
    state = {"risk_debate_state": debate}
    before = deepcopy(state)
    result = apply(state, "new")["risk_debate_state"]
    assert state == before
    assert result["count"] == 5 and result["latest_speaker"] == label
    assert result["history"] == f"prior\n{label} Analyst: new"
    assert result[f"{key}_history"] == f"saved {key}\n{label} Analyst: new"
    assert result[f"current_{key}_response"] == f"{label} Analyst: new"
    for other in {"aggressive", "conservative", "neutral"} - {key}:
        assert result[f"{other}_history"] == debate[f"{other}_history"]
        assert result[f"current_{other}_response"] == debate[f"current_{other}_response"]
```

- [ ] Run `pytest tests/test_shared_synthesis.py -q`; expect missing-function failures.
- [ ] Move existing risk and portfolio prompt expressions into their builders, passing explicit language. Move existing returned dictionaries into updates; preserve exact role prefixes and `latest_speaker="Judge"` for portfolio. Portfolio's count and all histories remain unchanged; `final_trade_decision` and judge decision receive output. Keep the original structured bind/invoke/renderer in the portfolio factory. Risk factories invoke the shared builder then call their update with `response.content`.
- [ ] Move reflection's existing system literal into `get_log_reflection_prompt`. Keep `Reflector._get_log_reflection_prompt` as a compatibility delegate and `self.log_reflection_prompt` initialization. The pure message builder uses the existing `+.1%` formatting and `human` role; choose the supplied `system_prompt` when not `None`. Existing `reflect_on_final_decision` calls that builder with `system_prompt=self.log_reflection_prompt`, preserving callers that customize this attribute, then invokes the existing model once.
- [ ] Add reflection equivalence regression:

```python
def test_reflection_builder_and_adapter_match():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from tradingagents.graph.reflection import Reflector, build_reflection_messages
    model = Mock()
    model.invoke.return_value = SimpleNamespace(content="lesson")
    reflector = Reflector(model)
    assert reflector.reflect_on_final_decision("decision", .042, .021, "^N225") == "lesson"
    messages = build_reflection_messages("decision", .042, .021, "^N225")
    model.invoke.assert_called_once_with(messages)
    assert "+4.2%" in messages[1][1] and "Alpha vs ^N225: +2.1%" in messages[1][1]
```

Add a custom `log_reflection_prompt` assertion, negative returns, and default SPY. Direct builders must work without constructing `Reflector`. Do not extract outcome calculation or memory writes.

- [ ] Test all risk prompt inputs and absent peers; portfolio with and without `past_context`; no network/global language lookup during direct preparation; exact domain-patch equivalence with fake factory outputs. Run `pytest tests/test_shared_synthesis.py tests/test_debate_opening.py tests/test_structured_agent_prompts.py tests/test_memory_log.py tests/test_memory_pointintime.py tests/test_risk_router_path_map.py -q` and targeted Ruff; expect pass.
- [ ] Commit named files with `refactor(agents): share risk portfolio and reflection logic`.

## Task 7: Clean install, protocol checks, CI, and milestone record

**Files:** Create `scripts/smoke_plugin_protocol.py`, `docs/plugin-runtime.md`; modify `.github/workflows/ci.yml`, `tests/test_plugin_runtime.py`, `tests/test_plugin_capabilities.py`. Retain the spec's staged-acceptance paragraph.

**Interface:** `scripts/smoke_plugin_protocol.py` is a standalone installed-package test executable with no project imports at module scope. It builds an isolated temporary cwd, selects `Path(sys.executable).with_name("tradingagents-mcp")`, drives the stdio protocol with SDK `ClientSession`, and fails on protocol/setup errors. No pytest dependency.

- [ ] Add a protocol smoke client using this core:

```python
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def check():
    with tempfile.TemporaryDirectory() as directory:
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
        env["TRADINGAGENTS_TEMPERATURE"] = "invalid-for-api"
        params = StdioServerParameters(
            command=str(Path(sys.executable).with_name("tradingagents-mcp")),
            args=["--state-dir", str(Path(directory) / "state")],
            cwd=directory, env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == ["get_capabilities"]
                result = await session.call_tool("get_capabilities", {})
                assert not result.isError
                assert result.structuredContent["available_tools"] == ["get_capabilities"]
                assert result.structuredContent["data_sources"]["fred"]["credential_present"] is False

if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(check(), timeout=30))
```

The SDK merges selected default environment fields; no LLM key names are included in defaults. Test from a temporary directory without ancestor `.env` files and verify package imports resolve under installed site-packages in a separate `python -I -c` assertion. Do not use editable installs for this smoke.

- [ ] Add a strict stdout regression in `test_plugin_runtime.py` that launches the module with `subprocess.Popen`, pipes and a 30-second overall timeout. Send newline-delimited JSON-RPC `initialize` (protocol `2025-11-25`, capabilities `{}`, clientInfo name/version), read the response, send `notifications/initialized`, then `tools/list`. Parse **every** stdout line with `json.loads`; reject any non-JSON line, wrong `jsonrpc`, or missing response IDs. Close stdin and terminate/kill in `finally` if necessary. This complements the SDK client, which should not be assumed to reject every stray log line. Capture stderr separately and never merge it into stdout.

- [ ] Wire pytest protocol tests to `pytest.importorskip("mcp")` inside only the tests that require the SDK. Base tests of pure discovery and missing-extra behavior still run without it. Do not import MCP unconditionally at test-module collection time.
- [ ] Add a separate CI job with the same `python-version: ["3.10", "3.11", "3.12", "3.13"]` matrix. Install the non-editable package with dev/plugin extras; run `pip check`, protocol smoke, and focused new tests:

```yaml
  plugin:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install ".[dev,plugin]"
      - run: python -m pip check
      - run: python scripts/smoke_plugin_protocol.py
      - run: pytest tests/test_plugin_runtime.py tests/test_plugin_capabilities.py tests/test_shared_analyst_prompts.py tests/test_shared_synthesis.py -q
```

Retain existing base test and lint jobs. Strengthen `smoke-install` after its base install with `python -I -c "import importlib.util; import tradingagents, cli.main; assert importlib.util.find_spec('mcp') is None"`; do not add the plugin extra to that job. Metadata-only SDK compatibility is insufficient: all four plugin jobs must pass before completion. If the pin fails the matrix, resolve and review a new compatible pin before proceeding; never raise the project Python floor silently.

- [ ] Write `docs/plugin-runtime.md` with exact setup commands, requiring an activated dedicated Python environment:

```bash
python -m pip install ".[plugin]"
python -m pip check
tradingagents-mcp --state-dir "$HOME/.tradingagents/plugin"
```

Explain that direct launch waits for an MCP client on stdin; a successful empty terminal is not a completed analysis. Document default path, `--state-dir` precedence over `TRADINGAGENTS_PLUGIN_STATE_DIR`, protocol-only stdout, optional Alpha Vantage/FRED credentials, keyless-source limits, and inherited package `.env` lookup relative to cwd. Recommend exported environment settings for launches outside the checkout. Document version-pinned SDK and `get_capabilities` as the only current tool; host manifest/activation and full workflow remain US-018/US-005 onward. Do not claim manifest installation provisions Python.

- [ ] Run final verification in the execution environment:

```bash
python -m pip install -e ".[dev,plugin]"
pytest -q
ruff check .
python -m pip wheel . --no-deps -w /tmp/tradingagents-foundation-dist
git diff --check
```

Separately create a fresh venv under a temporary directory, install `.[plugin]` non-editably from the checkout, run `pip check` and the smoke script using that environment's Python. Record actual Python versions, exit status, and any unavailable matrix runners; do not equate one local pass with all four CI results.

- [ ] Record US-001/002 checks and US-003/004 extraction checks against the PRD. Keep US-003's real plugin-consumption check open for US-009 integration; no full-product completion statement. Commit named files with `test(plugin): verify clean installs and protocol discovery`.

## Plan self-review and handoff

- Runtime/optional install/stdout/unwritable-root requirements: Tasks 1 and 7.
- Typed capabilities, secret absence, missing-key independence and API-setting separation: Task 2, plus installed smoke in Task 7.
- All four analyst builders, explicit language, crypto/date/identity and saved sentiment evidence: Tasks 3 and 4.
- All nine synthesis/reflection roles, output updates and API fallbacks: Tasks 5 and 6.
- Base compatibility and complete test/lint gates: Task 7.
- Later integrations remain explicit: real workflow consumption, run storage, outcome preparation, host packaging and installed-host acceptance.

Planning produced documentation only. Choose inline execution with checkpoints or subagent-driven execution before applying this plan.
