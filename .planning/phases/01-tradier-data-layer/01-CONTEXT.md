# Phase 1: Tradier Data Layer - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrate Tradier as a new data vendor for options chain retrieval with 1st-order Greeks and IV. Register options-specific tools and categories in the existing vendor routing system. Provide filtered, structured chain data for downstream options analysis agents.

</domain>

<decisions>
## Implementation Decisions

### API Authentication
- **D-01:** Use `TRADIER_API_KEY` env var for credentials, matching existing pattern (`OPENAI_API_KEY`, `ALPHA_VANTAGE_KEY`)
- **D-02:** Support sandbox via `TRADIER_SANDBOX=true` env var — auto-detect base URL (`sandbox.tradier.com` vs `api.tradier.com`)

### Data Fetching Strategy
- **D-03:** Pre-fetch all expirations within DTE range upfront at the start of an analysis run, cache for the session. Do NOT let individual agents make separate API calls for the same data.
- **D-04:** Default DTE filter range: 0-50 DTE (covers TastyTrade's 30-50 sweet spot plus weeklies and near-term options)
- **D-05:** Always request `greeks=true` from Tradier — there's no reason to skip Greeks when the whole point is options analysis

### Data Structure
- **D-06:** Dual output format: Pandas DataFrame for bulk operations (consistent with existing yfinance pattern) AND typed dataclass (`OptionsContract`, `OptionsChain`) for individual contract access by downstream agents

### Claude's Discretion
- **Caching strategy:** Claude picks the best caching approach. In-memory per-session is simpler; disk TTL helps during development. Choose based on what fits the existing architecture best.
- **Rate limit handling:** Claude picks the best approach based on existing `AlphaVantageRateLimitError` fallback pattern. Options include retry with backoff, pre-emptive throttling, or both.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Data Layer (follow these patterns)
- `tradingagents/dataflows/interface.py` — Vendor routing system: `TOOLS_CATEGORIES`, `VENDOR_METHODS`, `VENDOR_LIST`, `route_to_vendor()`
- `tradingagents/dataflows/config.py` — Config module pattern for vendor settings
- `tradingagents/default_config.py` — Default config with `data_vendors` and `tool_vendors` dicts
- `tradingagents/dataflows/y_finance.py` — Reference implementation for a data vendor module
- `tradingagents/dataflows/alpha_vantage.py` — Second vendor reference with rate limit error handling

### Tradier API
- `https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains` — Options chains endpoint
- `https://docs.tradier.com/reference/brokerage-api-markets-get-options-expirations` — Expirations endpoint
- `https://docs.tradier.com/reference/brokerage-api-markets-get-options-strikes` — Strikes endpoint
- `https://docs.tradier.com/docs/rate-limiting` — Rate limiting (120 req/min for market data)

### Project Research
- `.planning/research/STACK.md` — Stack recommendations including Tradier integration approach
- `.planning/research/PITFALLS.md` — Data quality pitfalls (stale Greeks, hourly update frequency)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `interface.py::route_to_vendor()` — Vendor routing with automatic fallback on rate limit errors
- `interface.py::TOOLS_CATEGORIES` — Tool category registration pattern (add new `options_chain` category)
- `interface.py::VENDOR_METHODS` — Method-to-vendor mapping (add new options methods)
- `config.py` — Config management with `get_config()`, `set_config()` pattern
- `AlphaVantageRateLimitError` — Rate limit error pattern to replicate for Tradier

### Established Patterns
- **Vendor module:** One Python file per vendor (`y_finance.py`, `alpha_vantage.py`) with exported functions
- **Function naming:** `get_*` prefix for data retrieval (`get_stock_data`, `get_fundamentals`)
- **Config:** Category-level defaults in `data_vendors` dict, tool-level overrides in `tool_vendors`
- **No SDK dependency:** Use `requests` directly for Tradier (consistent with keeping deps lean)

### Integration Points
- `interface.py` — Register new `options_chain` category in `TOOLS_CATEGORIES`, add `"tradier"` to `VENDOR_LIST`, add options methods to `VENDOR_METHODS`
- `default_config.py` — Add `"options_chain": "tradier"` to `data_vendors`
- `tradingagents/agents/utils/` — New tool functions for options data (like `core_stock_tools.py` pattern)

</code_context>

<specifics>
## Specific Ideas

- Tradier OCC symbology format: `AAPL220617C00270000` (symbol + date + C/P + strike*1000)
- Greeks fields from Tradier: `delta`, `gamma`, `theta`, `vega`, `rho`, `phi`, `bid_iv`, `mid_iv`, `ask_iv`, `smv_vol`
- Response format: `{"data": {"options": {"option": [...]}}}` — nested JSON requiring extraction
- Sandbox has no Greeks — production account required for full testing

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-tradier-data-layer*
*Context gathered: 2026-03-29*
