---
date: 2026-05-30
tags: [research, markov, strategy, brief, planning]
agent: pi
environment: development
---

# Debrief: Markov Phase 2 Research & Briefing

## Accomplishments

- **Phase 1 gap analysis:** Reviewed the existing `src/server/lib/markov/` implementation against Pham The Anh's 10-step Markov framework ("The Quant Secret Weapon," Towards AI, May 2026). Phase 1 covers Steps 1–6 and 8 (state classification, transition matrix, N-day forecast, signal generation). Three steps are missing: stationary distribution (#7), walk-forward backtest (#9), Hidden Markov Model (#10). All three are critical — stationary is the calibration baseline, walk-forward is the validation gate, HMM is the strategic upgrade.

- **Phase 2 brief authored:** `briefs/2026-05-30-brief-markov-phase2.md` — a complete execution document with four phases:
  - **Phase A:** Stationary distribution (1 session, `stationary.ts`)
  - **Phase B:** Walk-forward backtest (2 sessions, `backtest.ts`) — the empirical validation gate
  - **Phase C:** Hidden Markov Model via Python bridge (3 sessions, `hmm.ts` + `scripts/py/markov_hmm.py`)
  - **Phase D:** Bayesian Dirichlet-Multinomial transition estimation (1 session, `bayesian.ts`)
  - Schema additions for `regime_backtests` and `regime_hmm_models` tables
  - CLI extensions: `--backtest`, `--hmm`, `--stationary`, `--compare`, `--bayesian`, `--confidence`

- **Bayesian refinement assessed and incorporated:** The MLE transition matrix produces point estimates with no uncertainty. A Dirichlet-Multinomial conjugate prior on each row gives closed-form posteriors — no MCMC required, ~40 lines of TypeScript. The payoff: `P(signal > 0)` replaces the raw `signal` number, natural shrinkage when data is thin, confidence-aware position sizing. This maps directly to the stated objective: watch stocks until confidence crosses a threshold.

- **Complementary features documented (reserved for future phases):**
  - **Legendre Polynomial trend extraction** (Alexzap, May 2026): Low-order LP coefficients (a₀=level, a₁=slope, a₂=curvature) as an alternative state classifier — richer than raw 20-bar return. Phase 3+, after signal validated. The crossover strategy is rejected as dressed-up MA crossover with likely overfitting.
  - **Fractional Kelly position sizing** (Soroush, May 2025): `Position = 0.5 × Kelly_weight × P(signal > 0)`. Phase 4, after signal validated. Full Kelly is mathematically optimal but practically intolerable.
  - **Development philosophy** (Kirsten, Dec 2025): Start with market structure, simple rules, vectorised thinking. Principles already internalised.

- **Five articles assessed, zero rabbit holes entered:**
  | Article | Verdict |
  |---------|---------|
  | Markov Chains (Pham The Anh) | ✅ Core framework — Phase 2 built from this |
  | Quant Galore reading list | ✅ Reference calibration — confirms we're pointed right |
  | Legendre Polynomials (Alexzap) | ⚠️ Extraction method useful; strategy rejected |
  | Kelly Criterion (Soroush) | ✅ Phase 4 sizing; not yet |
  | Calendar TLT (Kirsten) | ❌ Bond-specific; philosophy only |

- **Research stop line drawn:** The brief is complete. Four executable phases with time estimates and schema are ready. Complementary features are documented for when the signal proves itself. No more articles until Phase 2 delivers results.

## Problems

- **No stationary distribution in Phase 1:** The original brief (`2026-05-20-brief-markov-regime.md`) explicitly listed Steps 7 and 9 as "future phase" but never scheduled them. The stationary distribution is critical for strategy calibration — if bear regimes are 12% of days, a strategy going short 40% of the time is structurally misaligned. Corrected in Phase 2.

- **No walk-forward validation:** Phase 1's `updateRegimeData()` computes one matrix from full history. Without walk-forward backtesting, there's no evidence the signal has predictive power. Phase B addresses this.

- **Observable states are the map, not the territory:** The article's key critique is that hand-labeled Bull/Bear/Sideways from 20-bar returns misses regimes that haven't shown up in price yet. The HMM (Phase C) is the solution — it discovers regimes from return distributions without labelled data.

- **Brief not registered in INDEX.jsonl:** The Phase 2 brief was written but not indexed. Needs registration before the next session can find it.

## Lessons Learned

- **The structural-layer heuristic applies everywhere:** Across all five articles, the same insight recurs: the visible explanation of how markets work is almost always incomplete. Observable states are the surface. Hidden regimes are the structure. The strategy isn't the strategy — the operation around the strategy is the strategy. This is consistent across authors, asset classes, and techniques. It's not a Medium cliché — it's a genuine pattern.

- **MLE without uncertainty is false precision:** The current `signal = P(bull) - P(bear)` is a point estimate that looks confident even when backed by 3 observations. The Bayesian Dirichlet posterior gives a distribution — `P(signal > 0)` rather than just `signal`. This is the bond-pricing instinct from NatWest applied to regime detection: bracket the value, don't assert a point.

- **Precision about uncertainty is more valuable than false precision about a point estimate.** This is the Scottish Enlightenment applied to probability: acknowledge what you don't know, quantify it, and size accordingly.

- **Small-investor advantages are concentration and patience:** Institutions can't concentrate (regulatory limits) and can't wait (redemption pressure). Those are genuine structural edges. The Markov + Bayesian pipeline is the mathematical expression of those edges: wait until the data is confident, then size proportionally.

- **The research-to-implementation ratio must tilt:** Five articles, one actionable brief, four executable phases. The research was productive because it converged on a specific implementation plan rather than diverging into more questions. When articles start confirming what you already planned rather than suggesting new directions, the research phase is done.

- **Briefs should be self-contained implementation documents:** The Phase 2 brief includes functional requirements, schema, CLI flags, time estimates, risk assessment, and complementary feature notes all in one file. A future session can pick up the brief and execute Phase A without asking a single question. This is the target standard for all briefs.

## Pipeline Architecture (Emerging)

```
Watchlist → Markov Regime Engine → Candidate Pool → Kelly Allocator → Execution
              │                      │                 │
              │ Phase 1: Observable   │                 │ Phase 4 (future)
              │ Phase 2: Walk-forward │ P(signal>0)≥0.75│ 0.5×Kelly×confidence
              │ Phase 2: Stationary   │                 │
              │ Phase 2: Bayesian    │                 │
              │ Phase 2: HMM         │                 │
              │ Phase 3: LP features │                 │
```

## Next Actions

1. Register `briefs/2026-05-30-brief-markov-phase2.md` in `briefs/INDEX.jsonl`
2. Start Phase A: stationary distribution (`stationary.ts`)
3. Create TD issues for Phases A–D
4. No more research until Phase B walk-forward results are in

## Reference

- **Phase 2 brief:** `briefs/2026-05-30-brief-markov-phase2.md`
- **Phase 1 brief:** `briefs/2026-05-20-brief-markov-regime.md`
- **Source article (Markov):** https://medium.com/@pta.forwork/the-quant-secret-weapon-win-trades-like-clockwork-with-markov-chains-32dc1f4ee9b3
- **HMM series:** Parts 1 and 2 at same author
- **Legendre article:** Alexzap, Towards AI, May 2026
- **Kelly article:** Farid Soroush, May 2025
- **Calendar TLT article:** Emma Kirsten, Coding Nexus, Dec 2025
- **Existing implementation:** `src/server/lib/markov/` (state.ts, matrix.ts, signal.ts, regime-data.ts, index.ts)
- **Existing CLI:** `src/cli/commands/regime.ts`
