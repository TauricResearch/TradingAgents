"""Unit tests for cli.doctor command."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.doctor import _mask_key, run_doctor
from cli.main import app


@pytest.mark.unit
class TestDoctor:
    def test_mask_key_not_configured(self):
        assert "Not configured" in _mask_key("")
        assert "Not configured" in _mask_key(None)

    def test_mask_key_short(self):
        masked = _mask_key("12345")
        assert "Configured" in masked
        assert "***" in masked

    def test_mask_key_long(self):
        masked = _mask_key("dummy_test_api_key_1234567890")
        assert "Configured" in masked
        assert "dumm" in masked
        assert "7890" in masked

    def test_run_doctor_executes_without_error(self, monkeypatch):
        monkeypatch.setattr("cli.doctor.vendor_reachable", lambda url: True)
        run_doctor()

    def test_doctor_cli_command(self, monkeypatch):
        runner = CliRunner()
        monkeypatch.setattr("cli.doctor.vendor_reachable", lambda url: True)
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "TradingAgents Health Check" in result.output
        assert "Python Version" in result.output
        assert "LLM Providers" in result.output
        assert "Data Vendors Connectivity" in result.output
