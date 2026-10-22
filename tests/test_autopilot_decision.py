from datetime import date

import pytest

from tradingagents.paper.autopilot.decision import AIExecutionProposal, policy_intent

PM="Rating: Overweight. Initiate after TWO consecutive closes above $226.87. Use a firm stop-loss at $212.16 for the paper trade, and reassess if it breaks."
ENTRY="TWO consecutive closes above $226.87"
TRADER="**Stop Loss**: $212.16"
REPORT="Original PM and trader document."


def proposal(**kw):
    args=dict(action="CONDITIONAL_LONG",rating="Overweight",entry_quote=ENTRY,
      stop_quote=TRADER,trigger_usd=226.87,stop_usd=212.16,required_closes=2,
      expiry_days=14,holding_sessions=20,allocation_fraction=.05,
      rationale="Only a confirmed breakout permits a capped paper position")
    return AIExecutionProposal(**(args|kw))


def plan(pr=None,pm=PM,trader=TRADER,close=225):
    return policy_intent(pr or proposal(),ticker="NVDA",session="2026-10-21",
         final_pm=pm,trader_plan=trader,report=REPORT,close_usd=close,sector="Technology")


def test_verbatim_evidence_generates_conditional_not_market_order():
    p=plan()
    assert p.entry_rule=="CLOSES_ABOVE"
    assert p.required_closes==2
    assert p.trigger_usd==226.87
    assert p.stop_loss_usd==212.16
    assert p.initial_allocation_fraction==.05
    assert p.expiry_date=="2026-11-04"
    assert p.max_entry_gap_fraction<=.025
    assert p.report_sha256


def test_overweight_only_does_not_authorise_trade():
    with pytest.raises(ValueError):plan(proposal(action="NO_TRADE"))
    with pytest.raises(ValueError):plan(pm="Rating: Overweight, please buy now")
    with pytest.raises(ValueError):plan(proposal(stop_quote="Risk review $212.16"))


def test_trader_stop_with_pm_risk_review_is_not_executable():
    pm="Rating: Overweight. Initiate after TWO consecutive closes above $226.87. Treat $212.16 as a risk-review level, not an executable stop."
    with pytest.raises(ValueError,match="stop"):
        plan(pm=pm)


def test_hallucinated_one_of_two_required_closes_rejected():
    with pytest.raises(ValueError,match="confirmation"):
        plan(proposal(required_closes=3))


def test_missing_proof_or_numeric_mismatch_rejected():
    with pytest.raises(ValueError,match="verbatim"):
        plan(proposal(entry_quote="Only enter after a breakout"))
    with pytest.raises(ValueError,match="grounded"):
        plan(proposal(trigger_usd=230))
    with pytest.raises(ValueError,match="stop"):
        plan(proposal(stop_usd=200))


def test_very_distant_trigger_or_allocation_exceeds_v3_cap_rejected():
    with pytest.raises(ValueError,match="stale"):
        plan(close=100)
    with pytest.raises(ValueError,match="allocation"):
        plan(proposal(allocation_fraction=.2))
    with pytest.raises(ValueError,match="horizon"):
        plan(proposal(holding_sessions=110))


def test_numerical_spoofing_has_no_order_authority():
    with pytest.raises(ValueError):plan(proposal(entry_quote="TWO consecutive closes above $226.88"))
    with pytest.raises(ValueError):plan(proposal(required_closes=None))
