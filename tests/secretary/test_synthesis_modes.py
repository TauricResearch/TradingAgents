from tradingagents.secretary.synthesis import build_synthesis_prompt


def test_single_analysis_prompt_does_not_claim_three_persona_teams():
    prompt = build_synthesis_prompt(
        ticker="NVDA",
        persona_runs=[
            {
                "persona_id": "balanced",
                "decision": "BUY",
                "final_trade_decision": "Bull and bear debate is material.",
            }
        ],
    )
    assert "Three persona investment teams" not in prompt
    assert "one or more investment analyses" in prompt
    assert "balanced" in prompt


def test_committee_prompt_preserves_disagreement_instruction():
    prompt = build_synthesis_prompt(
        ticker="AAPL",
        persona_runs=[
            {
                "persona_id": "value",
                "decision": "HOLD",
                "final_trade_decision": "valuation risk",
            },
            {
                "persona_id": "momentum",
                "decision": "BUY",
                "final_trade_decision": "trend strength",
            },
        ],
    )
    assert "Do NOT smooth over disagreement" in prompt
    assert "value" in prompt
    assert "momentum" in prompt
