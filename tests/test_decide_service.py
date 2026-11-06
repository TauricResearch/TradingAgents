"""Tests for the TradingAgents HTTP decision service (hermes#213) --
scripts/service.py, and decide.py's run_decision() extraction that both the
CLI and the service share.

Context: news-gap-ml's containerized cron can no longer subprocess into this
venv directly (container filesystem isolation broke the sibling-directory
assumption -- every triggered decision silently failed from the 2026-07-15/16
container cutover onward). This service is the fix: news-gap-ml reaches
TradingAgents over a loopback HTTP call instead.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _load_module(name: str, filename: str):
    """scripts/ isn't a package (no __init__.py) -- load a script module
    directly by path, same pattern test_external_signal_context.py already
    uses for decide.py."""
    path = Path(__file__).parent.parent / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def service():
    return _load_module("tradingagents_service_under_test", "service.py")


@pytest.fixture
def client(service):
    return TestClient(service.app)


@pytest.mark.unit
class TestRunDecisionExtraction:
    """run_decision() must behave identically to decide.py's old inline
    main() body -- this is a pure extract-function refactor."""

    def test_run_decision_returns_expected_shape(self):
        decide = _load_module("tradingagents_decide_under_test", "decide.py")
        fake_final_state = {"final_trade_decision": "FINAL TRANSACTION PROPOSAL: **BUY**"}
        with patch.object(decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = (fake_final_state, "Buy")
            result = decide.run_decision("WIPRO.NS", "2026-07-16")

        assert result["ticker"] == "WIPRO.NS"
        assert result["trade_date"] == "2026-07-16"
        assert result["asset_type"] == "stock"
        assert result["rating"] == "Buy"
        assert result["final_trade_decision"] == fake_final_state["final_trade_decision"]
        assert "generated_at" in result
        assert "cost_usd" in result
        assert "token_usage" in result

    def test_run_decision_raises_on_failure(self):
        """CLI catches this and exits 1; the service catches it and returns 500."""
        decide = _load_module("tradingagents_decide_under_test", "decide.py")
        with patch.object(decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.side_effect = RuntimeError("LLM provider timeout")
            with pytest.raises(RuntimeError, match="LLM provider timeout"):
                decide.run_decision("WIPRO.NS", "2026-07-16")


@pytest.mark.unit
class TestServiceAuth:
    def test_health_requires_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_reports_deployed_version(self, client, monkeypatch):
        """hermes#218's cross-service health page reads this -- baked in via
        the Dockerfile's ARG/ENV APP_VERSION, defaults to 'dev' locally."""
        monkeypatch.setenv("APP_VERSION", "d94b57c")
        resp = client.get("/health")
        assert resp.json()["version"] == "d94b57c"

    def test_health_version_defaults_to_dev_when_unset(self, client, monkeypatch):
        monkeypatch.delenv("APP_VERSION", raising=False)
        resp = client.get("/health")
        assert resp.json()["version"] == "dev"

    def test_decide_rejects_missing_auth_header(self, client, service):
        service._SERVICE_SECRET = "real-secret"
        resp = client.post("/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"})
        assert resp.status_code == 403

    def test_decide_rejects_wrong_secret(self, client, service):
        service._SERVICE_SECRET = "real-secret"
        resp = client.post(
            "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert resp.status_code == 403

    def test_decide_fails_closed_when_secret_unconfigured(self, client, service):
        """An unset TRADINGAGENTS_SERVICE_SECRET must reject every request --
        never silently skip auth (same posture as hermes' _validate_webhook,
        issue #144)."""
        service._SERVICE_SECRET = ""
        resp = client.post(
            "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
            headers={"Authorization": "Bearer anything"},
        )
        assert resp.status_code == 403

    def test_decide_accepts_correct_secret(self, client, service):
        service._SERVICE_SECRET = "real-secret"
        with patch.object(service, "run_decision", return_value={"rating": "Hold"}):
            resp = client.post(
                "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
                headers={"Authorization": "Bearer real-secret"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"rating": "Hold"}


@pytest.mark.unit
class TestServiceDecideEndpoint:
    def test_decide_passes_request_fields_through(self, client, service):
        service._SERVICE_SECRET = "s"
        with patch.object(service, "run_decision", return_value={"rating": "Sell"}) as mock_run:
            client.post(
                "/decide",
                json={
                    "ticker": "WIPRO.NS", "trade_date": "2026-07-16",
                    "asset_type": "stock", "context": '{"side": "short"}',
                },
                headers={"Authorization": "Bearer s"},
            )
        mock_run.assert_called_once_with("WIPRO.NS", "2026-07-16", "stock", '{"side": "short"}')

    def test_decide_defaults_asset_type_and_context(self, client, service):
        service._SERVICE_SECRET = "s"
        with patch.object(service, "run_decision", return_value={"rating": "Hold"}) as mock_run:
            client.post(
                "/decide", json={"ticker": "NVDA", "trade_date": "2026-07-16"},
                headers={"Authorization": "Bearer s"},
            )
        mock_run.assert_called_once_with("NVDA", "2026-07-16", "stock", None)

    def test_decide_surfaces_failure_as_500(self, client, service):
        service._SERVICE_SECRET = "s"
        with patch.object(service, "run_decision", side_effect=RuntimeError("LLM provider timeout")):
            resp = client.post(
                "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
                headers={"Authorization": "Bearer s"},
            )
        assert resp.status_code == 500
        assert "LLM provider timeout" in resp.json()["detail"]

    def test_decide_missing_required_field_is_422(self, client, service):
        service._SERVICE_SECRET = "s"
        resp = client.post(
            "/decide", json={"ticker": "WIPRO.NS"},  # missing trade_date
            headers={"Authorization": "Bearer s"},
        )
        assert resp.status_code == 422


@pytest.mark.unit
class TestStructuredDecisionFields:
    """TradingAgents#19 step 4: the structured scorer's number and gate reason
    have to reach the persisted decision, or every calibration question costs
    another billed batch (27 of 28 post-#21-fix retro rows have no score)."""

    def _decide(self):
        return _load_module("tradingagents_decide_under_test", "decide.py")

    def _factors(self, **over):
        from tradingagents.agents.schemas import FactorExtraction
        base = {
            "dated_catalyst_present": True, "catalyst_hours_to_resolution": 3.0,
            "technical_direction": 0.4, "technical_confidence": 0.6,
            "sentiment_direction": 0.2, "sentiment_confidence": 0.5,
            "risk_flags": ["fii_outflows"],
        }
        base.update(over)
        return FactorExtraction(**base)

    def test_absent_for_debate_and_off_modes(self):
        """Those modes have no scorer -- the persisted shape must not gain
        null columns that look like a failed extraction."""
        decide = self._decide()
        assert decide.structured_decision_fields({"final_trade_decision": "x"}) == {}
        assert decide.structured_decision_fields({"extracted_factors": None}) == {}

    def test_carries_score_rating_reason_and_raw_factors(self):
        decide = self._decide()
        fields = decide.structured_decision_fields({
            "extracted_factors": self._factors(),
            "structured_rating": "Hold",
            "structured_score": 0.18,
            "structured_reason": "Combined confidence-weighted score +0.18 ...",
        })

        assert fields["structured_rating"] == "Hold"
        assert fields["structured_score"] == 0.18
        assert "confidence-weighted score" in fields["structured_reason"]
        # The raw factors matter as much as the score: refitting thresholds
        # means recomputing ratings from the inputs, not the output.
        assert fields["structured_factors"]["technical_direction"] == 0.4
        assert fields["structured_factors"]["catalyst_hours_to_resolution"] == 3.0
        assert fields["structured_factors"]["risk_flags"] == ["fii_outflows"]

    def test_factors_are_json_serialisable(self):
        """These land in a .jsonl -- a bare pydantic object would blow up the
        writer at the end of an hour-long billed batch."""
        import json
        decide = self._decide()
        fields = decide.structured_decision_fields({
            "extracted_factors": self._factors(),
            "structured_rating": "Hold", "structured_score": 0.18, "structured_reason": "r",
        })
        assert json.loads(json.dumps(fields))["structured_factors"]["technical_confidence"] == 0.6

    def test_run_decision_merges_them_into_the_result(self):
        decide = self._decide()
        fake_final_state = {
            "final_trade_decision": "FINAL TRANSACTION PROPOSAL: **HOLD**",
            "extracted_factors": self._factors(),
            "structured_rating": "Hold",
            "structured_score": 0.18,
            "structured_reason": "Combined confidence-weighted score +0.18 ...",
        }
        with patch.object(decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = (fake_final_state, "Hold")
            result = decide.run_decision("KOTAKBANK.NS", "2026-07-17")

        assert result["structured_score"] == 0.18
        assert result["structured_factors"]["risk_flags"] == ["fii_outflows"]
        assert result["rating"] == "Hold"  # the existing shape is untouched

    def test_run_decision_shape_unchanged_without_a_scorer(self):
        decide = self._decide()
        with patch.object(decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = (
                {"final_trade_decision": "FINAL TRANSACTION PROPOSAL: **BUY**"}, "Buy")
            result = decide.run_decision("WIPRO.NS", "2026-07-16")

        assert not any(k.startswith("structured_") for k in result)
