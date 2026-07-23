# 02 — Pattern Report: Recurring Combinations

Deliverable 3. Where [01_trader_statistics.md](01_trader_statistics.md) counts single fields, this document reads the **co-occurrence** tables ([data/derived/cooccurrence_all_tiers.csv](data/derived/cooccurrence_all_tiers.csv)) to find method *combinations* that recur more than chance would predict.

## Method and how to read "lift"

For a pair of vocabulary values A and B, over the rows where **both** their parent fields are non-null:
- **support** = number of traders showing both A and B.
- **lift** = support / expected, where expected = (count A × count B) / N_both. Lift > 1 means the pair co-occurs more than independence predicts; lift = 3 means "3× more often than chance."

Honesty constraints (enforced in the analyzer): a pair is reported only at **support ≥ 3**, and lift is computed only over rows where both fields are disclosed. With N=146 and many fields half-undisclosed, supports are small — **treat every pattern below as a directional signal at the stated support, not an estimated prevalence.** High lift on support of 4–5 says "these genuinely travel together in the cases we can see," not "X% of traders do this."

## The strongest recurring combinations (support ≥ 4, ranked by lift)

| Combination | Support | Lift | Reading |
|---|---|---|---|
| Donchian-channel breakout + **ATR stop** | 8 | 10.6 | The classic Turtle/CTA package: channel entry sized and stopped off volatility. The single tightest pattern in the KB. |
| Earnings/fundamental catalyst + **fundamental screen** | 5 | 10.4 | Catalyst entries are pre-filtered by a fundamental watchlist — the growth-equity (O'Neil/Minervini) discipline. |
| Donchian breakout + **correlation/exposure filter** | 5 | 8.2 | Trend CTAs pair channel entries with portfolio-level correlation caps — diversification is part of the entry, not an afterthought. |
| Relative-strength rotation + **market-health index** | 5 | 8.1 | Momentum-equity rotation gated by a "market in uptrend?" breadth check (the CANSLIM "M"). |
| Volatility-event entry + **volatility-regime filter** | 5 | 7.0 | Vol traders condition entries on a regime read (VIX term structure, realized-vol state). |
| Range breakout + **market-health index** | 9 | 5.2 | Breakout traders (equities) wait for a healthy tape before taking breakouts — highest-support health-filter pattern. |
| Chart pattern + **trend-filter MA** | 5 | 4.7 | Pattern traders require the pattern to sit on the right side of a moving average. |
| **Trend-following + volatility-normalized sizing** | 12 | 4.2 | Highest-support strong pattern in the book: trend followers size positions by volatility (risk parity / % -vol), not fixed lots. |
| Range breakout + **watchlist prescreen** | 13 | 3.6 | Highest raw support of any pair: breakout traders work from a pre-built candidate list. |
| Chart pattern + **structure/swing stop** | 6 | 3.8 | Pattern traders stop at the structure that invalidates the pattern, not a fixed %. |
| Chart pattern + **watchlist prescreen** | 11 | 3.5 | Same prescreen discipline for pattern traders. |
| Chart pattern + **pattern-invalidation stop** | 5 | 3.2 | The stop is defined by where the thesis dies. |

## The four archetypal "packages" these combinations describe

Reading the pairs together, four coherent methodologies recur across the sample — each is a *bundle* of entry + filter + stop + sizing that shows up repeatedly, not a loose set of independent choices:

**1. The systematic trend-following package** (CTA cohort, ~tier A).
Channel/breakout entry (Donchian) → volatility-normalized position size → ATR-multiple stop → correlation/exposure cap across a diversified futures book → pyramiding into winners → trailing exit. This is the most internally consistent and most audited package in the KB (Dunn, JWH, Parker, the Turtles, Campbell, Aspect). Every component co-occurs at high lift. **Our engine already implements most of it** (ATR stop, R-ladder, breakeven, exposure cap) — the missing pieces are Donchian-channel entries, multi-market correlation caps, and pyramiding.

**2. The momentum/growth-equity package** (O'Neil school).
Market-health/breadth gate ("only buy in a confirmed uptrend") → relative-strength + fundamental prescreen to build a watchlist → breakout or chart-pattern entry off that list → structure/pattern-invalidation stop → sell into strength / trailing exit. The health-index and watchlist prescreen patterns are its signature. Discretionary but rule-guided (Minervini, O'Neil, Ryan, Zanger, Kell).

**3. The volatility/convexity package** (options cohort).
Volatility-regime read → volatility-event entry → asymmetric payoff construction (long convexity for the tail traders, premium selling for the income traders) → the "stop" is structural (defined loss on the option) rather than a price stop. Splits into two sub-schools with opposite sign: convex tail hedging (Taleb/Spitznagel/Cole — persistent small bleed, rare large payoff) vs premium harvesting (Sosnoff/Bruton — steady income, tail risk). **Niederhoffer and Bruton are the cautionary members: premium selling with no tail protection blew up.**

**4. The market-making / stat-arb package** (HFT + quant cohorts).
Order-flow/statistical-signal entry → spread capture or relative-value → holding periods of minutes-to-ticks → inventory/delta hedging rather than a directional stop → sizing undisclosed (proprietary). This package is *anti-correlated* with the discretionary technical patterns above — it shares almost no vocabulary with them, which is itself the point: it is a different business (earning the spread, not predicting direction).

## What the co-occurrence data does NOT show

- **No universal setup.** No single entry+filter+stop combination spans a majority of the KB. The four packages are cohort-bound; the "best traders" do not converge on one method, they converge *within* their style family.
- **Cross-package borrowing is rare.** ATR stops travel with channel breakouts, not with chart patterns (which take structure stops). Watchlist prescreens travel with equity breakouts, not with futures trend-following. The packages are internally tight and mutually distinct.
- **Small supports throughout.** The highest support of any pair is 13 (breakout + watchlist). Most are 4–8. These are real associations in the visible data, but the honest denominator is small — do not convert lift into a population percentage.

## Implication for the engine

The two packages our backtester can most credibly serve — because their components are mechanical and their exemplars are the best-documented (tier-A CTAs, competition-verified momentum traders) — are **#1 (systematic trend-following)** and **#2 (momentum/growth-equity)**. Both need capabilities the current engine lacks: Donchian/breakout entry orders (needs the order-lifecycle work, [06_hld.md](06_hld.md) T1), multi-market correlation caps (T3 portfolio), pyramiding (T1/T2), and a market-health/regime gate (partially present via the regime classifier). This is the evidentiary basis for the roadmap priorities in [13_roadmap.md](13_roadmap.md).
