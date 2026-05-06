# Upstream Issue Report: State Log Serialization Omits Debate Counter Fields

**Repository:** TauricResearch/TradingAgents  
**Component:** `tradingagents/graph/trading_graph.py` — `_log_state` method  
**Severity:** Medium (logging only, debate execution correct)  
**Status:** Fix available in fork

---

## Summary

The `_log_state` method in `tradingagents/graph/trading_graph.py` deliberately omits two fields used for debate routing logic:

1. **`count`** from both `investment_debate_state` and `risk_debate_state`
2. **`latest_speaker`** from `risk_debate_state`

These fields are used by `conditional_logic.py` to determine when to terminate debate rounds and which agent should speak next. Their absence in saved state logs creates the false impression that debate rounds are not tracking, when in fact the execution is correct and only the serialization is incomplete.

---

## Reproduction

Run any analysis and inspect the saved state log:

```python
import json

with open(f"~/.tradingagents/logs/TKA.DE/TradingAgentsStrategy_logs/full_states_log_2026-05-06.json") as f:
    data = json.load(f)

# Before fix: KeyError or None
print(data["investment_debate_state"].get("count"))      # None (key absent)
print(data["risk_debate_state"].get("count"))            # None (key absent)
print(data["risk_debate_state"].get("latest_speaker"))  # None (key absent)
```

**Expected:** `count` should be an integer reflecting actual debate rounds executed. `latest_speaker` should be a string.

**Actual:** Fields are missing from the serialized dict.

---

## Root Cause

In `tradingagents/graph/trading_graph.py:352-375`, the `_log_state` method constructs the output dict manually and does not include `count` or `latest_speaker`:

```python
"investment_debate_state": {
    "bull_history": ...,
    "bear_history": ...,
    "history": ...,
    "current_response": ...,
    "judge_decision": ...,
    # count missing
},
"risk_debate_state": {
    "aggressive_history": ...,
    "conservative_history": ...,
    "neutral_history": ...,
    "history": ...,
    "judge_decision": ...,
    # latest_speaker missing
    # count missing
},
```

Meanwhile, `conditional_logic.py:50` uses `count` for termination:
```python
state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
```

And `conditional_logic.py:60` uses `latest_speaker` for routing:
```python
state["risk_debate_state"]["latest_speaker"].startswith("Aggressive")
```

Both work correctly during execution but the evidence is lost when writing to disk.

---

## Impact

| Stakeholder | Impact |
|-------------|--------|
| **Developers** | Cannot verify debate round count from state logs; must add manual trace logging |
| **Researchers** | Cannot audit debate quality (how many rounds actually executed vs configured) |
| **Downstream consumers** | Dashboards or tools that read state logs see incomplete data |

---

## Fix

Add the missing fields to the serialization dict in `_log_state`:

```python
"investment_debate_state": {
    # ... existing fields ...
    "count": final_state["investment_debate_state"]["count"],
},
"risk_debate_state": {
    # ... existing fields ...
    "latest_speaker": final_state["risk_debate_state"]["latest_speaker"],
    "count": final_state["risk_debate_state"]["count"],
},
```

**Commit with fix:** `eee2dde` in fork `pjsvis/TradingAgents`

---

## Verification

After applying the fix, run any analysis and check the state log:

```python
>>> data["investment_debate_state"]["count"]
2
>>> data["risk_debate_state"]["count"]
3
>>> data["risk_debate_state"]["latest_speaker"]
"Judge"
```

Values confirm the debate mechanism executed the correct number of rounds:
- Investment debate: 2 turns (bull + bear) for `max_debate_rounds=1`
- Risk debate: 3 turns (aggressive + conservative + neutral) for `max_risk_discuss_rounds=1`

---

## Related

- `conditional_logic.py` — debate termination logic (uses `count`)
- `bull_researcher.py:43` / `bear_researcher.py:45` — counter increment
- `aggressive_debator.py:48` / `conservative_debator.py:50` / `neutral_debator.py:48` — risk counter increment

---

## Notes

This issue was discovered during an investigation into perceived "debate echo" (identical reasoning blocks in debug output). The debug output repetition was actually LangGraph's `debug=True` streaming trace, not a bug in debate execution. The counter omission was found during that investigation and is the only genuine bug.
