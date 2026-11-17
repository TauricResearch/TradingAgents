"""SEL-TA-FR-005 — Distinguish ratings and actions.

Fit: five final ratings and REVIEW are readable; REVIEW never becomes Hold;
completed reports carry exactly one final-rating header plus the three labelled
stages; no-portfolio Hold keeps its defined meaning.

Enforcing design: report envelope/body labels + runapi/finalize (INV-13).
"""

from __future__ import annotations

import pytest

from tradingagents.agents.rating import parse_rating
from tradingagents.runapi.result import RunResult

pytestmark = pytest.mark.unit


# TC-FR005-a: every five-tier rating and REVIEW is parsed as itself.
@pytest.mark.parametrize("rating", ["Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW"])
def test_tc_fr005_a_final_ratings_readable(rating):
    assert parse_rating(f"Rating: {rating}") == rating


# TC-FR005-b: unreadable final text is REVIEW, never a fabricated Hold.
def test_tc_fr005_b_unreadable_final_is_review():
    assert parse_rating("I cannot decide.") == "REVIEW"


# TC-FR005-c: a completed RunResult enforces one rating and consistent check.
def test_tc_fr005_c_completed_requires_single_rating():
    ok = RunResult("r1", "AAPL", "2026-11-12", "NO_PORTFOLIO", "COMPLETED", None,
                   "Hold", "PASSED", ())
    assert ok.final_rating == "Hold"
    with pytest.raises(ValueError):
        RunResult("r1", "AAPL", "2026-11-12", "NO_PORTFOLIO", "COMPLETED", None,
                  None, "NEEDS_REVIEW", ())


# TC-FR005-d: a report with different Research Manager / Trader / Portfolio
# Manager judgments labels the three stages and shows exactly one final rating,
# taken from the Portfolio Manager.
def test_tc_fr005_d_three_labelled_stages_one_pm_rating(tmp_path):
    from conftest import make_engine

    from tradingagents.runapi.execution import run_analysis_api
    from tradingagents.runapi.input_service import freeze_explicit

    rm_text = "RM_RECOMMENDATION: Overweight on improving demand."
    trader_text = "TRADER_ACTION: buy in two tranches."
    pm_text = "Rating: Sell\n\nPM_DECISION: take profits, direction reversed after debate."

    state = {
        "market_report": "MKT",
        "investment_debate_state": {"bull_history": "BULL", "bear_history": "BEAR"},
        "investment_plan": rm_text,
        "trader_investment_plan": trader_text,
        "risk_debate_state": {"neutral_history": "NEUTRAL"},
        "final_trade_decision": pm_text,
        "final_rating": "Sell",
    }
    factory, runner = make_engine(state)
    ctx = freeze_explicit("AAPL", "2026-11-12", None).confirm()
    result = run_analysis_api(
        ctx, config={"results_dir": str(tmp_path), "selected_analysts": ["market"]},
        selected_analysts=["market"], graph_factory=factory, engine_runner=runner,
    )

    report = (tmp_path / "AAPL" / result.run_id / "reports" / "complete_report.md").read_text()

    # Three stages are clearly labelled and carry their own judgment text.
    assert "## II. Research Team Decision" in report and "### Research Manager" in report
    assert "## III. Trading Team Plan" in report and "### Trader" in report
    assert "## V. Portfolio Manager Decision" in report and "### Portfolio Manager" in report
    assert rm_text in report and trader_text in report and pm_text.splitlines()[-1] in report

    # Exactly one final rating is shown, and it is the Portfolio Manager's.
    final_lines = [line for line in report.splitlines()
                   if line.startswith("- Final Portfolio Manager rating:")]
    assert final_lines == ["- Final Portfolio Manager rating: Sell"]
    assert result.final_rating == "Sell"
