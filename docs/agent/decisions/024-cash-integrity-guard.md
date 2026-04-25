# ADR 024: Cash-Integrity Guard Before PM Decision

**Date**: 2026-04-25
**Status**: Proposed
**Tags**: [portfolio, decision-integrity, fail-loud, invariants]
**Related files**:
- `tradingagents/graph/portfolio_setup.py`
- `tradingagents/agents/portfolio/pm_decision_agent.py`
- `tradingagents/portfolio/portfolio_states.py`
- `tradingagents/portfolio/repository.py`

## Context

In run `01KQ05XQ07FCBTNSEFJN6EZCNY` (2026-04-24) the portfolio loader
returned `{"cash": 0.0, "n_positions": 0, "total_value": null}` and
`pm_decision_agent` nonetheless proposed:

- `BUY AMD 246 shares @ $305.33` ≈ **$75 110**
- `BUY INTC 187 shares @ $66.78` ≈ **$12 488**
- Total notional ≈ **$87 598** against `cash=0`.
- `cash_reserve_pct=80.0` while deploying 100 % of zero cash.

The PM prompt does include a portfolio-summary block, but the LLM is
free to ignore the cash field, and there is currently no
deterministic gate between `load_portfolio` and `make_pm_decision`
that refuses to run the PM on a clearly broken portfolio payload.

This is the canonical class of error this codebase is most exposed
to: the LLM produces a plausible-looking decision against impossible
inputs, and downstream consumers cannot tell the difference.

Per ADR 023, decision-effecting nodes must hard-fail on bad input
rather than emit a synthetic verdict.

## Decision

Add a deterministic **`portfolio_integrity_guard`** node between
`compute_risk` and `review_holdings` (i.e. before any LLM node sees
the portfolio data). The node performs the following checks against
`state["portfolio_data"]`:

1. **Required fields present.** `cash`, `total_value`, `holdings`
   must be non-null. If `total_value is None`, raise.
2. **Type sanity.** `cash` must be `float >= 0`. `holdings` must be
   `list`. If types are wrong, raise.
3. **Conservation.** `abs(total_value - (cash + sum(h.market_value
   for h in holdings))) < $1`. If the equation breaks beyond the
   tolerance, raise.
4. **Non-degenerate.** If `cash == 0` *and* `len(holdings) == 0`,
   raise — there is nothing to manage and no cash to deploy; the
   load step likely failed silently.
5. **Currency.** All holdings + cash share the configured base
   currency. Mixed-currency state is currently unsupported and
   should raise rather than be silently summed.

On any check failure the node raises
`RuntimeError("portfolio_integrity_guard: <specific reason>")`
with enough context to diagnose the loader bug. No fallback, no
substitution.

Add a deterministic **`pm_decision_postcheck`** node after all
decision-mutating nodes and before `execute_trades`:

```text
make_pm_decision -> cash_sweep -> pm_decision_postcheck -> execute_trades
```

The postcheck validates the **final** `pm_decision` that will reach
trade execution, including any deterministic SGOV buy appended by
`cash_sweep`. If a future node mutates `pm_decision`, it must run
before this postcheck or add an equivalent final validation step.

1. **Cash adequacy.** Starting from current portfolio cash, apply
   same-run sells first, then all buys in final execution order.
   `available_cash_after_buys` must remain `>=
   projected_total_value * min_cash_pct`. If the final decision spends
   more cash than allowed, raise.
2. **Position-cap compliance.** Validate projected post-trade
   exposure, not each buy in isolation. For every ticker:
   `projected_ticker_value = current_holding_value - same_run_sells
   + same_run_buys`; then `projected_ticker_value /
   projected_total_value <= max_position_pct`.
3. **Sector-cap compliance.** Validate projected post-trade aggregate
   sector exposure after applying same-run sells and buys. Each
   projected sector allocation must satisfy `<= max_sector_pct`.
4. **Cash-reserve floor.** `cash_reserve_pct >= min_cash_pct`.
5. **Sells reference real holdings.** Every `sell.ticker` must
   exist in current holdings.
6. **No orphan holds.** Every `hold.ticker` must exist in current
   holdings.

Each violation raises immediately. **No clamping, no shrinking, no
silent adjustment** — that would be a fallback per ADR 023.
`execute_trades` is then free to assume the decision is internally
consistent.

## Implementation outline

```python
# tradingagents/graph/portfolio_setup.py
def _make_portfolio_integrity_guard_node():
    def node(state: PortfolioManagerState) -> dict:
        pd = json.loads(state.get("portfolio_data") or "{}")
        portfolio = pd.get("portfolio") or {}
        holdings = pd.get("holdings") or []

        if portfolio.get("total_value") is None:
            raise RuntimeError(
                "portfolio_integrity_guard: total_value is None — "
                "load_portfolio likely failed silently"
            )
        if not isinstance(portfolio.get("cash"), (int, float)) or portfolio["cash"] < 0:
            raise RuntimeError(...)
        if portfolio["cash"] == 0 and not holdings:
            raise RuntimeError(
                "portfolio_integrity_guard: empty portfolio "
                "(cash=0, n_positions=0) — refusing to run PM"
            )
        # ... conservation, currency checks ...
        return {"sender": "portfolio_integrity_guard"}
    return node
```

`pm_decision_postcheck` follows the same pattern, reading the final
post-sweep `pm_decision` JSON, upstream `portfolio_data`, current
prices, and portfolio constraints. It computes projected cash,
position, and sector exposure after same-run sells and buys before
checking caps.

## Consequences

- The PM can no longer "spend phantom cash". The loader bug surfaces
  as an explicit error rather than as a fabricated trade list.
- Constraint compliance becomes verifiable in the graph, not just
  hopeful in the prompt. The PM prompt's "MUST ensure all buys
  adhere to the portfolio constraints" becomes load-bearing again.
- `cash_sweep` may append its SGOV buy, but it cannot bypass the final
  portfolio invariant check.
- Operators see a stack trace pointing at the actual problem
  (loader returned bad data) instead of a suspicious-looking trade
  list to debug.
- Tests must cover both check paths plus all violation classes.

## Out of scope

- This ADR does not implement *automatic* repair. Per ADR 023, repair
  is a fallback that produces a synthetic decision; the operator
  fixes the loader and reruns from the checkpoint.
- Multi-currency handling is deferred to a separate decision; for
  now mixed-currency state is an error.
