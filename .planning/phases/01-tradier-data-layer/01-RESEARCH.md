# Phase 1: Tradier Data Layer - Research

**Researched:** 2026-03-29
**Domain:** REST API integration, options chain data retrieval, vendor routing pattern
**Confidence:** HIGH

## Summary

Phase 1 integrates Tradier as a new data vendor for options chain retrieval with 1st-order Greeks and implied volatility. The Tradier REST API is simple (3 endpoints, bearer token auth, JSON responses) and maps cleanly onto the existing vendor routing architecture in `tradingagents/dataflows/`. The implementation follows established patterns: one vendor module file (`tradier.py`), registration in `interface.py` registries, and new `@tool` functions in `tradingagents/agents/utils/`.

The primary complexity is not in the API calls themselves but in the data structure design (dual output: DataFrame + typed dataclasses), the pre-fetch/caching strategy for multiple expirations, and rate limit handling within the existing fallback framework. The Tradier API returns Greeks via ORATS with an `updated_at` timestamp that must be surfaced to downstream agents for staleness detection.

**Primary recommendation:** Use `requests` directly (no SDK), create `tradingagents/dataflows/tradier.py` following the `y_finance.py` pattern, register a new `options_chain` tool category in `interface.py`, and implement typed dataclasses (`OptionsContract`, `OptionsChain`) alongside DataFrame output.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `TRADIER_API_KEY` env var for credentials, matching existing pattern (`OPENAI_API_KEY`, `ALPHA_VANTAGE_KEY`)
- **D-02:** Support sandbox via `TRADIER_SANDBOX=true` env var -- auto-detect base URL (`sandbox.tradier.com` vs `api.tradier.com`)
- **D-03:** Pre-fetch all expirations within DTE range upfront at the start of an analysis run, cache for the session. Do NOT let individual agents make separate API calls for the same data.
- **D-04:** Default DTE filter range: 0-50 DTE (covers TastyTrade's 30-50 sweet spot plus weeklies and near-term options)
- **D-05:** Always request `greeks=true` from Tradier -- there is no reason to skip Greeks when the whole point is options analysis
- **D-06:** Dual output format: Pandas DataFrame for bulk operations (consistent with existing yfinance pattern) AND typed dataclass (`OptionsContract`, `OptionsChain`) for individual contract access by downstream agents

### Claude's Discretion
- **Caching strategy:** Claude picks the best caching approach. In-memory per-session is simpler; disk TTL helps during development. Choose based on what fits the existing architecture best.
- **Rate limit handling:** Claude picks the best approach based on existing `AlphaVantageRateLimitError` fallback pattern. Options include retry with backoff, pre-emptive throttling, or both.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | System can retrieve full options chain (strikes, expirations, bid/ask, volume, OI) via Tradier API | Tradier `/v1/markets/options/chains` endpoint returns all fields. See Architecture Patterns for response mapping. |
| DATA-02 | System can retrieve options expirations and available strikes for any ticker via Tradier API | Tradier `/v1/markets/options/expirations` with `strikes=true` returns both in one call. |
| DATA-03 | System displays 1st-order Greeks (Delta, Gamma, Theta, Vega, Rho) from ORATS via Tradier | Tradier `greeks=true` parameter returns `delta`, `gamma`, `theta`, `vega`, `rho`, `phi` + `updated_at` timestamp. |
| DATA-04 | System displays implied volatility per contract (bid_iv, mid_iv, ask_iv, smv_vol) | Tradier Greeks object includes `bid_iv`, `mid_iv`, `ask_iv`, `smv_vol` when `greeks=true`. |
| DATA-05 | System can filter options chains by DTE range (e.g., 30-60 DTE) | Fetch expirations first, filter by DTE range (D-04: 0-50 default), then fetch chains only for qualifying expirations. |
| DATA-08 | System integrates Tradier as new vendor in the existing data routing layer | Register `"tradier"` in `VENDOR_LIST`, add `options_chain` category to `TOOLS_CATEGORIES`, add methods to `VENDOR_METHODS`, add `"options_chain": "tradier"` to `DEFAULT_CONFIG["data_vendors"]`. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | >=2.32.4 | HTTP client for Tradier API | Already a project dependency. Tradier API is 3 simple REST endpoints -- no SDK needed. Consistent with alpha_vantage pattern. |
| pandas | >=2.3.0 | DataFrame output for bulk chain operations | Already a project dependency. DataFrame is the standard output format for vendor data functions (see `y_finance.py`). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dateutil | >=2.9.0 | DTE calculation from expiration dates | Already an indirect dependency. Used for date arithmetic in DTE filtering. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct requests | uvatradier SDK | Thin wrapper adds dependency without meaningful abstraction; Tradier REST API is 3 endpoints |
| Direct requests | lumiwealth-tradier | Same reasoning; direct requests with typed response models is cleaner |

**Installation:**
```bash
# No new packages needed for Phase 1
# requests and pandas already in project dependencies
```

**Version verification:** All required packages are already present in the project's `pyproject.toml`. No new dependencies for this phase.

## Architecture Patterns

### Recommended Project Structure
```
tradingagents/
  dataflows/
    tradier.py                    # New: Tradier vendor module (chains, expirations, strikes)
    tradier_common.py             # New: Auth, base URL, rate limit error, HTTP helper
    interface.py                  # Modified: Add options_chain category + tradier vendor
    config.py                     # Unchanged
  agents/
    utils/
      options_tools.py            # New: @tool functions for options data retrieval
  default_config.py               # Modified: Add "options_chain": "tradier" to data_vendors
```

### Pattern 1: Vendor Module Structure (tradier.py)
**What:** One file per vendor with exported functions matching `VENDOR_METHODS` signatures.
**When to use:** Always -- this is the established pattern.
**Example:**
```python
# Source: existing pattern from tradingagents/dataflows/y_finance.py
# tradingagents/dataflows/tradier.py

from typing import Annotated
from datetime import datetime, date
from dataclasses import dataclass, field
import pandas as pd
import requests

from .tradier_common import get_api_key, get_base_url, TradierRateLimitError


@dataclass
class OptionsContract:
    """Single options contract with Greeks and IV."""
    symbol: str              # OCC symbol e.g. AAPL220617C00270000
    underlying: str          # e.g. AAPL
    option_type: str         # "call" or "put"
    strike: float
    expiration_date: str     # YYYY-MM-DD
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    # Greeks (from ORATS)
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    phi: float | None = None
    # IV
    bid_iv: float | None = None
    mid_iv: float | None = None
    ask_iv: float | None = None
    smv_vol: float | None = None
    greeks_updated_at: str | None = None


@dataclass
class OptionsChain:
    """Full options chain for a ticker across expirations."""
    underlying: str
    fetch_timestamp: str
    expirations: list[str]
    contracts: list[OptionsContract] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to DataFrame for bulk operations."""
        return pd.DataFrame([vars(c) for c in self.contracts])

    def filter_by_dte(self, min_dte: int = 0, max_dte: int = 50) -> "OptionsChain":
        """Filter contracts by DTE range; skip contracts with bad expiration_date strings."""
        today = date.today()
        filtered = []
        for c in self.contracts:
            try:
                exp = datetime.strptime(c.expiration_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                # Log/skip malformed c.expiration_date — do not fail whole chain
                continue
            dte = (exp - today).days
            if min_dte <= dte <= max_dte:
                filtered.append(c)
        filtered_exps = list({c.expiration_date for c in filtered})
        return OptionsChain(
            underlying=self.underlying,
            fetch_timestamp=self.fetch_timestamp,
            expirations=sorted(filtered_exps),
            contracts=filtered,
        )
```

### Pattern 2: Tradier Common Module (tradier_common.py)
**What:** Auth, base URL detection, rate limit error, shared HTTP helper -- mirrors `alpha_vantage_common.py`.
**Example:**
```python
# tradingagents/dataflows/tradier_common.py

import os
import requests

TRADIER_PRODUCTION_URL = "https://api.tradier.com"
TRADIER_SANDBOX_URL = "https://sandbox.tradier.com"


class TradierRateLimitError(Exception):
    """Exception raised when Tradier API rate limit is exceeded."""
    pass


def get_api_key() -> str:
    api_key = os.getenv("TRADIER_API_KEY")
    if not api_key:
        raise ValueError("TRADIER_API_KEY environment variable is not set.")
    return api_key


def get_base_url() -> str:
    sandbox = os.getenv("TRADIER_SANDBOX", "false").lower() in ("true", "1", "yes")
    return TRADIER_SANDBOX_URL if sandbox else TRADIER_PRODUCTION_URL


def make_tradier_request(path: str, params: dict | None = None) -> dict:
    """Make authenticated GET request to Tradier API.

    Raises:
        TradierRateLimitError: When rate limit is exceeded.
        requests.HTTPError: On other HTTP errors.
    """
    url = f"{get_base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Accept": "application/json",
    }
    response = requests.get(url, headers=headers, params=params or {})

    # Check rate limit via headers (defensive parse — header may be non-numeric)
    remaining_raw = response.headers.get("X-Ratelimit-Available")
    expiry = response.headers.get("X-Ratelimit-Expiry")
    if remaining_raw is not None:
        try:
            remaining = int(remaining_raw)
        except (ValueError, TypeError):
            raise TradierRateLimitError(
                f"Invalid X-Ratelimit-Available={remaining_raw!r}; X-Ratelimit-Expiry={expiry!r}"
            )
        if remaining <= 0:
            raise TradierRateLimitError(
                f"Tradier rate limit exceeded (quota {remaining}). Resets at: {expiry}"
            )

    # Also check HTTP 429
    if response.status_code == 429:
        raise TradierRateLimitError("Tradier rate limit exceeded (HTTP 429)")

    response.raise_for_status()
    return response.json()
```

### Pattern 3: Vendor Registration in interface.py
**What:** Register new tool category, vendor, and method mappings.
**Example:**
```python
# Additions to tradingagents/dataflows/interface.py

from .tradier import (
    get_options_chain as get_tradier_options_chain,
    get_options_expirations as get_tradier_options_expirations,
)

# Add to TOOLS_CATEGORIES:
"options_chain": {
    "description": "Options chain data with Greeks and IV",
    "tools": [
        "get_options_chain",
        "get_options_expirations",
    ]
}

# Add to VENDOR_LIST:
VENDOR_LIST = ["yfinance", "alpha_vantage", "tradier"]

# Add to VENDOR_METHODS:
"get_options_chain": {
    "tradier": get_tradier_options_chain,
},
"get_options_expirations": {
    "tradier": get_tradier_options_expirations,
},
```

### Pattern 4: Rate Limit Integration with Fallback
**What:** `TradierRateLimitError` integrates into existing `route_to_vendor()` fallback.
**Current issue:** `route_to_vendor()` only catches `AlphaVantageRateLimitError`. It needs to catch a generic rate limit error or both vendor-specific ones.
**Recommendation:** Create a base `VendorRateLimitError` that both `AlphaVantageRateLimitError` and `TradierRateLimitError` inherit from. Update `route_to_vendor()` to catch the base class.

```python
# In a shared module (e.g., tradingagents/dataflows/errors.py or update interface.py)
class VendorRateLimitError(Exception):
    """Base rate limit error for vendor fallback."""
    pass

# In alpha_vantage_common.py:
class AlphaVantageRateLimitError(VendorRateLimitError):
    pass

# In tradier_common.py:
class TradierRateLimitError(VendorRateLimitError):
    pass

# In interface.py route_to_vendor():
except VendorRateLimitError:
    continue  # Fallback to next vendor
```

### Pattern 5: Tool Function for Agents (options_tools.py)
**What:** LangChain `@tool` functions that agents invoke, following `core_stock_tools.py` pattern.
**Example:**
```python
# tradingagents/agents/utils/options_tools.py

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_options_chain(
    symbol: Annotated[str, "ticker symbol of the company"],
    min_dte: Annotated[int, "minimum days to expiration"] = 0,
    max_dte: Annotated[int, "maximum days to expiration"] = 50,
) -> str:
    """
    Retrieve options chain data with Greeks and IV for a given ticker symbol.
    Returns strikes, expirations, bid/ask, volume, OI, Greeks, and IV
    filtered by DTE range.
    """
    return route_to_vendor("get_options_chain", symbol, min_dte, max_dte)
```

### Anti-Patterns to Avoid
- **Per-agent API calls:** D-03 explicitly forbids individual agents making separate API calls. Pre-fetch and cache at analysis start.
- **Assuming standard expiration:** Never compute expiration dates -- always use actual dates from Tradier `/expirations` endpoint (Pitfall 3 from PITFALLS.md).
- **Ignoring Greeks timestamp:** Always propagate `greeks.updated_at` from API response. Downstream agents need staleness detection.
- **Hardcoding base URL:** Must use environment-driven sandbox/production URL switching (D-02).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP auth/request boilerplate | Custom HTTP wrapper | `make_tradier_request()` shared helper | Centralizes auth, base URL, rate limit detection |
| Options expiration date calculation | Date math for "3rd Friday" | Tradier `/expirations` endpoint | Not all options expire on 3rd Friday (weeklies, quarterlies, AM/PM settlement) |
| Rate limit detection | Polling or manual counters | Tradier response headers (`X-Ratelimit-Available`) | API tells you exactly how many requests remain |
| OCC symbol parsing | Regex on symbol strings | Dataclass fields from API response | Tradier returns structured fields (strike, expiration, type) -- no need to parse OCC symbols |

**Key insight:** Tradier's API is well-structured and returns all needed data in structured JSON. The implementation is primarily data mapping (JSON to dataclass/DataFrame), not complex logic.

## Common Pitfalls

### Pitfall 1: Sandbox Has No Greeks Data
**What goes wrong:** The Tradier sandbox environment does not return Greeks data. Tests passing in sandbox may break in production due to different response structure.
**Why it happens:** Sandbox is delayed/simulated data without ORATS Greeks feed.
**How to avoid:** Code must handle `greeks: null` gracefully. Unit tests should mock both with-Greeks and without-Greeks responses. Document that full integration testing requires a production API key.
**Warning signs:** All Greeks fields are None/null in sandbox responses.

### Pitfall 2: Single Contract vs Array Response
**What goes wrong:** When Tradier returns exactly 1 option contract, the `option` field may be a dict instead of a list. Code that always does `response["options"]["option"][0]` will fail.
**Why it happens:** Common JSON API pattern where single-item arrays get collapsed to objects.
**How to avoid:** Normalize the response: if `option` is a dict, wrap it in a list. Check this on every API response parse.
**Warning signs:** `TypeError: string indices must be integers` or similar when processing results for illiquid tickers with few strikes.

### Pitfall 3: Rate Limit Across Multiple Expirations
**What goes wrong:** Fetching chains for a ticker with 8+ expirations means 8+ API calls per ticker. At 120 req/min (production) or 60 req/min (sandbox), analyzing multiple tickers in sequence can exhaust limits quickly.
**Why it happens:** Each expiration requires a separate chain request (Tradier does not support multi-expiration in one call).
**How to avoid:** Pre-fetch only expirations within DTE range (D-04: 0-50 DTE typically yields 3-8 expirations). Track rate limit headers and add backoff when `X-Ratelimit-Available` drops below 10. Cache aggressively within session.
**Warning signs:** HTTP 429 responses or `TradierRateLimitError` in logs.

### Pitfall 4: Null/Missing Fields in Response
**What goes wrong:** Not all options contracts have all fields populated. Illiquid contracts may have `null` for bid, ask, volume, greeks fields.
**Why it happens:** No trading activity = no market data.
**How to avoid:** All dataclass fields that can be null should use `Optional`/`None` defaults. DataFrame should handle NaN gracefully. Filter functions should not crash on missing data.
**Warning signs:** `KeyError` or `TypeError` when processing far-OTM strikes.

### Pitfall 5: Expiration Response Format Varies
**What goes wrong:** When `expirations.date` contains a single date, it may be returned as a string rather than a list.
**Why it happens:** Same single-item array collapsing as Pitfall 2.
**How to avoid:** Always normalize to list: `dates = resp["expirations"]["date"]` then `if isinstance(dates, str): dates = [dates]`.

## Code Examples

### Fetching Expirations with DTE Filter
```python
# Source: Tradier API docs + D-03/D-04 decisions
from datetime import date, datetime

def get_options_expirations(
    symbol: str,
    min_dte: int = 0,
    max_dte: int = 50,
    include_strikes: bool = False,
) -> list[str]:
    """Get options expirations filtered by DTE range."""
    params = {
        "symbol": symbol.upper(),
        "includeAllRoots": "false",
        "strikes": str(include_strikes).lower(),
    }
    data = make_tradier_request("/v1/markets/options/expirations", params)

    dates = data.get("expirations", {}).get("date", [])
    if isinstance(dates, str):
        dates = [dates]

    today = date.today()
    filtered = []
    for d in dates:
        exp_date = datetime.strptime(d, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        if min_dte <= dte <= max_dte:
            filtered.append(d)

    return filtered
```

### Fetching Full Chain for One Expiration
```python
# Source: Tradier API docs + D-05 (always request greeks=true)

def get_chain_for_expiration(symbol: str, expiration: str) -> list[dict]:
    """Fetch options chain for a single expiration date."""
    params = {
        "symbol": symbol.upper(),
        "expiration": expiration,
        "greeks": "true",  # D-05: always include Greeks
    }
    data = make_tradier_request("/v1/markets/options/chains", params)

    options = data.get("options", {}).get("option", [])
    # Pitfall 2: normalize single contract to list
    if isinstance(options, dict):
        options = [options]

    return options
```

### Parsing API Response to Dataclass
```python
# Source: Tradier response structure from API docs

def _parse_contract(raw: dict) -> OptionsContract:
    """Parse Tradier API option dict into typed dataclass."""
    greeks = raw.get("greeks") or {}
    return OptionsContract(
        symbol=raw["symbol"],
        underlying=raw.get("underlying", ""),
        option_type=raw.get("option_type", ""),
        strike=float(raw.get("strike", 0)),
        expiration_date=raw.get("expiration_date", ""),
        bid=float(raw.get("bid", 0) or 0),
        ask=float(raw.get("ask", 0) or 0),
        last=float(raw.get("last", 0) or 0),
        volume=int(raw.get("volume", 0) or 0),
        open_interest=int(raw.get("open_interest", 0) or 0),
        delta=greeks.get("delta"),
        gamma=greeks.get("gamma"),
        theta=greeks.get("theta"),
        vega=greeks.get("vega"),
        rho=greeks.get("rho"),
        phi=greeks.get("phi"),
        bid_iv=greeks.get("bid_iv"),
        mid_iv=greeks.get("mid_iv"),
        ask_iv=greeks.get("ask_iv"),
        smv_vol=greeks.get("smv_vol"),
        greeks_updated_at=greeks.get("updated_at"),
    )
```

### Caching Recommendation (Claude's Discretion)
```python
# Recommendation: In-memory per-session cache using a simple dict.
# Rationale: Fits the existing architecture (no external cache dependencies).
# The session lifetime matches a single propagate() call.
# During development, the cache prevents repeated API calls when re-running.

_options_cache: dict[str, OptionsChain] = {}

def get_cached_chain(symbol: str, min_dte: int, max_dte: int) -> OptionsChain:
    """Get options chain, using session cache if available."""
    cache_key = f"{symbol}:{min_dte}:{max_dte}"
    if cache_key in _options_cache:
        return _options_cache[cache_key]

    chain = _fetch_full_chain(symbol, min_dte, max_dte)
    _options_cache[cache_key] = chain
    return chain

def clear_options_cache():
    """Clear the session cache. Call at start of each propagate() run."""
    _options_cache.clear()
```

### Rate Limit Handling Recommendation (Claude's Discretion)
```python
# Recommendation: Combine pre-emptive throttling (check headers) with retry+backoff.
# Rationale: The existing AlphaVantageRateLimitError only triggers fallback.
# For Tradier (the only options vendor), fallback has nowhere to go.
# So we need retry logic in addition to the error class.

import time

def make_tradier_request_with_retry(
    path: str, params: dict | None = None, max_retries: int = 3
) -> dict:
    """Tradier request with rate limit awareness and retry."""
    for attempt in range(max_retries):
        try:
            return make_tradier_request(path, params)
        except TradierRateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait)
            else:
                raise
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tradier XML responses | JSON responses (default) | Years ago | Always use `Accept: application/json` header |
| Per-request API key param | Bearer token auth | Current standard | Use `Authorization: Bearer {key}` header |
| Manual Greeks calculation | ORATS-sourced Greeks via API | Current | No need to calculate 1st-order Greeks; rely on Tradier |

**Deprecated/outdated:**
- Tradier documentation URLs moved from `documentation.tradier.com` to `docs.tradier.com` (308 redirect in place)

## Open Questions

1. **Sandbox Greek behavior**
   - What we know: CONTEXT.md notes "Sandbox has no Greeks -- production account required for full testing"
   - What is unclear: Exact response structure when Greeks are absent (null object? missing key? empty object?)
   - Recommendation: Test in sandbox during implementation, document the exact behavior, ensure code handles both cases

2. **Historical IV endpoint for IV Rank**
   - What we know: STATE.md flags "Historical IV data endpoint for IV Rank (52-week history) needs validation during Phase 1/3 planning"
   - What is unclear: Whether Tradier provides historical IV data or only current snapshot
   - Recommendation: This is a Phase 3 concern (VOL-01/VOL-02). Phase 1 only needs current Greeks/IV. Defer investigation.

3. **Tradier response when market is closed**
   - What we know: API should still return last-known data
   - What is unclear: Whether Greeks are zeroed out or stale during off-hours
   - Recommendation: Test during implementation, propagate `greeks_updated_at` timestamp for staleness detection

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.13.12 (venv) | -- |
| uv | Package management | Yes | 0.11.2 | -- |
| requests | Tradier HTTP calls | Yes | In pyproject.toml | -- |
| pandas | DataFrame output | Yes | In pyproject.toml | -- |
| Tradier API key | All API calls | Unknown | -- | Sandbox key free at developer.tradier.com |

**Missing dependencies with no fallback:**
- `TRADIER_API_KEY` env var must be set. Free sandbox key available at developer.tradier.com.

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | **pytest** (>=8) — Phase 1 adds `tests/unit/data/test_tradier.py` and `pytest` dev dependency; existing `tests/test_ticker_symbol_handling.py` may remain unittest-style until migrated. |
| Config file | **None in Wave 0** — no `pytest.ini`/`pyproject` test section required for initial Tradier tests; add later if markers/fixtures grow. |
| Quick run command | `uv run python -m pytest tests/unit/data/test_tradier.py -x --timeout=10` |
| Full suite command | `uv run python -m pytest tests/ --timeout=30` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Retrieve full options chain (strikes, exps, bid/ask, vol, OI) | unit (mock / vcr) | `uv run python -m pytest tests/unit/data/test_tradier.py::TestGetOptionsChain -x` | No -- Wave 0 |
| DATA-02 | Retrieve expirations and strikes for any ticker | unit (mock / vcr) | `uv run python -m pytest tests/unit/data/test_tradier.py::TestGetExpirations -x` | No -- Wave 0 |
| DATA-03 | 1st-order Greeks displayed per contract with timestamp | unit (mock / vcr) | `uv run python -m pytest tests/unit/data/test_tradier.py::TestGreeksPresent -x` | No -- Wave 0 |
| DATA-04 | IV per contract (bid_iv, mid_iv, ask_iv, smv_vol) | unit (mock / vcr) | `uv run python -m pytest tests/unit/data/test_tradier.py::TestIVPresent -x` | No -- Wave 0 |
| DATA-05 | Filter options chain by DTE range | unit | `uv run python -m pytest tests/unit/data/test_tradier.py::TestDTEFilter -x` | No -- Wave 0 |
| DATA-06 | (Phase 2) 2nd-order Greeks — not validated in Phase 1 | — | — | N/A |
| DATA-07 | (Phase 10) Tastytrade streaming — not validated in Phase 1 | — | — | N/A |
| DATA-08 | Tradier registered in vendor routing layer | unit | `uv run python -m pytest tests/unit/data/test_tradier.py::TestVendorRegistration -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/unit/data/test_tradier.py -x --timeout=10`
- **Per wave merge:** `uv run python -m pytest tests/ --timeout=30`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/data/test_tradier.py` -- covers DATA-01 through DATA-05, DATA-08 (Tier 2 data layer; prefer **vcrpy** cassettes under `tests/fixtures/cassettes/tradier/` for realistic HTTP replay)
- [ ] `tests/conftest.py` (repo root or `tests/unit/data/`) -- shared fixtures + VCR configuration
- [ ] Install pytest: `uv add --dev pytest>=8.0` and `uv add --dev vcrpy` (or pytest-vcr) when enabling cassettes

## Project Constraints (from CLAUDE.md)

- **Python >=3.11**, consistent with `pyproject.toml` and Tastytrade SDK (Phase 10)
- **snake_case.py** for all module names, no hyphens
- **Factory functions** use `create_` prefix; getter functions use `get_` prefix
- **`requests`** for HTTP calls (no new HTTP client dependency)
- **Error handling:** Return error strings from data-fetching tool functions (LLM context); raise `ValueError` for programming errors
- **`@tool` docstrings** are LLM-readable descriptions (LangChain convention)
- **Config pattern:** Module-level `_config` dict with `get_config()`/`set_config()`
- **No automated formatter/linter** configured -- match existing style manually
- **`__all__` lists** in key `__init__.py` files for controlled exports
- **LLM provider agnostic:** Options agents must work with any supported LLM provider via the client factory

## Sources

### Primary (HIGH confidence)
- [Tradier Options Chains API](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains) -- endpoint, params, response fields verified
- [Tradier Options Expirations API](https://docs.tradier.com/reference/brokerage-api-markets-get-options-expirations) -- endpoint, params, response fields verified
- [Tradier Options Strikes API](https://docs.tradier.com/reference/brokerage-api-markets-get-options-strikes) -- endpoint, params verified
- [Tradier Rate Limiting](https://docs.tradier.com/docs/rate-limiting) -- 120 req/min production, 60 req/min sandbox, response headers verified
- Existing codebase: `interface.py`, `y_finance.py`, `alpha_vantage_common.py`, `core_stock_tools.py` -- pattern analysis

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` -- stack recommendations cross-referenced with official docs
- `.planning/research/PITFALLS.md` -- domain pitfalls cross-referenced with Tradier docs

### Tertiary (LOW confidence)
- Sandbox Greeks behavior -- noted in CONTEXT.md but unverified empirically

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, Tradier API docs verified
- Architecture: HIGH -- patterns directly derived from reading existing codebase
- Pitfalls: HIGH -- documented from Tradier API docs + domain research + existing project pitfalls doc

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (30 days -- Tradier API is stable)
