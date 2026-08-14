"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

import json
from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"judge_decision": "RM PLAN"},
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"judge_decision": "PM DECISION"},
    }


def _full_state_for_log():
    state = _state()
    state.update(
        {
            "company_of_interest": "AAPL",
            "trade_date": "2026-01-10",
            "sentiment_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": "",
                "bear_history": "",
                "history": "",
                "current_response": "",
                "judge_decision": "RM PLAN",
            },
            "risk_debate_state": {
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "history": "",
                "judge_decision": "PM DECISION",
            },
            "investment_plan": "Research plan.",
            "final_trade_decision": "PM DECISION",
        }
    )
    return state


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "PM DECISION"
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
    assert "MKT" in complete and "PM DECISION" in complete


@pytest.mark.unit
def test_write_report_tree_uses_canonical_final_trade_decision(tmp_path):
    state = _state()
    state["risk_debate_state"]["judge_decision"] = "BUY: stale portfolio manager decision"
    state["final_trade_decision"] = "BLOCKED: evidence strict mode prevented action"

    out = write_report_tree(state, "AAPL", tmp_path)

    decision = (tmp_path / "5_portfolio" / "decision.md").read_text()
    complete = out.read_text()
    assert decision == "BLOCKED: evidence strict mode prevented action"
    assert "BLOCKED: evidence strict mode prevented action" in complete
    assert "BUY: stale portfolio manager decision" not in complete


@pytest.mark.unit
def test_write_report_tree_emits_evidence_audit(tmp_path):
    state = _state()
    state.update(
        {
            "evidence_ledger": {
                "items": [
                    {
                        "evidence_id": "EVD-MKT-TEST",
                        "source": "verified_market_snapshot",
                        "title": "Verified | Market\nSnapshot",
                        "as_of_date": "2026-01-10",
                        "payload": {
                            "latest_date": "2026-01-10",
                            "latest_ohlcv": {"Close": 100.0, "Volume": 123456},
                            "look_back_days": 20,
                            "rows": [{"large": "payload stays in json only"}],
                        },
                    }
                ]
            },
            "citation_verification": {
                "passed": True,
                "cited_ids": ["EVD-MKT-TEST"],
                "unknown_ids": [],
                "missing_required": False,
                "warnings": [],
            },
            "quantitative_anchors": [
                {
                    "anchor_id": "QA-TEST",
                    "symbol": "AAPL",
                    "as_of_date": "2026-01-10",
                    "current_price": 100.0,
                    "evidence_id": "EVD-MKT-TEST",
                }
            ],
            "math_guardrail_events": [
                {
                    "rule_id": "price_target_multiple",
                    "status": "warn",
                    "message": "Price target is materially outside the anchor.",
                    "action": "review_target_price",
                    "evidence_id": "EVD-MKT-TEST",
                }
            ],
            "evidence_warnings": ["One analyst claim lacked a citation."],
            "evidence_strict_mode": "block",
            "evidence_strict_blocked": True,
            "evidence_blocking_reasons": ["price_target_multiple: target too far"],
            "evidence_decision_status": "blocked",
            "evidence_actionable": False,
            "original_final_trade_decision": "BUY: stale portfolio manager decision",
        }
    )

    out = write_report_tree(state, "AAPL", tmp_path)

    complete = out.read_text()
    assert "## VI. Evidence Audit" in complete
    assert "**Citation Verification**: Passed" in complete
    assert "**Quantitative Anchors**: 1" in complete
    assert "**Math Guardrail Events**: 1" in complete
    assert "**Evidence Strict Status**: block / blocked" in complete
    assert "**Strict Mode Blocked**" not in complete
    assert "target too far" in complete
    assert "One analyst claim lacked a citation." in complete
    audit_markdown = (tmp_path / "6_evidence" / "audit.md").read_text()
    for markdown in (complete, audit_markdown):
        assert "### Evidence Ledger" in markdown
        assert (
            "| [EVD-MKT-TEST](#evidence-1-evd-mkt-test) | "
            "Verified \\| Market Snapshot | verified_market_snapshot | "
            "2026-01-10 | latest_date=2026-01-10; Close=100.0; "
            "Volume=123456; look_back_days=20 |"
        ) in markdown
        assert "#### Evidence 1 EVD-MKT-TEST" in markdown
        assert "### Quantitative Anchors" in markdown
        assert (
            "| QA-TEST | AAPL | 100.0 | 2026-01-10 | "
            "[EVD-MKT-TEST](#evidence-1-evd-mkt-test) |"
        ) in markdown
        assert "### Math Guardrail Events" in markdown
        assert (
            "| price_target_multiple | warn | "
            "Price target is materially outside the anchor.; "
            "action=review_target_price; "
            "[EVD-MKT-TEST](#evidence-1-evd-mkt-test) |"
        ) in markdown
    audit = json.loads((tmp_path / "evidence_audit.json").read_text())
    assert audit["evidence_ledger"]["items"][0]["evidence_id"] == "EVD-MKT-TEST"
    assert audit["evidence_ledger"]["items"][0]["payload"]["rows"] == [
        {"large": "payload stays in json only"}
    ]
    assert audit["citation_verification"]["passed"] is True
    assert audit["quantitative_anchors"][0]["current_price"] == 100.0
    assert audit["math_guardrail_events"][0]["status"] == "warn"
    assert audit["evidence_warnings"] == ["One analyst claim lacked a citation."]
    assert audit["evidence_strict_mode"] == "block"
    assert audit["evidence_strict_blocked"] is True
    assert audit["evidence_decision_status"] == "blocked"
    assert audit["evidence_actionable"] is False
    assert audit["original_final_trade_decision"] == "BUY: stale portfolio manager decision"


@pytest.mark.unit
def test_write_report_tree_escapes_special_evidence_ids_and_avoids_anchor_collisions(
    tmp_path,
):
    long_scalar = "X" * 180
    state = _state()
    state.update(
        {
            "evidence_ledger": {
                "items": [
                    {
                        "evidence_id": "EVD MKT/TEST[1]",
                        "source": "news",
                        "title": "Special ID",
                        "as_of_date": "2026-01-10",
                        "payload": {"headline": long_scalar, "quality": "primary"},
                    },
                    {
                        "evidence_id": "EVD-MKT-TEST-1",
                        "source": "filing",
                        "title": "Colliding ID",
                        "as_of_date": "2026-01-11",
                        "payload": {"form": "10-K"},
                    },
                ]
            },
            "quantitative_anchors": [
                {
                    "anchor_id": "QA-SPECIAL",
                    "symbol": "AAPL",
                    "current_price": 100.0,
                    "as_of_date": "2026-01-10",
                    "evidence_id": "EVD MKT/TEST[1]",
                }
            ],
            "math_guardrail_events": [
                {
                    "rule_id": "special_id_check",
                    "status": "warn",
                    "message": "Uses special evidence id.",
                    "evidence_id": "EVD MKT/TEST[1]",
                }
            ],
        }
    )

    out = write_report_tree(state, "AAPL", tmp_path)

    complete = out.read_text()
    audit_markdown = (tmp_path / "6_evidence" / "audit.md").read_text()
    for markdown in (complete, audit_markdown):
        assert "[EVD MKT/TEST\\[1\\]](#evidence-1-evd-mkt-test-1)" in markdown
        assert "[EVD-MKT-TEST-1](#evidence-2-evd-mkt-test-1)" in markdown
        assert "#### Evidence 1 EVD MKT/TEST[1]" in markdown
        assert "#### Evidence 2 EVD-MKT-TEST-1" in markdown
        assert (
            "| QA-SPECIAL | AAPL | 100.0 | 2026-01-10 | "
            "[EVD MKT/TEST\\[1\\]](#evidence-1-evd-mkt-test-1) |"
        ) in markdown
        assert (
            "Uses special evidence id.; "
            "[EVD MKT/TEST\\[1\\]](#evidence-1-evd-mkt-test-1)"
        ) in markdown
        assert long_scalar not in markdown
        assert f"headline={'X' * 117}..." in markdown

    audit = json.loads((tmp_path / "evidence_audit.json").read_text())
    assert audit["evidence_ledger"]["items"][0]["payload"]["headline"] == long_scalar


@pytest.mark.unit
def test_write_report_tree_renders_no_math_guardrail_events(tmp_path):
    state = _state()
    state.update(
        {
            "evidence_ledger": {
                "items": [
                    {
                        "evidence_id": "EVD-NEWS-TEST",
                        "source": "news",
                        "title": "News Summary",
                        "as_of_date": "2026-01-10",
                        "payload": {"headline": "Guidance reaffirmed", "quality": "primary"},
                    }
                ]
            },
            "quantitative_anchors": [],
            "math_guardrail_events": [],
        }
    )

    out = write_report_tree(state, "AAPL", tmp_path)

    complete = out.read_text()
    audit_markdown = (tmp_path / "6_evidence" / "audit.md").read_text()
    for markdown in (complete, audit_markdown):
        assert "**Math Guardrail Events**: 0" in markdown
        assert "### Math Guardrail Events\n\nNone." in markdown


@pytest.mark.unit
def test_state_log_persists_evidence_audit(tmp_path):
    state = _full_state_for_log()
    state["evidence_ledger"] = {"items": [{"evidence_id": "EVD-MKT-TEST"}]}
    state["citation_verification"] = {"passed": True, "cited_ids": ["EVD-MKT-TEST"]}
    state["quantitative_anchors"] = [{"anchor_id": "QA-TEST", "current_price": 100.0}]
    state["math_guardrail_events"] = [{"rule_id": "price_target_multiple", "status": "pass"}]
    state["evidence_warnings"] = []

    mock_self = SimpleNamespace(
        config={"results_dir": str(tmp_path)},
        ticker="AAPL",
        log_states_dict={},
    )
    TradingAgentsGraph._log_state(mock_self, "2026-01-10", state)

    log_path = tmp_path / "AAPL" / "TradingAgentsStrategy_logs" / "full_states_log_2026-01-10.json"
    payload = json.loads(log_path.read_text())
    assert payload["evidence_audit"]["evidence_ledger"]["items"][0]["evidence_id"] == "EVD-MKT-TEST"
    assert payload["evidence_audit"]["citation_verification"]["passed"] is True
    assert payload["evidence_audit"]["quantitative_anchors"][0]["current_price"] == 100.0


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    # Unbound: with an explicit save_path, the method doesn't touch self/config.
    out = TradingAgentsGraph.save_reports(None, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    mock_self = SimpleNamespace(config={"results_dir": str(tmp_path)})
    out = TradingAgentsGraph.save_reports(mock_self, _state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")
