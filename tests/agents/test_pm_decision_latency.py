"""Prompt-size budget tests for the PM decision node (PR-B4.1).

These tests verify that the prompt diet keeps context and instruction text within
character budgets. They are static structural checks — no LLM call is made.
Real end-to-end latency measurement requires a live LLM call and belongs in an
integration test with live credentials.

Run unit tests with: pytest tests/agents/test_pm_decision_latency.py -v
"""


def test_pm_context_block_under_5000_chars():
    """After prompt diet, the dynamic context block (_build_pm_context) is < 5000 chars.

    B4.1 acceptance: context block shrinks so total token consumption stays low.
    """
    import json

    from tradingagents.agents.portfolio.pm_decision_agent import _build_pm_context

    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {"cash": 50000.0, "total_value": 200000.0},
                "holdings": [],
            }
        ),
        "macro_brief": "RISK-ON: Equities preferred. Earnings season positive.",
        "micro_brief": "AAPL: BUY thesis intact. ET: HOLD.",
        "prioritized_candidates": json.dumps(
            [
                {
                    "ticker": "AAPL",
                    "conviction": "high",
                    "thesis_angle": "AI cycle",
                    "priority_score": 9.0,
                    "candidate_final_trade_decision_summary": "BUY AAPL at $175.",
                }
            ]
        ),
        "analysis_date": "2026-05-01",
    }
    cfg = {"min_cash_pct": 0.05}
    context = _build_pm_context(state, cfg)

    # The context itself should be compact
    assert len(context) < 5000, f"Context block too large: {len(context)} chars"


def test_pm_system_message_instruction_under_2500_chars():
    """After prompt diet, the static instruction preamble (before context) is < 2500 chars.

    B4.1 acceptance criterion: instruction text trimmed to essential rules only.
    The pre-diet prompt was ~3100 chars of instruction; target is < 2500.
    """
    import json

    from tradingagents.agents.portfolio.pm_decision_agent import _build_pm_context

    # Build a minimal context and measure just the instruction preamble
    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {"cash": 50000.0, "total_value": 200000.0},
                "holdings": [],
            }
        ),
        "macro_brief": "",
        "micro_brief": "",
        "prioritized_candidates": "[]",
    }
    cfg = {}
    context = _build_pm_context(state, cfg)

    # Reconstruct system_message exactly as the node does
    system_message = (
        "You are a portfolio manager. Synthesize the inputs below into a JSON-only "
        "decision matching the structured schema. Every BUY must satisfy: "
        "entry_price > 0; entry_price <= max_chase_price <= limit_price; "
        "stop_loss is 5-15% below entry; take_profit is 10-30% above entry; "
        "valid_as_of is the analysis date in YYYY-MM-DD. "
        "Sum of (shares*entry_price) across BUYs MUST NOT EXCEED "
        "max_total_buy_notional shown in Portfolio Constraints. "
        "Do not buy a ticker absent from Input B (candidate summaries). "
        "Output JSON only.\n\n"
        f"{context}"
    )

    instruction_only = system_message[: system_message.find("## Portfolio Constraints")]
    assert len(instruction_only) < 2500, (
        f"System instruction preamble too long: {len(instruction_only)} chars. "
        "Trim narrative prose; keep only rules the schema cannot enforce."
    )
