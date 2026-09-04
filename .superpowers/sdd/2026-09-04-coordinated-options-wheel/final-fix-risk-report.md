# Final Risk Fix Report

## Scope

- Owned production file: `tradingagents/risk.py`
- Owned tests: `tests/test_risk.py`
- Review issue: sample variance and covariance used a fixed divisor of 39 for every accepted return window, including 60 observations.

## Root Cause

The risk helpers accept aligned return histories from 40 through 60 observations, but both `_annualized_variance` and `_annualized_covariance` divided their centered sums by `Decimal("39")`. That is correct only for exactly 40 observations. Sample statistics require `n - 1` degrees of freedom for the actual validated series length. The covariance helper already rejects unequal input lengths before calculating its denominator.

## TDD Evidence

Added literal, hand-derived expectations at both supported boundaries for variance and covariance.

RED command:

```text
.venv/bin/pytest -q tests/test_risk.py
```

RED result:

```text
1 failed, 10 passed in 0.05s
expected Decimal('3780'), got Decimal('5718.461538461538461538461538')
```

The exact 40-observation case passed; the exact 60-observation case reproduced the fixed-divisor defect.

Minimal fix: divide variance by `len(values) - 1` and covariance by `len(left) - 1` after the existing minimum-length and equal-length validation.

GREEN result:

```text
11 passed in 0.02s
```

## Static Verification

```text
.venv/bin/ruff check tradingagents/risk.py tests/test_risk.py
All checks passed!

.venv/bin/python -m py_compile tradingagents/risk.py tests/test_risk.py
exit 0

git diff --check -- tradingagents/risk.py tests/test_risk.py
exit 0
```

No broker or network calls were made.
