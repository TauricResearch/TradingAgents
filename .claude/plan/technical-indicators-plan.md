# Technical Indicators: Registry, Fixes, New Indicators, Params

## Context

The market analyst LLM picks up to 8 indicators from a hardcoded menu of 14 (3 MAs, 3 MACD lines, RSI, 3 Bollinger lines, ATR, VWMA, plus custom multi-timeframe TD-9 and z-score). Review found four problems:

1. **Triplicated metadata** — indicator names/descriptions are hand-synced across `market_analyst.py:27-53`, `y_finance.py:65-146` (`best_ind_params`), and `alpha_vantage_indicator.py:30-58`. Every new indicator is a three-file edit.
2. **MFI half-wired** — described in `y_finance.py:131` but absent from the analyst prompt, snapshot, and AV vendor. Also stockstats `mfi` outputs **0–1**, not the conventional 0–100 the description claims (verified live).
3. **AV fallback short-circuit bug** — `alpha_vantage_indicator.py:148` (vwma) and `:150` (catch-all) **return** prose instead of raising, so `route_to_vendor` (`interface.py:161`) treats it as success and never falls back to yfinance.
4. **No parameterization** — all windows hardcoded (RSI 14, Boll 20/2σ, ATR 14...).

User approved all four tracks plus new indicators (ADX/DMI, volume flow, stochastic, one new custom multi-timeframe) and asked whether other indicator vendors can be connected.

**Verified against installed stockstats 0.6.5** (live-tested via `.venv/bin/python`):
- Native: `mfi` (0–1 scale!), `adx` (fixed EMA-6-of-DX-14; **not** parameterizable, `adx_14` fails), `pdi`/`ndi` (**no `mdi`** — raises UserWarning), `kdjk`/`kdjd`/`kdjj` (9), `stochrsi` (14), `supertrend`/`supertrend_ub`/`supertrend_lb` (14, mult 3), `high_252_max`.
- Param naming: `rsi_7`, `close_20_sma`, `atr_21`, `vwma_20`, `mfi_10`, `kdjk_14`, `stochrsi_21`, `supertrend_10` all work; `boll_30` → **`boll_ub_30`/`boll_lb_30`** (suffix asymmetry vs default `boll_ub`); MACD only via comma form — defer.
- Not native: OBV, CMF, Donchian.
- OHLCV cache stores raw prices only; indicators always recomputed → no cache migration needed.

## Phase 1 — Single indicator registry (foundation)

**Create `tradingagents/dataflows/indicator_registry.py`:**
- `@dataclass(frozen=True) IndicatorSpec`: `name`, `category`, `description` (lifted **verbatim** from `y_finance.py:65-146`), `stockstats_column` (None for custom), `column_template` (e.g. `"rsi_{window}"`, None if not parameterizable), `default_params`, `custom` (None | `"td_9"` | `"z_score"` | later additions), `av_function`/`av_column`/`av_extra_params` (None = AV-unsupported), `scale` (default 1.0), `in_snapshot` (bool).
- `INDICATORS: dict[str, IndicatorSpec]` in current prompt order; helpers `get_spec`, `supported_names`, `snapshot_indicators`, `render_prompt_section()` (regenerates `market_analyst.py:27-53` byte-identically), `resolve_column(name, params)` (Phase 4 hook).

**Modify:**
- `tradingagents/dataflows/y_finance.py` — drop `best_ind_params`; validate/describe via registry; dispatch td_9/z_score on `spec.custom`; `_get_stock_stats_bulk` computes `spec.stockstats_column`.
- `tradingagents/dataflows/alpha_vantage_indicator.py` — drop its description/supported dicts; supported = `spec.av_function is not None`; CSV column from `spec.av_column` (replaces `col_name_map` at lines 165-170).
- `tradingagents/agents/analysts/market_analyst.py` — splice `render_prompt_section()` into the system message (plain concatenation, like `get_language_instruction()`); keep surrounding instructions verbatim.
- `tradingagents/dataflows/market_data_validator.py` — `DEFAULT_SNAPSHOT_INDICATORS = indicator_registry.snapshot_indicators()` (keep the module-level name).

**Tests** (`tests/test_indicator_registry.py`): golden string-equality test of `render_prompt_section()` vs the old hardcoded prompt block (anti-drift contract); every non-custom name computes through `get_stock_stats_indicators_window` with monkeypatched `load_ohlcv`; same description from both vendor paths; unknown name raises `ValueError`; prompt section contains no `{`/`}` braces.

## Phase 2 — MFI wiring + AV fallback fix

- Registry: `mfi` → `scale=100.0`, `in_snapshot=True`, `av_function="MFI"`; fix its description (0–100 after rescale). Apply `spec.scale` in **both** `_get_stock_stats_bulk` and the `build_verified_market_snapshot` loop (`market_data_validator.py:77-82`) so tool and ground truth agree.
- `alpha_vantage_indicator.py`: add `MFI` request branch (mirror RSI branch at lines 122-129). Replace the vwma string-return (line 148) and the `"not implemented yet"` return (line 150) with one up-front `if spec.av_function is None: raise ValueError(...)` — restores the fallback chain (pattern already codified in `tests/test_zscore.py::TestAlphaVantageFallback`).
- MFI enters the analyst prompt automatically via the registry.

**Tests** (`tests/test_mfi_and_vendor_gaps.py`): MFI manual-formula ×100 check; snapshot has 0–100 `mfi` row; AV `vwma` raises `ValueError`; end-to-end `route_to_vendor` with AV-primary returns yfinance values for vwma (copy config save/restore from `test_zscore.py:157-178`); loop over all registry names asserting AV either requests (mocked) or raises — never returns prose.

## Phase 3 — New indicators

**Native (registry entries only):**
- `adx` (AV `ADX`; Tips must note stockstats's EMA-6-of-DX-14 differs from Wilder's classic 14/14, so values won't match TradingView exactly; not parameterizable).
- `pdi` (AV `PLUS_DI`) and agent-facing **`mdi` mapped to stockstats column `ndi`** (AV `MINUS_DI`) — the name→column indirection exists for this.
- `kdjk`/`kdjd`/`kdjj` (AV-unsupported — AV STOCH smoothing differs numerically; let fallback handle it).
- `stochrsi` (AV `STOCHRSI`, column `FastK`) — prompt line 55 already anticipates the name.

**Custom (in `tradingagents/dataflows/stockstats_utils.py`):**
- `obv`: `(sign(close.diff()) * volume).cumsum()`, rendered through the existing daily `date: value` window format (not tiered). AV `OBV`.
- `supertrend` — the new multi-timeframe custom, tiered weekly > monthly > daily like td_9/z_score. stockstats computes it natively, so the custom part is only OHLC resampling (open first / high max / low min / close last) + formatting, mirroring `td_setup_by_timeframe` and `format_td_setup_block`. Returns per-tier `{direction, supertrend_level, distance_pct}` — adds a concrete trailing-stop level orthogonal to td_9 (exhaustion) and z_score (stretch).
- **CMF: skip** (no stockstats support; near-duplicate of properly-wired MFI). Donchian/52-wk-high deferred (`high_252_max` makes the latter a one-line registry add later).
- Dispatch via `spec.custom` in `get_stock_stats_indicators_window` (same shape as td_9/z_score branches at `y_finance.py:150-157`).

**Prompt budget:** ~24 entries; keep "up to 8" and add one guidance sentence (≤1-2 per category; prefer one each of trend/momentum/volatility/volume/exhaustion). Do not abbreviate existing descriptions.
**Snapshot:** append `mfi`, `adx`, `kdjk` (append-only; existing validator tests assert substrings — safe).

**Tests**: `tests/test_supertrend_mtf.py` (mirror `test_td_sequential.py`: monotonic-up → direction up / level below close on all tiers; down → opposite) and `tests/test_new_indicators.py` (OBV manual cumsum; adx/pdi/mdi/kdj/stochrsi smoke via monkeypatched `load_ohlcv`; `mdi` resolves to `ndi` values; AV raises for kdj*/supertrend).

## Phase 4 — Parameterizable windows

- `tradingagents/default_config.py`: add `"indicator_params": {}` (comment example: `{"rsi": {"window": 7}}`). One-level-deep `set_config` merge already composes.
- `resolve_column(name, params)`: defaults → bare legacy column (`rsi`, `boll_ub`) for byte-identical unconfigured behavior; overrides → template (`rsi_{window}`...), with the Bollinger `boll_ub_{n}` asymmetry handled **only here**. Non-parameterizable: `adx`, `macd*` (defer), `td_9`. `z_score` already accepts `window=`.
- Both `y_finance.py` and `market_data_validator.py` resolve through the registry (tool output and verified snapshot must stay numerically identical). Report header shows effective params (`## rsi (window=7) ...`).
- AV: pass resolved window as `time_period` where supported. `get_indicators` tool signature unchanged; canonical names stable.

**Tests** (`tests/test_indicator_params.py`): rsi window=7 ≠ default and matches direct `rsi_7`; boll override → `boll_ub_30`; empty config → exact legacy columns; snapshot respects overrides.

## Phase 5 — Vendor question (answer, no code by default)

Yes — pluggable: new vendor = one module exposing `get_indicator(symbol, indicator, curr_date, look_back_days)` + entries in `VENDOR_METHODS`/`VENDOR_LIST` (`interface.py:64-111`); fallback/rate-limit/no-data semantics come free. **Recommendation: don't add another indicator-API vendor** — indicators are computed locally from OHLCV; a third API adds N×M name mapping, can't serve customs (td_9/z_score/supertrend-MTF/obv), and risks numeric drift vs the verified snapshot. Higher-ROI: a second **OHLCV** source (Stooq via pandas-datareader, keyless; or Tiingo) benefiting all ~24 indicators and hardening against yfinance 429s. If an indicator API is still wanted, Twelve Data, mirroring `alpha_vantage_indicator.py`. (Optional follow-up, not in this change.)

## Verification

- 2026-06-12 implementation review: registry, MFI rescale, Alpha Vantage
  fallback, new indicators, parameter overrides, and snapshot parity were
  reviewed against the current staged diff. Fixed one full-suite blocker in
  `tradingagents/llm_clients/openai_client.py` where explicit `api_key`
  kwargs were ignored for OpenAI-compatible providers such as DeepSeek.
- 2026-06-12 checks: targeted indicator suite passed (`49 passed`); full
  suite passed (`501 passed, 1 skipped, 7 warnings, 79 subtests passed`).
- Per phase: `uv run --with pytest python -m pytest tests/ -q` (pytest not a project dep).
- After Phase 1: golden prompt test green = no agent-behavior drift.
- After Phase 2: force AV primary via `tool_vendors: {"get_indicators": "alpha_vantage"}` in a scratch config and confirm vwma/kdj fall back to yfinance values.
- End-to-end smoke after Phase 3/4: run one analyst pass (e.g. `python -m cli.main` or existing run scripts) on a liquid ticker and confirm the market report cites new indicators sensibly; spot-check `mfi` is 0–100 and supertrend tiers render.

## Risks

1. Prompt drift → golden test is the contract; never paraphrase existing descriptions.
2. AV short-circuit recurrence → the all-names loop test makes "raise, never return prose" permanent.
3. MFI rescale changes prior 0–1 readings — bug fix, but rescale identically in tool + snapshot.
4. stockstats raises `UserWarning` (not KeyError) for unknown columns; registry up-front validation keeps `_get_stock_stats_bulk`'s broad `except` from silently emitting empties.
5. `mdi`→`ndi`→`MINUS_DI` mapping lives in exactly one place (the spec).

Sizing: ~4 working days (P1 ≈ 1d, P2 ≈ 0.5d, P3 ≈ 1.5d, P4 ≈ 1d).
