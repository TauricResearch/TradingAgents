# Cash-Floor Invariants and the PM Decision Tail

This document is the durable explanation of the cash-flow math that runs at the
end of every Portfolio Manager (PM) decision. It exists so that future engineers
can change adjacent code without re-deriving the algebra, and so that reviewers
can audit a basket against a concrete worked example rather than against
folklore.

The audience is engineers who know Python and LangGraph but do not necessarily
know finance. Where finance vocabulary is unavoidable it is defined inline.

---

## 1. The Invariant

> After a PM decision is finalized, the projected post-trade cash held by the
> portfolio is at least `min_cash_pct` of the projected post-trade total NAV,
> priced at the same live execution prices that the trade executor will use.

In symbols:

```
projected_cash_after_buys >= min_cash_pct * projected_total_value
```

where every BUY is priced with `resolve_buy_execution_price(buy, prices)` —
the live price, not the PM's intended `entry_price`.

If this invariant cannot be reached by scaling buys, the basket is rejected by
`pm_decision_postcheck` and execution does not run.

---

## 2. The Pipeline

The PM decision tail is four nodes:

```
make_pm_decision  →  rescale_buys  →  cash_sweep  →  pm_decision_postcheck  →  execute_trades
```

Each node has one job, and only the order shown is guaranteed to satisfy the
invariant.

### 2.1 `make_pm_decision`

LLM-driven node. Emits a `pm_decision` JSON blob with `sells`, `buys`, and
`holds`. The PM may emit a basket whose aggregate buy cost violates the cash
floor — that is acceptable here. Downstream nodes correct it deterministically.

### 2.2 `rescale_buys`

Deterministic guard. Computes a hard cash ceiling and, if buys exceed it, scales
every buy's `shares` field by the same factor `scale = ceiling / total_notional`.

Cash-related formula:

```
ceiling       = max(0, cash - min_cash_pct * total_value)
total_notional = sum(shares_i * resolve_buy_execution_price(buy_i, prices))
if total_notional > ceiling:
    for each buy: buy["shares"] *= ceiling / total_notional
```

If `ceiling <= 0`, all buys are dropped.

The crucial point — and the source of the P2 fix — is that `total_notional` is
priced at the **live** execution price, not at `entry_price`. Postcheck does the
same, so what passes here cannot be rejected there for cash reasons.

### 2.3 `cash_sweep`

Deterministic node that parks idle cash in SGOV (a 0–3-month treasury ETF used
as the system's cash equivalent). It runs *after* `rescale_buys` so that it
sizes against the cash that survives the PM buys, not the pre-buy cash.

Cash-related formula:

```
approved_buy_notional = sum(
    shares_i * resolve_buy_execution_price(buy_i, prices)
    for buy_i in pm_decision.buys
    if buy_i.ticker != "SGOV"
)
cash_after_buys = cash - approved_buy_notional
if cash_after_buys / total_value > target_cash_pct:
    excess        = cash_after_buys - target_cash_pct * total_value
    sweep_shares  = int(excess / sgov_price)     # floor to whole shares
    append SGOV buy with sector="Cash Equivalent"
```

`target_cash_pct` reads from `config["target_cash_pct"]` and defaults to
`min_cash_pct` when unset. This is the value the sweep aims to leave on hand;
it is **not** a hard constraint — the hard constraint is `min_cash_pct`,
enforced by postcheck. Defaulting `target_cash_pct` to `min_cash_pct`
guarantees that a deployment which raises the floor (e.g. `min_cash_pct=0.10`)
does not have its operator-intent silently violated by a hardcoded 5% target.
Operators may still set `target_cash_pct > min_cash_pct` to keep a buffer
above the floor.

### 2.4 `pm_decision_postcheck`

Deterministic auditor. Re-projects the portfolio assuming sells then buys are
filled at live prices and runs seven checks. The cash-related check is:

```
projected_total_value = projected_cash + sum(projected_holding.value)
if projected_cash < projected_total_value * min_cash_pct:
    raise RuntimeError
```

Because `min_cash_pct` is the same value `rescale_buys` already targeted, and
both nodes use `resolve_buy_execution_price`, postcheck is mathematically
guaranteed not to reject for the cash floor when the upstream nodes ran.

The postcheck also enforces position-cap (`max_position_pct`) and sector-cap
(`max_sector_pct`) constraints. SGOV / `Cash Equivalent` is exempt from both.

---

## 3. Symbols

| Symbol                  | Definition                                                                         | Source                                              | Where set                                                         |
|-------------------------|------------------------------------------------------------------------------------|-----------------------------------------------------|-------------------------------------------------------------------|
| `cash`                  | Current portfolio cash, in base currency                                           | `portfolio.cash` in `portfolio_data` JSON           | `load_portfolio` node, ultimately the DB                          |
| `total_value`           | Current NAV (cash + equity at live prices) — pre-trade                             | `portfolio.total_value` or recomputed inline        | `compute_risk` / `prioritize_candidates` enrichment               |
| `min_cash_pct`          | **Hard floor.** Minimum cash as fraction of NAV that postcheck enforces.           | Config, default `0.05`                              | `default_config.py`; can be overridden per deployment             |
| `target_cash_pct`       | **Soft target.** Level the sweep aims to leave on hand after parking excess.       | Config, defaults to `min_cash_pct` when unset       | `default_config.py` / `_make_cash_sweep_node`                     |
| `max_position_pct`      | Per-ticker cap (excludes SGOV)                                                     | Config, default `0.15`                              | `default_config.py`                                               |
| `max_sector_pct`        | Per-sector cap (excludes "Cash Equivalent")                                        | Config, default `0.35`                              | `default_config.py`                                               |
| `prices[ticker]`        | Live market price used for projection and execution                                | State key `prices`                                  | `compute_risk` / vendor fetch                                     |
| `entry_price`           | PM's intended entry; can differ from live within `max_chase_price`                 | `buy.entry_price`                                   | LLM output                                                        |
| `resolve_buy_execution_price` | Helper returning live price; raises if missing                              | `tradingagents/portfolio/order_guards.py`           | shared by rescale, sweep, postcheck, executor                     |
| `ceiling`               | `max(0, cash - min_cash_pct * total_value)` — the cash dollars rescale will spend  | computed in `rescale_buys`                          | —                                                                 |
| `total_notional`        | Sum of `shares_i * live_price_i` across all PM buys                                | computed in `rescale_buys` and `cash_sweep`         | —                                                                 |
| `cash_after_buys`       | `cash - approved_buy_notional` — cash remaining once PM buys settle                | computed in `cash_sweep`                            | —                                                                 |
| `excess`                | `cash_after_buys - target_cash_pct * total_value` — dollars to sweep into SGOV     | computed in `cash_sweep`                            | —                                                                 |

---

## 4. Worked Example

Inputs at PM decision time:

- `cash = $50,000`
- `total_value = $200,000` (so equity is $150,000)
- `min_cash_pct = 0.05`, `target_cash_pct = 0.05`
- One PM buy: ticker `XYZ`, `shares = 100`, `entry_price = $400`,
  `max_chase_price = $450`
- Live prices: `XYZ = $450`, `SGOV = $100`
- Sells: none. Holds: any.

### Step A — `rescale_buys`

```
ceiling        = max(0, 50_000 - 0.05 * 200_000) = max(0, 50_000 - 10_000) = 40_000
total_notional = 100 * 450 = 45_000               # live, not entry
total_notional > ceiling → scale = 40_000 / 45_000 = 0.8889
new_shares     = 100 * 0.8889 = 88.89
```

The basket leaves the rescale node with `XYZ` shares = 88.89, notional = $40,000
at live price.

Counterfactual: if `rescale_buys` had used `entry_price = $400`, it would have
computed `total_notional = 40_000`, judged the basket within ceiling, and not
scaled. Postcheck would then have priced the basket at $45,000 and rejected
for `projected_cash = 5_000 < required = 10_000` (since
`projected_total_value` is unchanged at $200K because cash drops by the same
dollars equity gains). This is **P2**.

### Step B — `cash_sweep`

```
approved_buy_notional = 88.89 * 450 = 40_000
cash_after_buys       = 50_000 - 40_000 = 10_000
current_cash_pct      = 10_000 / 200_000 = 0.05
0.05 > 0.05? No → no sweep
```

No SGOV buy is appended. Good: rescale already drove cash to the floor, leaving
nothing to sweep.

Counterfactual: if `cash_sweep` had used pre-buy `cash = $50,000`, it would have
seen `current_cash_pct = 0.25`, computed `excess = 40_000`, and sized
`sweep = int(40_000 / 100) = 400 shares` of SGOV worth $40,000. Combined with
the PM buy of $40,000, the basket would consume $80,000 against $50,000 of
real cash — leaving projected cash at -$30,000. Postcheck would reject. This
is **P1**.

### Step C — `pm_decision_postcheck`

Project cash: `50_000 - 88.89 * 450 = 10_000`. Project equity: existing
$150,000 plus new $40,000 = $190,000. Projected NAV = $200,000. Required cash
= `0.05 * 200_000 = 10_000`. `10_000 >= 10_000` — passes exactly.

Position-cap and sector-cap checks: scaling shrank XYZ's share, so it can only
be lower than what the PM proposed; it cannot newly violate the per-ticker
cap. Same for sectors.

### Step D — `execute_trades`

Submits 88 (or 88.89, depending on broker) shares of XYZ at limit ≤ $450. Done.

---

## 5. History — The Two Bugs

### P1 — `cash_sweep` sized SGOV from pre-buy cash

`cash_sweep` originally read `portfolio.cash` directly and computed
`excess = cash - target_cash_pct * total_value`. Because the node runs *after*
`rescale_buys`, the PM buys are already approved in `pm_decision.buys` but the
portfolio object still shows pre-buy cash. The sweep happily sized SGOV
against money that was about to be spent, causing the combined basket to
breach the cash floor in postcheck.

**Why it slipped past the spec:** the original spec described `cash_sweep` as a
standalone "park idle cash" node, written before `rescale_buys` existed.
Composition was never re-validated when rescale was added between the PM and
the sweep.

**What now prevents recurrence:** `cash_sweep` subtracts `approved_buy_notional`
from `cash` before computing `excess`. Test:
`tests/graph/test_cash_sweep_node.py::test_cash_sweep_subtracts_approved_buy_notional_from_excess`
and the live-price companion
`test_cash_sweep_uses_live_price_for_buy_notional`.

### P2 — `rescale_buys` priced notional at `entry_price`

`rescale_buys` originally totalled `shares * entry_price`. Postcheck has always
projected cash with the live price (`resolve_buy_execution_price`). When live
> entry — the common case for a momentum buy with a high `max_chase_price` —
a basket "rescaled to the ceiling" by entry-price math still over-spent at
live-price math, and postcheck rejected it.

**Why it slipped past the spec:** `entry_price` was the PM's intent and felt
authoritative. The asymmetry with postcheck was not noticed until the
trust-first review.

**What now prevents recurrence:** `rescale_buys` calls
`resolve_buy_execution_price` exactly like postcheck does. Test:
`tests/graph/test_rescale_buys_node.py::test_rescale_buys_uses_execution_price_not_entry_price`.

---

## 6. Open Questions and Known Limitations

These are *not* fixed in this iteration. They are flagged here as future work
so the next person who touches this code knows where the rough edges are.

- [x] ~~**`target_cash_pct` is hardcoded to 0.05 in `cash_sweep`.**~~ **Fixed.**
  `target_cash_pct` now reads from `config["target_cash_pct"]` and defaults to
  `min_cash_pct` when unset, so a deployment that raises the floor no longer
  has its operator intent silently violated by a hardcoded 5% target. Tests:
  `tests/graph/test_cash_sweep_node.py::test_cash_sweep_target_defaults_to_min_cash_pct`
  and `::test_cash_sweep_explicit_target_cash_pct_wins`.

- [ ] **Sells are not projected forward into the cash basis used by `rescale_buys`
  and `cash_sweep`.** Postcheck applies sells before buys when projecting,
  but the upstream guards size buys against pre-sell cash. A basket with
  large sells freeing cash is rescaled more aggressively than necessary — a
  conservatism, not a bug. **Fix:** add `projected_sell_proceeds` to the
  cash basis in both nodes. Severity: Nice-to-have (manifests as
  under-deployment of approved capital, never as a floor breach).

- [ ] **Proportional scaling is conviction-blind.** When the basket exceeds the
  ceiling, `rescale_buys` scales every buy by the same factor regardless of
  the candidate's score. A real desk would scale low-conviction names to
  zero before touching the high-conviction names. **Fix:** weight by the
  `priority_score` from `prioritize_candidates`, or peel buys off the
  basket lowest-score-first until under the ceiling. Severity: Important
  (this is a portfolio quality issue, not a safety issue).

- [ ] **No slippage buffer on the floor.** Both nodes target the floor exactly.
  If the live price ticks up by even one cent between projection and fill,
  postcheck still passes (because both use the same snapshot), but the
  actual fill can leave cash a hair below `min_cash_pct * total_value`.
  **Fix:** subtract a `slippage_buffer_bps` (e.g., 10 bps) from the
  ceiling. Severity: Nice-to-have for retail-scale baskets, Important for
  institutional fill sizes.

- [ ] **Integer-shares rounding in `cash_sweep`.** `int(excess / sweep_etf_price)`
  floors. Worst case is one share's worth of cash above the target — at
  $100/share, that is $99.99 of cash that could have been parked. Bounded
  and harmless. Severity: Non-issue.

- [ ] **Rescale-then-sweep rounding.** `rescale_buys` produces fractional
  shares (`shares * scale`). At execution, the broker may round these down.
  Because the round is downward, projected cash after fills is ≥ projected
  cash from postcheck, so the floor is preserved. But it means the actual
  sweep target is undershot by up to one share per rescaled buy. Severity:
  Non-issue for safety; tracked as a quality observation.

- [ ] **Unsettled sells.** Real-world T+1/T+2 settlement means sell proceeds
  are not actually spendable on the same day. The current math implicitly
  assumes intra-day settlement (i.e. cash from sells is available for buys
  in the same basket). If this system ever runs against a broker that
  enforces settlement, the cash basis must subtract `unsettled_sells`.
  Severity: Important when wiring real brokers.

---

## 7. What NOT to Change Without Re-Validating the Math

Before touching any of the following, re-derive the invariant against the
worked example in §4 and add a test that fails on the proposed change before
the change ships.

- [ ] **Do not change the order of `rescale_buys → cash_sweep → postcheck`.**
  The sweep depends on the rescale having already shrunk buys; the postcheck
  depends on the sweep having already added SGOV. Inserting any new node
  between them that mutates `pm_decision.buys` or `portfolio.cash`
  invalidates the proof. If you add a node, decide first whether it goes
  before rescale (it sees raw PM output) or after postcheck (it sees an
  already-validated basket). Never in the middle.

- [ ] **Do not change the price source used by either guard.** All three nodes
  (`rescale_buys`, `cash_sweep`, `pm_decision_postcheck`) and the executor
  must call `resolve_buy_execution_price` against the same `prices` dict.
  Replacing it with `entry_price` resurrects P2. Replacing it with anything
  else (e.g. mid, NBBO, vendor-specific feed) requires updating all four
  callers in lockstep.

- [ ] **Do not raise `target_cash_pct` above `min_cash_pct` in the sweep.** That
  would cause the sweep to leave more cash than the floor requires, which is
  fine in isolation, but if a deployment also lowers `min_cash_pct` below
  `target_cash_pct`, the sweep will keep buying SGOV until the projection
  hits its target — potentially exceeding what the operator wanted invested
  in cash equivalents. If you touch `target_cash_pct`, also add a test that
  asserts `target_cash_pct >= min_cash_pct` at config-load time.

- [ ] **Do not exempt new tickers/sectors from postcheck caps without auditing
  rescale.** SGOV / "Cash Equivalent" is exempt from position and sector
  caps. Adding a second exempt ticker (e.g. another money-market ETF)
  without updating the sweep-source-of-cash-equivalent set would let it
  silently bypass the cap on the equity side too.

- [ ] **Do not introduce buys outside `pm_decision.buys`.** Both rescale and
  sweep iterate `decision["buys"]` to compute notional. If a future node
  injects buys via a separate state key (e.g. a "rebalance" node), neither
  guard will see them and postcheck will reject the basket.

- [ ] **Do not assume `total_value` is the post-trade NAV.** It is the
  pre-trade NAV used as the denominator for the floor and caps. Because a
  buy converts cash to equity at the same dollar amount, NAV is invariant
  at decision time, and using pre-trade NAV is correct. If a future change
  introduces fee accrual, slippage debit, or anything else that *does*
  shift NAV at decision time, recompute the projection in postcheck and
  use the projected NAV in rescale and sweep.

- [ ] **Do not make `min_cash_pct` and `target_cash_pct` independently
  configurable without writing the relationship test.** Whatever pair the
  config exposes, the test should assert that the sweep-after-rescale
  composition cannot violate postcheck under any ordering of live-vs-entry
  prices.

---

## 8. Cross-References

- `tradingagents/graph/portfolio_setup.py` — `_make_rescale_buys_node`,
  `_make_cash_sweep_node`, `_make_pm_decision_postcheck_node`.
- `tradingagents/portfolio/order_guards.py` — `resolve_buy_execution_price`,
  `buy_order_guard`.
- `tests/graph/test_rescale_buys_node.py` — rescale unit tests including the
  P2 regression test.
- `tests/graph/test_cash_sweep_node.py` — sweep unit tests including the P1
  regression test and the live-price companion.
- `docs/superpowers/specs/2026-05-01-trading-agents-trust-first-fixes-design.md`
  — the design spec that motivated these fixes.
- `docs/portfolio/00_overview.md` — broader portfolio architecture.
