"""Unit tests for the structured-output smoke helpers (issue #1216).

The smoke script (scripts/smoke_structured_output.py) should fail fast with
clear, actionable errors instead of an opaque traceback when a provider
credential is missing, an agent call raises, or a rendered output is empty.
These helpers keep that logic pure and unit-testable.
"""

from __future__ import annotations

import pytest

from tradingagents.testing.smoke_helpers import (
    check_structure,
    require_api_key,
    run_agent_call,
)

API_KEY_ENV = "TRADINGAGENTS_TEST_SMOKE_KEY"


@pytest.mark.unit
class TestRequireApiKey:
    def test_missing_key_raises_clear_error(self, monkeypatch, capsys):
        monkeypatch.delenv(API_KEY_ENV, raising=False)
        with pytest.raises(SystemExit) as exc:
            require_api_key(API_KEY_ENV, "openai")
        assert exc.value.code == 2
        # The message must name the env var and the provider so the user
        # knows exactly what to set.
        err = capsys.readouterr().err
        assert "TRADINGAGENTS_TEST_SMOKE_KEY" in err
        assert "openai" in err

    def test_present_key_returns_value(self, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "sk-test")
        assert require_api_key(API_KEY_ENV, "openai") == "sk-test"

    def test_blank_key_is_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "")
        with pytest.raises(SystemExit) as exc:
            require_api_key(API_KEY_ENV, "openai")
        assert exc.value.code == 2


@pytest.mark.unit
class TestRunAgentCall:
    def test_returns_result_on_success(self):
        def ok():
            return {"investment_plan": "plan"}

        result = run_agent_call("Research Manager", ok)
        assert result == {"investment_plan": "plan"}

    def test_raises_system_exit_on_exception(self, capsys):
        def boom():
            raise RuntimeError("provider timeout")

        with pytest.raises(SystemExit) as exc:
            run_agent_call("Trader", boom)
        assert exc.value.code == 2
        assert "Trader" in capsys.readouterr().err

    def test_empty_result_raises_clear_error(self, capsys):
        def empty():
            return {}

        with pytest.raises(SystemExit) as exc:
            run_agent_call("Portfolio Manager", empty)
        assert exc.value.code == 2
        assert "Portfolio Manager" in capsys.readouterr().err


@pytest.mark.unit
class TestCheckStructure:
    def test_all_markers_present_returns_empty_failures(self):
        failures = check_structure("Research Manager", "**Recommendation**: Buy", ["**Recommendation**:"])
        assert failures == []

    def test_missing_marker_reported_with_name_and_marker(self):
        failures = check_structure("Trader", "**Action**: Buy", ["FINAL TRANSACTION PROPOSAL:"])
        assert len(failures) == 1
        assert "Trader" in failures[0]
        assert "FINAL TRANSACTION PROPOSAL:" in failures[0]

    def test_empty_text_flags_every_marker(self):
        failures = check_structure("PM", "", ["**Rating**:", "**Executive Summary**:"])
        assert len(failures) == 2

    def test_multiple_missing_markers_all_reported(self):
        failures = check_structure("PM", "**Rating**: Hold", ["**Rating**:", "**Executive Summary**:", "**Investment Thesis**:"])
        assert len(failures) == 2
