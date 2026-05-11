# Brief: Trading Benchmark Command

**Date:** 2026-05-08
**Brief ID:** BENCH-001
**Status:** Closed — implemented in `src/cli/commands/benchmark.ts`
**Priority:** P1
**Language:** TypeScript (Bun runtime)
**Location:** `src/cli/commands/benchmark.ts`

---

## Objective

Add a `trading benchmark` command that compares portfolio returns against a passive benchmark index over standard holding periods (3m, 6m, 1y).

**Core question:** Is our active trading adding alpha, or would we be better off in a passive ETF?

---

## Requirements

### Data Sources

| Source | Table | Columns Used |
|--------|-------|-------------|
| Portfolio positions | `positions` | ticker, quantity, avg_cost, entry_date |
| Portfolio prices | `prices` | ticker, date, close, currency, gbp_rate |
| Benchmark prices | `prices` | ticker=VWCE.DE or BENCHMARK env, date, close |

### Metrics

| Metric | Calculation |
|--------|-------------|
| Portfolio return | `(current_value - cost_basis) / cost_basis` |
| Benchmark return | `(benchmark_current - benchmark_entry) / benchmark_entry` |
| Alpha | `portfolio_return - benchmark_return` |
| Annualized | `(1 + total_return)^(365/days) - 1` |

### Periods

- **Since inception:** From earliest position entry date
- **YTD:** From Jan 1 of current year
- **1 year:** Last 252 trading days
- **Custom:** `--since YYYY-MM-DD`

### Output

```
BENCHMARK COMPARISON
Benchmark: VWCE.DE (Vanguard FTSE All-World)
═══════════════════════════════════════════════════════════════

Period          Portfolio     Benchmark     Alpha        Winner
───────────────────────────────────────────────────────────────
Since inception  +12.6%        +8.3%        +4.3%        🟢 You
YTD 2026         +5.2%         +3.1%        +2.1%        🟢 You
1 year           —             —            —            —
───────────────────────────────────────────────────────────────

Portfolio value:    £82,524
Cost basis:         £73,287
Benchmark (same):   £79,412  (if invested at same times)

Annualized return:  +18.4%
Benchmark ann:      +11.2%
Alpha ann:          +7.2%
```

---

## Implementation

### Algorithm

1. **Load positions:** All open positions with entry_date and avg_cost
2. **Load prices:** For each position ticker, get price at entry_date and latest price
3. **Compute portfolio:**
   - Entry value = sum(quantity * avg_cost * gbp_rate_at_entry)
   - Current value = sum(quantity * latest_price * latest_gbp_rate)
4. **Load benchmark:** VWCE.DE prices for same date range
5. **Compute benchmark:** Same cost basis invested in benchmark at same entry dates
6. **Calculate periods:** Slice by date ranges

### Edge Cases

- Missing price for entry date: use first available price after entry
- Missing benchmark price: skip period, show "—"
- Currency mismatch: All values in GBP (use gbp_rate)
- No positions: Show empty state with benchmark-only data

---

## Acceptance Criteria

- [ ] `trading benchmark` shows comparison table with periods
- [ ] `trading benchmark --since 2026-01-01` custom period
- [ ] `trading benchmark --benchmark SPY` different benchmark
- [ ] All returns computed in GBP
- [ ] Graceful handling of missing price data
- [ ] Color coding: green = portfolio ahead, red = behind
- [ ] `just check` passes
- [ ] `just test-cli` passes (add test if needed)

---

## Technical Notes

- Reuses `portfolio-data.ts` computation patterns
- Queries prices table (not live yfinance) for consistency
- Benchmark ticker configurable via `--benchmark` or env `BENCHMARK`
- Default benchmark: VWCE.DE (already in price table)

---

## Related

- `src/cli/commands/portfolio.ts` — similar data loading pattern
- `src/server/lib/benchmark.ts` — server-side benchmark logic (Python subprocess)
- `src/server/lib/portfolio-data.ts` — price fetching, GBP conversion
- Brief: `briefs/brief-doc-review-recommendations-2026-05-08.md` Task 5 (minimal server test suite)
