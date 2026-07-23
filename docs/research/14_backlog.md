# 14 — Prioritized Backlog

Deliverable 14. The roadmap ([13_roadmap.md](13_roadmap.md)) phases broken into implementable stories, in build order. **Estimates are planning estimates, not commitments** (pd = person-days, sized the way this repo's shipped features were). Risk 1–3 (low/med/high). "Evidence" cites the finding that justifies the story.

## Legend
Phase · Story · Estimate (pd) · Depends · Risk · Evidence

## P0 — Strategy SDK (Track T1)

| ID | Story | pd | Depends | Risk | Evidence |
|---|---|---|---|---|---|
| P0.1 | `strategy.py`: `Strategy` protocol, `StrategyContext`, `OrderIntent`, `ParamSpace` | 1.5 | — | 1 | [10](10_strategy_sdk.md) |
| P0.2 | `registry.py` + `register`/`build_strategy`/`list_strategies` | 0.5 | P0.1 | 1 | [10](10_strategy_sdk.md) |
| P0.3 | Wrap rules engine as `rules_v1` (lift signals/gates/ladder constants into ParamSpace) | 2 | P0.1 | 2 | [01](01_trader_statistics.md) §7 (params as options, a-priori defaults) |
| P0.4 | Wrap LLM pipeline as `pipeline_llm`; `BacktestEngine.strategy` branch | 1.5 | P0.3 | 2 | [07](07_lld.md) T1 |
| P0.5 | `strategy_id`+`strategy_params` in record; `schema_version` marker | 1 | P0.2 | 1 | [08](08_data_schema.md) |
| P0.6 | `GET /api/backtest/strategies` + frontend dynamic strategy/param picker | 2 | P0.5 | 2 | [09](09_api_spec.md) |
| P0.7 | Regression guard: `rules_v1` reproduces current strategy-quality outcomes; gates+deploy+prod-verify | 1 | P0.4 | 2 | cross-phase invariant |

## P1 — Order lifecycle (Track T2)

| ID | Story | pd | Depends | Risk | Evidence |
|---|---|---|---|---|---|
| P1.1 | `PendingOrder` book on SimBroker: `submit`/`cancel`/`_match_pending`; market path unchanged | 2 | P0.1 | 2 | [05](05_gap_analysis.md) §A |
| P1.2 | Limit + stop-entry fills (touch/gap-through, pessimistic) + per-kind tests | 2 | P1.1 | 3 | [12](12_validation_methodology.md) Part 1 #2 |
| P1.3 | Brackets (entry+stop+TP as OCO group); existing TP-ladder+breakeven becomes default bracket | 2 | P1.2 | 3 | [02](02_pattern_report.md) chart-pattern+invalidation-stop |
| P1.4 | Trailing stops (atr/pct/chandelier), ratchet-only, `initial_stop` fixed | 1.5 | P1.3 | 2 | [03](03_institutional_best_practices.md) BP6 (trailing 23/24) |
| P1.5 | Pyramiding: scale-in intents, aggregate stop trails, depth bounded by caps | 2 | P1.4 | 3 | [03](03_institutional_best_practices.md) BP3 (pyramids 19/20) |
| P1.6 | `orders.json` artifact + trade→order join; UI order-type controls | 2 | P1.3 | 2 | [08](08_data_schema.md) T2 |
| P1.7 | Gates + deploy + prod-verify (market bracket == today's result) | 1 | P1.6 | 2 | cross-phase invariant |

## P2 — Optimization + guards (Track T3)

| ID | Story | pd | Depends | Risk | Evidence |
|---|---|---|---|---|---|
| P2.1 | `optimize.py`: grid + random search over ParamSpace; each trial a child run | 2 | P0.3 | 2 | [05](05_gap_analysis.md) C6 |
| P2.2 | Walk-forward *fitting* (extend `walkforward.py` window gen); OOS-concatenated result | 2 | P2.1 | 2 | [12](12_validation_methodology.md) Part 2 |
| P2.3 | `validation.py`: purged/embargoed CV split helper + tests vs worked examples | 2 | — | 2 | [12](12_validation_methodology.md) |
| P2.4 | Deflated Sharpe + PBO (CSCV); enforced reporting (OOS headline, n_trials, verdict band) | 2 | P2.3 | 2 | [12](12_validation_methodology.md) Parts 2–3 |
| P2.5 | Optimization job type + records + ring-unit (parent+children) | 1.5 | P2.1 | 2 | [08](08_data_schema.md) T3 |
| P2.6 | `POST /optimize` + `/optimizations` endpoints + progress SSE + UI (heatmap, guards) | 3 | P2.5 | 2 | [09](09_api_spec.md) |
| P2.7 | Perf: process-pool trials, drop headless sleep, share indicator series | 2 | P2.1 | 2 | [11](11_performance_recommendations.md) R1–R3 |
| P2.8 | Gates + deploy + prod-verify a small real sweep | 1 | P2.6 | 2 | cross-phase invariant |

## P3 — Portfolio + multi-TF (Track T4)

| ID | Story | pd | Depends | Risk | Evidence |
|---|---|---|---|---|---|
| P3.1 | `PortfolioReplay` k-way timestamp merge; single-symbol = degenerate case | 2.5 | P0.1 | 3 | [07](07_lld.md) T4 |
| P3.2 | Higher-TF aggregation, visible only after close + look-ahead assertion | 2 | P3.1 | 3 | [12](12_validation_methodology.md) Part 1 #1 |
| P3.3 | Capital allocator (equal/vol-normalized/fixed); budget conservation | 2 | P3.1 | 2 | [03](03_institutional_best_practices.md) BP1 |
| P3.4 | Portfolio-heat cap + correlation-exposure cap in risk engine | 2 | P3.3, P1.1 | 3 | [02](02_pattern_report.md) Donchian+correlation (lift 8.2) |
| P3.5 | `symbols[]`/`timeframes[]` request + `equity_by_symbol.json` + UI multi-symbol | 2.5 | P3.4 | 2 | [08](08_data_schema.md)/[09](09_api_spec.md) T4 |
| P3.6 | Gates + deploy + prod-verify a 2–3 symbol run | 1 | P3.5 | 3 | cross-phase invariant |

## P4 — Cost/funding realism (Track T5)

| ID | Story | pd | Depends | Risk | Evidence |
|---|---|---|---|---|---|
| P4.1 | `SpreadModel` (per-asset half-spread) + effective-fill wiring | 1.5 | P1.1 | 2 | [05](05_gap_analysis.md) C5 |
| P4.2 | `ImpactModel` (sqrt participation) + per-trade `impact_bps` | 1.5 | P4.1 | 2 | [04](04_framework_comparison.md) (impact = field-wide gap) |
| P4.3 | `FundingModel` perp accrual, as-of-safe; `funding_paid` per trade | 2 | P4.1 | 2 | [12](12_validation_methodology.md) Part 1 #3 |
| P4.4 | `cost_profile` request + provenance in view; flat defaults reproduce today | 1 | P4.3 | 1 | [08](08_data_schema.md) T5 |
| P4.5 | Gates + deploy + prod-verify realistic vs flat on one window | 1 | P4.4 | 2 | cross-phase invariant |

## P5 — Analytics + RL/regime decision (Track T6)

| ID | Story | pd | Depends | Risk | Evidence |
|---|---|---|---|---|---|
| P5.1 | Add Omega/MAR/Ulcer/UPI/tail-ratio/gain-to-pain/CVaR to metrics (None-safe, fixtures) | 2 | — | 1 | [04](04_framework_comparison.md) porting list |
| P5.2 | Rolling Sharpe/Sortino/vol series + `rolling.json` + UI | 1.5 | P5.1 | 1 | [04](04_framework_comparison.md) |
| P5.3 | Wire rule-based regime into StrategyContext (look-ahead-safe) | 1.5 | P0.1 | 2 | [03](03_institutional_best_practices.md) BP5 |
| P5.4 | Written decision: integrate vs retire the Q-learning prototype | 0.5 | — | 1 | [05](05_gap_analysis.md) C6 (unwired ML) |
| P5.5 | Gates + deploy + prod-verify new metric cards | 1 | P5.2 | 1 | cross-phase invariant |

## Totals (planning only)

| Phase | Stories | ~pd |
|---|---|---|
| P0 Strategy SDK | 7 | ~9.5 |
| P1 Order lifecycle | 7 | ~12.5 |
| P2 Optimization + guards | 8 | ~15.5 |
| P3 Portfolio + multi-TF | 6 | ~14 |
| P4 Cost/funding | 5 | ~7 |
| P5 Analytics + decision | 5 | ~6.5 |
| **Total** | **38** | **~65 pd** |

These are order-of-magnitude planning figures for scoping conversations, not a schedule. The honest read: this is a multi-month program for one engineer, and P0→P1→P2 (the differentiating core: pluggable strategies, real order lifecycle, validated optimization) is roughly the first ~37 pd and delivers most of the operator-visible value. P3–P5 are the breadth build-out that follows.
