# Signal Risk Pipeline

`signal_pipeline.py` connects the new agent artifact layer to deterministic
risk review.

```python
from tradingagents.research_platform.signal_pipeline import review_legacy_decision
```

The bridge does three things:

1. Reads the current legacy Portfolio Manager markdown.
2. Converts it into a validated `TradeSignal`.
3. Runs `evaluate_basic_risk(...)` to produce a `RiskReview`.

This gives the project a safe migration path:

```text
legacy final_trade_decision
  -> TradeSignal
  -> RiskReview
  -> future BacktestResult / report / cockpit
```

The legacy graph can keep producing markdown while the new layers consume typed
objects. Over time, agents should emit `TradeSignal` directly and this bridge
can shrink to compatibility code.
