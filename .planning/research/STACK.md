# Technology Stack

**Project:** TradingAgents Options Trading Module
**Researched:** 2026-03-29

## Recommended Stack

### Options Data Providers

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **Tradier REST API** (direct `requests`) | N/A (REST) | Options chains, strikes, expirations, 1st-order Greeks, IV | Returns delta/gamma/theta/vega/rho/phi + bid_iv/mid_iv/ask_iv/smv_vol via ORATS. Free sandbox. No SDK needed -- simple REST with `requests` (already a dependency). Hourly Greeks refresh is sufficient for batch analysis. | HIGH |
| **tastytrade** (tastyware community SDK) | >=12.3.1 | Real-time streaming Greeks, live quotes via DXLink WebSocket | Official `tastytrade-sdk-python` was archived March 2026. The `tastyware/tastytrade` community SDK is the de facto standard: 95%+ test coverage, full typing with Pydantic, async DXLink WebSocket streaming. Requires Python >=3.11 (project venv is 3.13, so no issue). | HIGH |

**Data provider strategy:** Tradier is the primary REST data source (chains, expirations, ORATS Greeks). Tastytrade is the streaming supplement for real-time Greeks updates. Both fit the existing vendor-routing pattern in `tradingagents/dataflows/`.

**API keys required:**
- `TRADIER_API_KEY` -- free sandbox at developer.tradier.com, production requires brokerage account
- `TASTYTRADE_USERNAME` / `TASTYTRADE_PASSWORD` -- requires tastytrade account (free to create)

### Greeks and Pricing Calculation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **blackscholes** | >=0.2.0 | 1st, 2nd, and 3rd order Greeks (Charm, Vanna, Volga/Vomma) | Actively maintained (Dec 2024 release), Python >=3.8, supports BSM + Black-76, up to 3rd-order Greeks out of the box. Lightweight, no heavy C dependencies. Covers the gap where Tradier API only provides 1st-order Greeks. | HIGH |
| **scipy** (optimize) | >=1.14.0 | IV solver (Brent's method), SVI curve fitting (least squares) | Already an indirect dependency via pandas/numpy ecosystem. `scipy.optimize.brentq` for IV root-finding, `scipy.optimize.minimize` for SVI parameter calibration. Battle-tested numerical methods. | HIGH |
| **numpy** | >=2.0.0 | Vectorized Greeks computation, GEX aggregation across strikes | Already an indirect dependency. All Greeks math and exposure aggregation should be vectorized with numpy for performance across full options chains (hundreds of strikes). | HIGH |

**Not recommended:**
- **py_vollib** (v1.0.1, last release 2017) -- effectively abandoned. The `blackscholes` package is newer, actively maintained, and covers more Greeks.
- **py-vollib-vectorized** (v0.1.1, last release 2021) -- depends on abandoned py_vollib, not maintained.
- **mibian** -- undocumented, minimal maintenance, limited to basic Greeks. `blackscholes` is strictly better.
- **QuantLib** (v1.41) -- massively over-engineered for this use case. 200+ MB compiled binary, complex C++ binding. Justified for interest rate derivatives or exotic options, not for equity options Greeks in an LLM agent pipeline. The vol surface modeling via SVI can be done with scipy alone.

### Volatility Surface Modeling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **scipy.optimize** | >=1.14.0 | SVI model calibration (5 params: a, b, rho, m, sigma) | SVI (Stochastic Volatility Inspired) is the industry standard for equity options vol smile fitting. Calibration is a nonlinear least-squares problem -- `scipy.optimize.minimize` with SLSQP or L-BFGS-B handles it well. No dedicated library needed. | MEDIUM |
| **scipy.interpolate** | >=1.14.0 | Interpolation across strikes/expirations for smooth vol surface | `RectBivariateSpline` or `griddata` for 2D interpolation across the (strike, expiration) grid. Standard approach when parametric SVI is overkill for some expirations. | HIGH |
| **matplotlib** | >=3.9.0 | Vol surface visualization (3D plots, heatmaps) | For debugging and analysis output. Optional -- only needed if generating visual reports. | HIGH |

**Approach:** Use SVI parametric fitting per-expiration to construct the volatility smile, then interpolate across expirations to build the full surface. This is the standard approach used in practice (confirmed by multiple 2025 implementations and academic comparisons).

**Not recommended:**
- **SABR model** -- better suited for interest rate derivatives. For equity options with discrete strikes and limited expirations, SVI is simpler and equally accurate. A 2025 thesis comparing SVI vs SABR on SPY/QQQ found comparable performance with SVI being easier to calibrate.

### Gamma Exposure (GEX) Computation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **numpy** | >=2.0.0 | Vectorized GEX calculation across all strikes/expirations | GEX formula is straightforward: `GEX_per_strike = Gamma * OI * 100 * Spot^2 * 0.01`, then `Net_GEX = sum(Call_GEX) - sum(Put_GEX)`. Pure numpy vectorization handles the full chain in microseconds. | HIGH |
| **pandas** | >=2.3.0 | Structuring GEX output (strike-level breakdown, flip zones, walls) | Already a core dependency. GEX output is naturally tabular: per-strike gamma, cumulative GEX, call/put walls, flip zones. | HIGH |

**No external library needed.** GEX computation is arithmetic on options chain data. The SpotGamma methodology is documented:
- Net GEX across strikes identifies gamma walls (high absolute GEX = support/resistance)
- Sign flip in cumulative GEX identifies the "Vol Trigger" / gamma flip zone
- Call Wall = strike with max positive call gamma exposure
- Put Wall = strike with max negative put gamma exposure

The complexity is in interpretation (which the LLM agent handles), not computation.

### Options Flow / Unusual Activity Detection

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **pandas** | >=2.3.0 | Volume/OI ratio analysis, sweep/block classification | Flow detection is data filtering: volume > threshold, volume/OI ratio > 1.25, relative volume vs historical average. Pure pandas operations. | HIGH |
| **Tradier API** (historical options) | N/A | Historical volume/OI baselines for relative volume calculation | Tradier provides historical options data to establish baselines. Without baselines, "unusual" has no reference point. | MEDIUM |

**Detection heuristics (no library needed):**
- Unusual activity: `volume / avg_daily_volume > 2.0` AND `volume / open_interest > 1.25`
- New position signal: `volume >> open_interest` (new positions being opened)
- Smart money proxy: large block trades (>100 contracts), sweeps across exchanges
- Put/call volume ratio spikes relative to historical norm

**Limitation:** Tradier's market data API does not provide trade-level data (individual fills, sweep detection). True sweep/block detection requires Level 2 or trade-by-trade data. The module should classify by volume patterns rather than individual trade types. Flag this as a known limitation.

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| **pydantic** | >=2.0 | Data models for options chain, Greeks, GEX output | Already an indirect dependency (via tastytrade SDK, LangChain). Use for typed data structures in the options module. | HIGH |
| **httpx** | >=0.27.0 | Async HTTP client for Tradier API | If async Tradier calls are needed alongside tastytrade's async DXLink. Otherwise `requests` (already a dependency) suffices for sync calls. | LOW |
| **python-dateutil** | >=2.9.0 | Options expiration date calculations (3rd Friday, weeklies) | Parsing and computing DTE, expiration cycles. Likely already an indirect dependency. | HIGH |

## Python Version Consideration

The project declares `requires-python = ">=3.10"` but the development venv runs Python 3.13. The tastytrade SDK requires `>=3.11`. Two options:

1. **Recommended:** Bump `requires-python` to `>=3.11` when adding the options module. This unlocks the tastytrade SDK and latest numpy/scipy without constraints.
2. **Alternative:** Keep `>=3.10` and make tastytrade an optional dependency. Tradier alone covers the core use case.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Greeks calculation | blackscholes | py_vollib | Abandoned since 2017, no 2nd/3rd order Greeks |
| Greeks calculation | blackscholes | QuantLib | 200MB+ binary, C++ dependency, massive overkill for equity options |
| Greeks calculation | blackscholes | mibian | Minimal maintenance, no typing, limited Greek support |
| Vol surface | scipy SVI fitting | QuantLib SviInterpolatedSmileSection | QuantLib dependency not justified for SVI alone |
| Vol surface model | SVI | SABR | SABR better for rates; SVI simpler and equally accurate for equities |
| Tradier SDK | Direct requests | uvatradier | Thin wrapper adds dependency without meaningful abstraction; Tradier REST API is 3 endpoints |
| Tradier SDK | Direct requests | lumiwealth-tradier | Same reasoning; direct requests with typed response models is cleaner |
| Tastytrade SDK | tastyware/tastytrade | tastytrade-sdk (official) | Official SDK archived March 2026; community SDK is the maintained option |
| IV calculation | scipy.optimize.brentq | py_vollib LetsBeRational | LetsBeRational is faster but py_vollib is abandoned; scipy is reliable and already available |
| GEX computation | numpy (custom) | No alternative | No established GEX library exists; the math is simple enough for custom implementation |

## Installation

```bash
# Core options dependencies (new)
uv add blackscholes>=0.2.0 tastytrade>=12.3.1 matplotlib>=3.9.0

# Already present in project (no action needed)
# requests, pandas, numpy (indirect), scipy (indirect), pydantic (indirect)
```

**Environment variables to add to `.env.example`:**
```bash
# Options data providers
TRADIER_API_KEY=your_tradier_api_key      # Get free sandbox key at developer.tradier.com
TRADIER_ENVIRONMENT=sandbox               # "sandbox" or "production"
TASTYTRADE_USERNAME=your_tastytrade_user   # Required for streaming Greeks
TASTYTRADE_PASSWORD=your_tastytrade_pass
```

## Architecture Integration Notes

1. **Tradier fits the existing vendor pattern.** Create `tradingagents/dataflows/tradier.py` alongside `y_finance.py` and `alpha_vantage.py`. Same interface contract: function takes ticker + params, returns pandas DataFrame.

2. **Tastytrade streaming is optional.** The batch analysis flow (`propagate()`) works fine with Tradier's hourly-refreshed Greeks. Tastytrade DXLink streaming is an enhancement for scenarios needing fresher data.

3. **blackscholes is computation-only.** No API calls, no state. Use it in agent tool functions to compute 2nd-order Greeks from Tradier's 1st-order data + underlying price.

4. **GEX and flow detection are pure pandas/numpy.** No external dependencies beyond what's already in the project. These are custom computations wrapped as agent tools.

## Sources

- [Tradier Options Chain API docs](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains) -- HIGH confidence, official docs
- [tastyware/tastytrade SDK](https://github.com/tastyware/tastytrade) -- HIGH confidence, actively maintained community SDK (v12.3.1, Mar 2026)
- [tastytrade-sdk-python archived](https://github.com/tastytrade/tastytrade-sdk-python) -- HIGH confidence, archived Mar 2026
- [blackscholes package](https://github.com/CarloLepelaars/blackscholes) -- HIGH confidence, v0.2.0 Dec 2024, supports 3rd-order Greeks
- [py_vollib on PyPI](https://pypi.org/project/py_vollib/) -- HIGH confidence, v1.0.1 last released 2017
- [QuantLib-Python v1.41](https://quantlib-python-docs.readthedocs.io/en/latest/termstructures/volatility.html) -- HIGH confidence, official docs
- [SpotGamma GEX methodology](https://spotgamma.com/gamma-exposure-gex/) -- MEDIUM confidence, proprietary methodology with published formulas
- [SVI vs SABR comparison (2025 thesis)](https://repositori.upf.edu/items/eceeb187-f169-483e-bf67-416fd9e00d70) -- MEDIUM confidence, academic source
- [SVI fitting with Python](https://tradingtechai.medium.com/python-volatility-surface-modeling-data-fetching-iv-calculation-svi-fitting-and-visualization-80be58328ac6) -- LOW confidence, blog post but methodology is standard
- [NumPy 2.4.x release](https://numpy.org/news/) -- HIGH confidence, official
- [SciPy 1.17.x release](https://docs.scipy.org/doc/scipy/release.html) -- HIGH confidence, official
