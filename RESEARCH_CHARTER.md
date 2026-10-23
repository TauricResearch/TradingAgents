# Koral Equities — Research Mandate v2.0 (proposed, 21 October 2026)

**Status: research specification, not live trading approval.** This document does not modify the user's running £10,000 GBP paper-forward configuration. The first live-forward run and all subsequent decisions retain their own original strategy version and timestamps.

## Mandate

Develop a repeatable, measurable **long-only U.S. equity swing** research strategy, initially with virtual capital. Seek risk-adjusted returns above a genuinely investable passive index and a cheap factor baseline **after** trading costs, FX effects and model/research costs. Keep the user's existing long-term Trading 212 ISA holdings outside all paper and future live order namespaces. Do not represent a plausible hypothesis or backtest result as a guaranteed income.

## Investment hypothesis (falsifiable)

Conditional on liquidity and quality, U.S. stocks with intermediate-horizon momentum, credible positive fundamental developments and well-established earnings/estimate catalysts may deliver favourable 5–20 session forward returns. An LLM investment committee could improve selection or veto risky candidates **beyond** a cheap deterministic screen. The competing null hypothesis is that AI adds no return or worse returns relative to a deterministic strategy with identical universe, exposure, costs and portfolio rules.

Academic antecedents: Jegadeesh–Titman momentum (1993); Novy-Marx profitability (2013); Asness–Frazzini–Pedersen Quality Minus Junk (2019); PEAD literature. These are not direct validations of this particular strategy. Momentum crashes exist (Daniel–Moskowitz 2016); post-earnings anomalies change by period and are not universal.

## Architecture — additions to assess, in priority order

1. **Market-universe ingestion (required before live integration).** Collect point-in-time, historically accurate, **tradeable-at-the-time** US common-stock membership, including failed/delisted companies and corporate actions. Distinguish prices, split adjustments, volume, calendar/filing publication timestamps, and analyst estimate snapshots. No all-history test may use today's S&P 500 members as the past universe. Snapshot data and provenance; fail closed on stale/missing vital fields.
2. **Deterministic stock screen (first module available separately).** Start with US common stocks at least $10/share, $2bn cap and $20m average dollar volume (research priors); positive 6–1 and 12–1 momentum, price above 200-session average; remove companies with known earnings in the next seven calendar days. Rank and send at most 12 names for AI review. Inputs must be stamped as known as of the cutoff. A real corporate-action/data provider is **not yet connected** to this module. These thresholds are unoptimised starting hypotheses.
3. **Fundamental and catalyst features (not implemented).** Profitability, cash-flow quality, balance-sheet resilience, earnings/guidance surprises, consensus revisions **from as-of vendor histories**. Avoid spurious precision and revised data. Force each AI claim to name the underlying source and its release time; no unsupported price targets. No AI-generated news counts as a source.
4. **AI committee (adapt existing TradingAgents graph).** Give bull and bear distinct evidence and require explicit disconfirming evidence. Include source-grounding/verification and a structured rating + risks + catalyst expiry. Log raw inputs, model/provider/version, temperature, tools, timestamps, output and reasoning summaries. Fail closed on provider errors, unavailable data and prompt-injected sources; do not let raw headlines issue operational instructions. Never promote verbal confidence to calibrated probability unless validated.
5. **Entry/exit and portfolio layer (existing paper engine; refine after isolated testing).** Next-session open, long-only, no margin. Keep agreed **2% intended stop-risk per position** as the named paper baseline, capped by cash, max 30% name exposure, 5 positions and 6% aggregate planned risk, with a 10% sticky drawdown guard on **new** positions. Stop losses and gaps can exceed budget. Evaluate ATR/volatility-based stops against the existing fixed 8% stop in a separate pre-registered experiment; do **not** silently change it. Add group/sector correlation constraints and explicit pre-earnings exposure policy before any live deployment. A risk filter is not a guaranteed risk limit during a gap.
6. **Regime and exposure research (not implemented).** Candidate inputs such as market trend/breadth and realised volatility may serve to cap gross exposure **only if** their incremental benefit survives unseen periods. Avoid tuning macro narratives to past corrections.
7. **Portfolio-level validation.** Use actual point-in-time dividends/splits, next-open prices, realistic participation, latency, overnight gaps, spreads/fees and conversion. Score daily GBP equity curves, net CAGR/Sharpe/Sortino/maximum DD, total-return benchmark-relative alpha, calibration, turnover, drawdown length, and costs including LLM calls. All candidate ranking and model selections must be held fixed before final test.
8. **Operational hardening before real money.** Independent kill switch, daily autonomous schedule, missed-session catch-up without skipping stops, full order reconciliation and real API permission audit; no connection to the real Trading 212 ISA until these exist. Test partial fills, delistings, splits, earnings calendars and data outages.

## Comparison design

Run at least four fully separate portfolios using **same starting equity, universe snapshot, execution/costs and risk rules**:

- **A:** passive GBP total-return SPY benchmark (net of applicable FX/fees in comparative basis; benchmark isn't a live ETF holding).
- **B:** deterministic momentum-and-quality strategy without AI.
- **C:** B with a *single* AI veto/rank analyst.
- **D:** B with the full multi-agent debate.

Also retain an **unchanged original eight-stock watchlist** forward baseline. Comparing only D to cash/zero is insufficient. Use ablation analysis to find out whether the expensive AI element contributes enough after API costs.

## No-look-ahead and registration protocol

- Freeze one train/explore window, one model-selection window, and a **never-touched** final test window. A candidate split for investigation is 2017–2022 exploratory, 2023–2024 validation, 2025–2026 holdout; only confirm the final boundary once adequate as-of data coverage and vendor availability are known. Do not use hindsight-tuned earnings/news from the holdout.
- Train/research and final tests must use immutable data and code hashes, model IDs, provider responses when permitted, source publication times and recorded parameters. Do not select winners among hundreds of variants without correction for multiple testing, and do not discard failed experiments from the audit log.
- Forward paper evaluation: **at least six calendar months and 100 completed trades**, whichever takes longer, then assess evidence of net *incremental* benefit; do not treat 100 highly correlated trades as 100 independent signals.
- Model drift, broken data feeds, changed symbol mappings and AI vendor outages are **failures to observe**, not a reason to imagine an order.
- Final baseline is approved only after the experiment is registered, code tested, and dependencies frozen. Any change creates a new experimental version; preserve the old portfolio's timestamps and decisions. Do not optimize risk sizing from returns alone.

## What counts as a useful result

A decision is defensible when D is robustly superior to B and C on unseen portfolio returns **after costs and adjusted for comparable risk**, with stable behaviour across different market conditions, and no severe unexamined tail risk. A single positive backtest or first profitable month is not sufficient. Treat failure to add value as a valid outcome and retire unnecessary agents. The long-term business case only exists if the strategy's audited out-of-sample results can justify the time, data bills and capital risk.

## Immediate state

- Forward engine/dashboard: paper only, **not** proven profitable, currently manually triggered.
- This release: an **offline deterministic screener** (with exclusion reasons) and test suite; not connected to live price feeds, TradingAgents decisions, nor the forward book. No portfolio risk or order behaviour is changed.
- Before expanding universe: fix data provenance, benchmark total returns, cost assumptions, split/delisting handling, earnings calendars and sector exposure policies, and establish a parameter/model change log.
