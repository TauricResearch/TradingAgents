# LM Studio Support

This document describes the LM Studio provider integration added to TradingAgents, including setup, configuration, and how to run the tests.

## What was changed

LM Studio is now a first-class provider alongside Ollama, using the same OpenAI-compatible chat completions path. The changes touch six source files and add a new test file:

| File | Change |
|---|---|
| `tradingagents/llm_clients/factory.py` | Added `"lmstudio"` to the OpenAI-compatible provider tuple |
| `tradingagents/llm_clients/openai_client.py` | Added `http://localhost:1234/v1` default URL; `LMSTUDIO_BASE_URL` env-var override |
| `tradingagents/llm_clients/api_key_env.py` | Registered `"lmstudio"` as a no-auth local runtime (`None`) |
| `tradingagents/llm_clients/model_catalog.py` | Added quick and deep model lists with a "Custom model ID" escape hatch |
| `tradingagents/llm_clients/validators.py` | LM Studio accepts any model ID — no catalog validation |
| `cli/utils.py` | Added LM Studio to the provider dropdown; added `confirm_lmstudio_endpoint()` |
| `cli/main.py` | Calls `confirm_lmstudio_endpoint()` after provider selection |
| `tests/test_lmstudio_base_url.py` | 19 new tests (see below) |
| `tests/test_api_key_env.py` | Added `"lmstudio"` to the provider coverage assertion |

## Prerequisites

1. Download and install [LM Studio](https://lmstudio.ai).
2. Load a model inside LM Studio.
3. Start the local server: **LM Studio → Local Server → Start Server** (default port: `1234`).

## Configuration

### Default endpoint

LM Studio's server runs at `http://localhost:1234/v1` by default. No configuration is required when using the default.

### Custom endpoint (`LMSTUDIO_BASE_URL`)

To point TradingAgents at a different host or port — for example a remote LM Studio instance or a local proxy — set `LMSTUDIO_BASE_URL` in your environment or `.env` file:

```bash
LMSTUDIO_BASE_URL=http://192.168.1.50:1234/v1
```

The value is read at call time (not import time), so changes take effect without restarting the process.

### No API key required

LM Studio's built-in server does not enforce authentication by default. TradingAgents does not prompt for or require an API key when `lmstudio` is selected.

## Usage

### Interactive CLI

Run the TradingAgents CLI and select **LM Studio** from the provider dropdown:

```bash
python main.py
# Step 6: select "LM Studio"
# The resolved endpoint is printed before model selection
```

The CLI will show the resolved endpoint (and its source — default vs `LMSTUDIO_BASE_URL`) before asking you to pick a model.

### Python API

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["llm_provider"]   = "lmstudio"
config["quick_think_llm"] = "meta-llama-3.2-3b-instruct"  # model ID from LM Studio
config["deep_think_llm"]  = "meta-llama-3.3-70b-instruct"
# config["backend_url"]  = "http://192.168.1.50:1234/v1"  # optional override

ta = TradingAgentsGraph(config=config)
```

The `backend_url` key in the config overrides `LMSTUDIO_BASE_URL` and the compiled-in default, in that order of precedence.

### Model IDs

The CLI offers a curated list of common models. **The model ID must match exactly what LM Studio reports in its server tab** — check the "Model identifier" shown there, or use "Custom model ID" in the dropdown to type it directly.

Typical format: `meta-llama-3.3-70b-instruct`, `qwen2.5-7b-instruct`, `phi-4-mini-instruct`.

## Running the tests

### Install dependencies

```bash
# With uv (recommended — installs the project + all deps including questionary)
uv sync

# Or with pip
pip install -e ".[dev]"
# If there is no [dev] extra, install from requirements directly:
pip install -r requirements.txt
```

### Run the LM Studio tests

```bash
# All LM Studio tests
uv run pytest tests/test_lmstudio_base_url.py -v

# Or without uv
python -m pytest tests/test_lmstudio_base_url.py -v
```

### Run all provider-related tests together

```bash
uv run pytest tests/test_lmstudio_base_url.py \
              tests/test_ollama_base_url.py \
              tests/test_api_key_env.py \
              tests/test_model_validation.py -v
```

### Run the full test suite

```bash
uv run pytest
```

### Expected results

The 12 non-CLI tests in `test_lmstudio_base_url.py` pass without any external services. The 7 CLI tests (`test_cli_dropdown_*`, `test_confirm_endpoint_*`) require `questionary` to be installed — they pass when run via `uv run pytest` (which uses the project virtualenv) and fail when run against a bare Python install that lacks `questionary`. This is the same behaviour as the equivalent Ollama tests.

## Test coverage

`tests/test_lmstudio_base_url.py` covers:

| Area | Tests |
|---|---|
| `_resolve_provider_base_url` | Default URL, env-var override, call-time evaluation, no cross-provider leakage, Ollama env does not affect LM Studio |
| `OpenAIClient.get_llm()` | Picks up `LMSTUDIO_BASE_URL`; explicit `base_url` wins over env |
| CLI dropdown | Reflects `LMSTUDIO_BASE_URL`; falls back to default when unset |
| `confirm_lmstudio_endpoint` | Shows default, marks env origin, warns on missing scheme, warns on non-default remote port, quiet for localhost |
| Model catalog | No `(local)` labels; `"custom"` option present and last |
| `api_key_env` | `get_api_key_env("lmstudio")` returns `None` |
| `validators` | Any model ID accepted |
| Factory routing | `create_llm_client(provider="lmstudio")` returns an `OpenAIClient` |
