# Runtime policy catalog — Deterministic Safety Gate reason codes

Stable codes are frozen strings (aligned with `tradingagents/agents/rating.py`
conventions). `PASS` carries an empty reason-code list and empty missing-evidence list.
Codes are collected in a fixed order: selected evidence, investment plan, trader plan,
decision, then rating usability.

| Code | Trigger | Action | Evidence recorded | Escalation |
|---|---|---|---|---|
| PASS | No violation: selected reports + plans + decision present, rating canonical | Preserve `final_rating`; status PASS | empty reason/missing lists | none |
| MISSING_SELECTED_EVIDENCE | Any selected report missing / blank / non-string | Downgrade to REVIEW | exact report state keys in `safety_gate_missing_evidence` | human/re-run with full selection |
| MISSING_INVESTMENT_PLAN | `investment_plan` missing or blank | Downgrade to REVIEW | key `investment_plan` | human re-run |
| MISSING_TRADER_PLAN | `trader_investment_plan` missing or blank | Downgrade to REVIEW | key `trader_investment_plan` | human re-run |
| MISSING_DECISION | `final_trade_decision` missing or blank | Downgrade to REVIEW | key `final_trade_decision` | human re-run |
| UNUSABLE_RATING | `final_rating` present but noncanonical/REVIEW, or absent and unrecoverable | Downgrade to REVIEW | rating field context | human review of decision text |
| GATE_ERROR | Unexpected exception inside the gate | Downgrade to REVIEW | available missing keys (stably empty) | engineering investigation |

Fail-closed rule: every non-PASS outcome forces `final_rating=REVIEW`. The gate never
upgrades REVIEW and never swaps one tradeable tier for another (INV-SG-02).
