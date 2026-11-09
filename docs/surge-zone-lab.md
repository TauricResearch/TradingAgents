# Surge Zone Lab — first vertical slice

Read the [architecture audit and roadmap](surge-zone-lab-audit.md) for integration
points and subsequent increments. This slice is deliberately independent of the
TradingAgents CLI, graph, memory and vendor defaults.

## Windows / VS Code / PowerShell

Open this repository folder in VS Code. In its PowerShell terminal (Python 3.11+):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,surge]"
# If absent, copy .env.example to .env; keep existing .env credentials otherwise.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env locally: EODHD_API_TOKEN=<your own token>
.\.venv\Scripts\python.exe -m streamlit run tradingagents/surge/app.py
```

Select `.venv\Scripts\python.exe` via **Python: Select Interpreter** in VS Code.
No activation or PowerShell execution-policy change is needed. A token with daily
US price access is required for downloads. SPY.US, QQQ.US, AAPL.US and NVDA.US use
the same endpoint. Cached results require no network until TTL expiry (six hours)
or explicit refresh. Each scan/refresh uses one API request. A 401/402/403/429 stops
without retries; check account limits before retrying. No automatic provider fallback.
Request spacing is per client instance, not an account-wide quota coordinator.

If an older pip fails certificate verification on Windows, upgrade it with the
system trust store before retrying installation:

```powershell
.\.venv\Scripts\python.exe -m pip install --use-feature=truststore --upgrade pip
```

Do not disable certificate verification. The optional dashboard requires Streamlit
1.67+; its installed documentation and agent API were used for local verification.

Daily sessions use XNYS close timestamps in UTC, including holidays, DST and early
closes. Only completed bars enter detection; completion is not proof of vendor
publication at that moment. Missing sessions remain missing and block crossing
patterns. Provenance displays retrieval and last completed bar; these are historical
or delayed prices, never a live feed. API responses with invalid OHLCV are rejected.

Raw OHLCV is retained alongside vendor adjusted_close. Adjustment-factor jumps over
0.1% flag potential splits/dividends and block pattern context; small adjustments
and all revisions cannot be certified. Refresh replaces the entire requested snapshot
to avoid combining inconsistent price scales. This is TTL snapshot caching, not
incremental downloading. Data licensing/redistribution depends on your EODHD plan.

## Experimental detector

The four labels are incoming direction + compact base + departing direction:
RBR/DBR = Demand; RBD/DBD = Supply. The incoming and departing single candles must
meet configured body/ATR and body/range thresholds. ATR uses only earlier bars.
Base body fractions, total base range and base count are configurable. When nested
bases share a departure, choose the longest qualifying base. Departure must close
outside the base. Confirmation occurs at that bar's close. A gap or adjustment
break resets warmup and excludes crossing contexts. The engine accepts an aware
`as_of` cutoff and yields identical formations on every matching historical prefix.

**Reference Cards 1 and 2 (20260501) have now been reviewed.** See the
[rule mapping and remaining ambiguities](surge-reference-rules.md). Proximal uses
the documented base body-edge option. Reversal distal boundaries include incoming
leg, base, and departing leg; continuation distal boundaries include base and
departing leg. Demand takes the low and supply the high. These formulas are applied
to the detector's experimental single-candle leg spans, not certified segmentation.

The scorecard implements the six documented bands, including half points. Automatic
evidence currently covers only Time (base count); the dashboard shows earned points
and evaluated maximum separately. Missing components remain unscored. `official_score`
stays null and partial scores never receive entry guidance. Complete externally
verified evidence can be scored using `surge/scorecard.py`; proximal guidance begins
at 8.5, confirmation at 7, and scores below 7 give no-trade guidance. Scores are not
probabilities. BOS remains an experimental trailing-window break and is not used
as the official breakout evidence; FVG is not an extra scoring criterion.

Replay truncates bars before recomputing detection. The chart marks incoming leg,
base region and confirmation. Zone rectangles start at confirmation, not before
the zone was knowable. `confirmed; lifecycle not evaluated` explicitly does not
claim a zone is fresh, active, visited or unbroken today.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_surge_engine.py tests/test_surge_eodhd.py tests/test_surge_chart.py tests/test_surge_app.py tests/test_surge_scorecard.py -q
.\.venv\Scripts\python.exe -m ruff check tradingagents/surge tradingagents/dataflows/vendors/eodhd.py tests/test_surge_*.py
```

No API credentials or paid requests are needed for mocked tests. Optional-extra
tests skip when their dependencies are absent, preserving the base installation.
See `surge-zone-lab-validation.md` for the actual local execution results.

## Remaining work

Intraday/resampling and incremental revision-aware caching are pending. So are
verified full-pattern segmentation and automated context scoring, visits/invalidation, entry/stop/target outcome
simulation (including OHLC ambiguity), trade journal/fills/fees, ML, comparable-case
statistics, the full eight-page dashboard and opt-in LLM integration. There are no
Create Trade buttons until the journal can validate, edit and persist a proposal.
No live orders, claims of backtested performance, or changes to production trading.

Provider contract references: [EODHD daily API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes),
[intraday API for the next increment](https://eodhd.com/financial-apis/intraday-historical-data-api).
UI references: [Streamlit forms](https://docs.streamlit.io/develop/api-reference/execution-flow/st.form)
and [Plotly charts](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart).
