from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dashboard.batch import build_batch_config, run_batch_analysis


@pytest.mark.unit
def test_build_batch_config_defaults_to_korean_output(tmp_path):
    config = build_batch_config(tmp_path)
    assert config["output_language"] == "Korean"


@pytest.mark.unit
def test_run_batch_analysis_saves_each_result(tmp_path, sample_final_state):
    mock_graph = MagicMock()
    mock_graph.propagate.side_effect = [
        (dict(sample_final_state, company_of_interest="NVDA"), "Hold"),
        (dict(sample_final_state, company_of_interest="AAPL"), "Hold"),
    ]

    with patch("tradingagents.dashboard.batch.TradingAgentsGraph", return_value=mock_graph):
        summary = run_batch_analysis(
            ["NVDA", "AAPL"],
            "2024-05-10",
            artifact_dir=tmp_path,
        )

    assert summary["completed"] == 2
    assert summary["failed"] == []
    assert len(summary["run_ids"]) == 2
    assert (tmp_path / "dashboard.db").exists()
    assert len(list((tmp_path / "runs").glob("*.json"))) == 2


@pytest.mark.unit
def test_run_batch_analysis_collects_failures(tmp_path, sample_final_state):
    mock_graph = MagicMock()
    mock_graph.propagate.side_effect = [
        (dict(sample_final_state, company_of_interest="NVDA"), "Hold"),
        RuntimeError("boom"),
    ]

    with patch("tradingagents.dashboard.batch.TradingAgentsGraph", return_value=mock_graph):
        summary = run_batch_analysis(
            ["NVDA", "AAPL"],
            "2024-05-10",
            artifact_dir=tmp_path,
        )

    assert summary["completed"] == 1
    assert len(summary["failed"]) == 1
    assert summary["failed"][0]["ticker"] == "AAPL"
