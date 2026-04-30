# Portfolio Graph Validation Plan Tightening

## Problem

The existing implementation plan at `docs/superpowers/plans/2026-04-29-fix-portfolio-graph-validation.md` is directionally correct, but a few boundaries are still loose enough to let the implementation drift:

- new PM buy-order fields can become schema-only rather than runtime-enforced
- postcheck grounding can still rely on candidate presence instead of structured BUY evidence
- rerun-idempotency language can blur the distinction between canonical `run_id` and transient execution keys
- rerun-key lifecycle can be implemented in a way that clears protection too early

The plan should be tightened so every new field and guard is enforced at the same runtime boundaries where invalid orders or duplicate reruns would otherwise escape.

## Recommended Approach

Keep the current 8-task structure, but revise Tasks 3, 4, 5, and 7 so the runtime contract is explicit and end-to-end.

## Tightened Design

### 1. PM Buy Order Runtime Contract

The PM buy-order schema should continue to require:

- `entry_price`
- `limit_price`
- `max_chase_price`
- `order_type`
- `valid_as_of`

These are not documentation-only fields. They are runtime contract fields and must be validated before trade execution.

Required semantics:

- `valid_as_of` must exactly equal the portfolio run `analysis_date`
- `entry_price` must be positive
- `limit_price` must be positive
- `max_chase_price` must be positive
- `entry_price <= limit_price`
- `entry_price <= max_chase_price`
- `order_type` must be `"limit"`

Live execution semantics:

- a live price below `entry_price` is allowed
- a live price above `limit_price` is rejected
- a live price above `max_chase_price` is rejected
- `stop_loss` must remain below live price
- `take_profit` must remain above live price

### 2. Candidate Grounding Rule

For any non-SGOV buy to pass PM postcheck, the ticker must be grounded by structured candidate evidence, not just candidate presence.

Grounding rule:

- candidate must appear in `prioritized_candidates`
- candidate must carry `candidate_final_trade_decision_structured`
- structured payload must have `status == "completed"`
- structured payload must have `action == "BUY"`

This keeps prose from reintroducing ambiguity after Task 2 filters candidate admission.

### 3. SGOV Exception Scope

SGOV remains the only exception to the full PM buy-order guard fields.

That means:

- SGOV cash sweep can continue using the narrow cash-equivalent path
- no other ticker gets the same exception
- the plan should describe this as an explicit one-off exception, not a general cash-equivalent category shortcut

### 4. Postcheck and Executor Parity

The order guard must exist in both places:

- **postcheck** rejects invalid PM output before execution
- **executor** rejects invalid orders again in case postcheck is bypassed, stale, or called through another path

The same contract should be enforced in both layers so schema drift cannot create a silent gap.

### 5. Rerun Idempotency Scope

Task 7 should be described as duplicate rerun prevention on the same canonical run, not run-id replacement.

Design facts:

- the root persistent identifier remains the same `run_id`
- rerun helpers may use a distinct transient execution key for event-mapper and logger isolation
- duplicate active reruns for the same `(phase, identifier, node_id)` on the same root run should return `409`

### 6. active_rerun_key Lifecycle

`active_rerun_key` should be cleared only when the active rerun:

- completes
- fails
- is explicitly stopped

It should not be cleared inside generic task-replacement plumbing such as `_set_run_task()`, because that can erase protection for the rerun that was just claimed.

## Plan Edits Required

The implementation plan should be revised as follows:

1. **Task 3**: state that the new PM fields are runtime-enforced contract fields.
2. **Task 4**: extend buy validation to check `valid_as_of == analysis_date`, `entry_price > 0`, `entry_price <= limit_price`, and `entry_price <= max_chase_price`.
3. **Task 4**: change grounding to require structured completed BUY evidence.
4. **Task 5**: mirror the same buy-order guard rules in the executor.
5. **Task 7**: describe duplicate rerun prevention on the same root run and clear `active_rerun_key` only in rerun completion/failure/stop paths.

## Error Handling

Failures should stay explicit and deterministic:

- missing live prices fail loudly
- invalid order envelopes fail loudly
- stale or mismatched `valid_as_of` fails loudly
- missing structured BUY grounding fails loudly
- duplicate active rerun requests fail with `409`

## Testing Expectations

The tightened plan should keep regression coverage focused on:

- schema enforcement for required PM fields
- postcheck rejection for invalid entry/limit/chase/date conditions
- executor rejection for the same invalid order conditions
- structured BUY grounding only
- SGOV-only exception behavior
- duplicate rerun request rejection and correct rerun-key lifecycle

## Scope Check

This remains a single implementation plan. It is still focused on one coherent goal: hardening portfolio graph validation and rerun safety so only executable, grounded orders can flow downstream.
