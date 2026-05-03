import json
import pytest
from unittest.mock import MagicMock, patch

from tradingagents.graph._consistency_guard import (
    extract_rm_claims,
    check_claims_via_llm,
)


# ---------------------------------------------------------------------------
# extract_rm_claims
# ---------------------------------------------------------------------------

def test_extract_square_bracket_high():
    text = "- [HIGH] Revenue grew +15% YoY, increasing from $906M to $1,043M."
    assert extract_rm_claims(text) == ["Revenue grew +15% YoY, increasing from $906M to $1,043M."]


def test_extract_parenthesis_high():
    text = "*   (HIGH) Asset price breakout at $79.93 on 11.54x relative volume."
    assert extract_rm_claims(text) == ["Asset price breakout at $79.93 on 11.54x relative volume."]


def test_extract_bullet_dot():
    text = "• [MED] Sector momentum tailwind: Technology leads +9.08% monthly."
    assert extract_rm_claims(text) == ["Sector momentum tailwind: Technology leads +9.08% monthly."]


def test_extract_low_confidence_included():
    text = "  - [LOW] Analyst projects price target at $5.68."
    assert extract_rm_claims(text) == ["Analyst projects price target at $5.68."]


def test_extract_all_confidence_levels():
    text = (
        "- [HIGH] Revenue expanded +15.1% YoY.\n"
        "- [MED] Volume surged to 62M shares vs 30M average.\n"
        "- [LOW] Analyst asserts price target of $5.68.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 3
    assert claims[0] == "Revenue expanded +15.1% YoY."
    assert claims[1] == "Volume surged to 62M shares vs 30M average."
    assert claims[2] == "Analyst asserts price target of $5.68."


def test_extract_ignores_non_claim_lines():
    text = (
        "**Strongest Bull Evidence**\n"
        "  - [HIGH] Revenue grew.\n"
        "Some narrative line without a marker.\n"
        "  - [MED] Margin expanded.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 2


def test_extract_empty_text_returns_empty():
    assert extract_rm_claims("") == []
    assert extract_rm_claims("  \n  ") == []


def test_extract_nok_real_output():
    """Validate against actual NOK RM output from run 01KQNKJ4PF4D4XN7GXN6YEQHV4."""
    text = (
        "• **Strongest Bull Evidence**\n"
        "  - [HIGH] NOK revenue accelerated from $4.39B in Q1 2025 to $6.13B in Q4 2025, "
        "recording +27.0% YoY growth and sequential QoQ expansion of +3.5%, +6.2%, and +26.9%.\n"
        "  - [HIGH] NOK registered breakout accumulation on unusual volume alongside a "
        "52-week high print at $12.92.\n"
        "  - [MED] NOK price consolidation holds above $10.76 support.\n"
        "• **Strongest Bear Evidence**\n"
        "  - [HIGH] NOK sequential revenue expansion from $4.39B to $6.13B imposes a "
        "$1.74B absolute quarterly variance.\n"
        "  - [MED] Macro regime degradation below +3/6 introduces volatility risk.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 5
    assert any("$4.39B" in c and "$6.13B" in c for c in claims)


# ---------------------------------------------------------------------------
# check_claims_via_llm
# ---------------------------------------------------------------------------

def _mock_llm(response_json: dict) -> MagicMock:
    llm = MagicMock()
    msg = MagicMock()
    msg.content = json.dumps(response_json)
    llm.invoke.return_value = msg
    return llm


def test_check_claims_no_violations():
    llm = _mock_llm({"results": [{"index": 0, "ok": True}]})
    result = check_claims_via_llm(["Revenue grew +15% YoY."], "Revenue: +15% YoY.", llm)
    assert result == [{"index": 0, "ok": True}]


def test_check_claims_with_violation():
    llm = _mock_llm({
        "results": [
            {"index": 0, "ok": False, "reason": "Fundamentals show compression, not expansion."}
        ]
    })
    result = check_claims_via_llm(["Margin expanded 200bps."], "Margin compressed 270bps.", llm)
    assert result[0]["ok"] is False
    assert "compression" in result[0]["reason"]


def test_check_claims_empty_list_skips_llm():
    llm = MagicMock()
    result = check_claims_via_llm([], "any fundamentals", llm)
    assert result == []
    llm.invoke.assert_not_called()


def test_check_claims_invalid_json_raises():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "not valid json at all"
    llm.invoke.return_value = msg
    with pytest.raises(ValueError, match="not valid JSON"):
        check_claims_via_llm(["some claim"], "some fundamentals", llm)


def test_check_claims_missing_results_key_raises():
    llm = _mock_llm({"something_else": []})
    with pytest.raises(ValueError, match="missing 'results' key"):
        check_claims_via_llm(["some claim"], "some fundamentals", llm)


def test_check_claims_fail_open_for_missing_index():
    """LLM returns fewer results than claims — missing indexes default to ok=True."""
    llm = _mock_llm({"results": [{"index": 0, "ok": True}]})
    result = check_claims_via_llm(
        ["Claim 0.", "Claim 1.", "Claim 2."],
        "some fundamentals",
        llm,
    )
    assert len(result) == 3
    assert result[0]["ok"] is True
    assert result[1]["ok"] is True
    assert result[2]["ok"] is True


# ---------------------------------------------------------------------------
# Guard node behavior (patching check_claims_via_llm)
# ---------------------------------------------------------------------------


def test_guard_node_passes_clean_rm_output():
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=[{"index": 0, "ok": True}]):
        from tradingagents.graph.setup import GraphSetup
        gs = object.__new__(GraphSetup)
        gs.quick_thinking_llm = MagicMock()
        node = gs._make_rm_consistency_guard_node(gs.quick_thinking_llm)
        result = node({
            "investment_plan": "- [HIGH] Revenue expanded +15% YoY.",
            "fundamentals_report": "Revenue: +15% YoY.",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "ok"
    assert result["consistency_violations"] == []
    assert result["sender"] == "rm_consistency_guard"
    assert "_rm_consistency_attempt" not in result


def test_guard_node_routes_reprompt_on_first_offense():
    violation = {"index": 0, "ok": False, "reason": "Fundamentals show compression.", "claim": "Margin expanded 200bps."}
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=[violation]):
        from tradingagents.graph.setup import GraphSetup
        gs = object.__new__(GraphSetup)
        gs.quick_thinking_llm = MagicMock()
        node = gs._make_rm_consistency_guard_node(gs.quick_thinking_llm)
        result = node({
            "investment_plan": "- [HIGH] Margin expanded 200bps.",
            "fundamentals_report": "Margin compressed 270bps.",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "reprompt"
    assert result["_rm_consistency_attempt"] == 1
    assert len(result["consistency_violations"]) == 1
    assert "claim" in result["consistency_violations"][0]


def test_guard_node_raises_after_second_offense():
    violation = {"index": 0, "ok": False, "reason": "Still wrong.", "claim": "Margin expanded 200bps."}
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=[violation]):
        from tradingagents.graph.setup import GraphSetup
        gs = object.__new__(GraphSetup)
        gs.quick_thinking_llm = MagicMock()
        node = gs._make_rm_consistency_guard_node(gs.quick_thinking_llm)
        with pytest.raises(ValueError, match="unresolved.*violations"):
            node({
                "investment_plan": "- [HIGH] Margin expanded 200bps.",
                "fundamentals_report": "Margin compressed 270bps.",
                "_rm_consistency_attempt": 1,
            })


def test_guard_node_nok_regression_no_false_positive():
    """NOK historical range claim must NOT produce violations."""
    ok_results = [{"index": i, "ok": True} for i in range(5)]
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=ok_results):
        from tradingagents.graph.setup import GraphSetup
        gs = object.__new__(GraphSetup)
        gs.quick_thinking_llm = MagicMock()
        node = gs._make_rm_consistency_guard_node(gs.quick_thinking_llm)
        result = node({
            "investment_plan": (
                "• **Strongest Bull Evidence**\n"
                "  - [HIGH] NOK revenue accelerated from $4.39B in Q1 2025 to $6.13B in Q4 2025.\n"
                "  - [HIGH] NOK registered breakout accumulation at $12.92.\n"
                "  - [MED] NOK price consolidation holds above $10.76 support.\n"
                "• **Strongest Bear Evidence**\n"
                "  - [HIGH] NOK sequential revenue expansion from $4.39B to $6.13B.\n"
                "  - [MED] Macro regime degradation below +3/6 introduces volatility risk.\n"
            ),
            "fundamentals_report": "Q1 2025: $4.39B\nQ4 2025: $6.13B (+26.9% QoQ)\n",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "ok"
    assert result["consistency_violations"] == []


def test_guard_node_no_claims_extracted_passes_without_llm_call():
    """RM with no [HIGH]/[MED]/[LOW] bullets — guard delegates to check_claims_via_llm with empty list."""
    from unittest.mock import ANY
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=[]) as mock_check:
        from tradingagents.graph.setup import GraphSetup
        gs = object.__new__(GraphSetup)
        gs.quick_thinking_llm = MagicMock()
        node = gs._make_rm_consistency_guard_node(gs.quick_thinking_llm)
        result = node({
            "investment_plan": "Some narrative without claim markers.",
            "fundamentals_report": "Revenue: +15% YoY.",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "ok"
    mock_check.assert_called_once_with([], "Revenue: +15% YoY.", ANY)


def test_guard_node_violation_dict_has_no_index_key():
    """Violation stored in state has claim+reason only — no LLM-internal index."""
    violation_result = {"index": 0, "ok": False, "reason": "Fundamentals show compression.", "claim": "Margin expanded 200bps."}
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=[violation_result]):
        from tradingagents.graph.setup import GraphSetup
        gs = object.__new__(GraphSetup)
        gs.quick_thinking_llm = MagicMock()
        node = gs._make_rm_consistency_guard_node(gs.quick_thinking_llm)
        result = node({
            "investment_plan": "- [HIGH] Margin expanded 200bps.",
            "fundamentals_report": "Margin compressed 270bps.",
            "_rm_consistency_attempt": 0,
        })
    v = result["consistency_violations"][0]
    assert "index" not in v
    assert "claim" in v
    assert "reason" in v
