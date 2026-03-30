# Plan: Simplify Env Loading and Config Precedence

**Status**: pending
**ADR**: 006 (update required)
**Branch**: codex/simplify-env-config-precedence-wt
**Depends on**: none

## Context

Environment-variable handling is currently spread across multiple layers:

- `tradingagents/default_config.py` loads `.env` at module import time and builds `DEFAULT_CONFIG`.
- `main.py` and `cli/main.py` also call `load_dotenv()`.
- `tests/unit/test_env_override.py` relies on `importlib.reload()` and patches `dotenv.load_dotenv` to avoid developer-local `.env` leakage.
- `tradingagents/dataflows/config.py` snapshots `DEFAULT_CONFIG.copy()` into a mutable module-global cache.
- Some runtime paths still read `os.getenv(...)` directly instead of using a built config object.

That makes precedence harder to reason about, couples behavior to import order, and lets tests accidentally consume developer-local secrets.

## Target Model

There should be exactly one place responsible for building default runtime config and loading optional `.env` values.

Precedence must be:

1. Hardcoded defaults
2. `.env`
3. Explicit process environment

Tests must default to deterministic hardcoded values unless a test explicitly opts into `.env` loading.

Config consumers should receive an already-built config object and should not reload dotenv or reconstruct precedence themselves.

## Decision

Refactor `tradingagents/default_config.py` into a single config-builder module that:

- defines hardcoded defaults in code
- optionally loads `.env` into an isolated overlay
- merges `.env` and real environment with explicit precedence
- exposes `build_default_config(...)` for deterministic rebuilds in tests
- keeps `DEFAULT_CONFIG = build_default_config()` for runtime convenience

Routing and graph code should read from built config state, not from raw environment or implicit module-import side effects.

The interface layer should also be reviewed during this refactor so we keep only the abstractions that actually protect boundaries:

- keep a routing boundary if it centralizes vendor selection and observability
- remove or simplify interface layers that only forward calls while hiding config ownership
- avoid graph-level config passing on one side and module-global config lookup on the other

## Additional Overcomplicated Logic Discovered

- **Mutable config singleton in `tradingagents/dataflows/config.py`**
  The module caches a copied config globally and initializes it at import time. That obscures lifetime and makes tests/stateful flows harder to reason about.
- **Split config interface in graphs vs routing**
  Graph classes accept a `config` object, but `route_to_vendor()` still resolves vendors from a separate module-global config set via `set_config()`. That is unnecessary abstraction because config is both explicit and implicit at the same time.
- **Mixed ownership between config and raw env reads**
  Some modules use built config while others read `os.getenv(...)` directly for the same concepts (`mongo_uri`, `mongo_db`, reports dir). That weakens the “single source of truth” guarantee.
- **Import-time behavior as public contract**
  Current docs and tests encode “importing config loads `.env`” as an invariant. That is the core hidden side effect causing brittle tests.
- **Shallow copies of nested config**
  Many call sites use `DEFAULT_CONFIG.copy()`. For nested keys like `data_vendors` and `tool_vendors`, that keeps shared nested dict references unless callers replace them fully.
- **Very thin tool-interface wrappers**
  Most `agents/utils/*_tools.py` functions are valid LangChain tool definitions, but architecturally they are mostly pass-through wrappers over `route_to_vendor()`. They are acceptable for schema exposure, but should not become another place where config or vendor logic is re-decided.
- **Duplicated LLM config resolution across graphs**
  `TradingAgentsGraph`, `ScannerGraph`, and `PortfolioGraph` each reimplement similar provider/model/backend fallback logic. This is adjacent complexity worth noting, though it should only be folded into this task if it materially blocks config simplification.

