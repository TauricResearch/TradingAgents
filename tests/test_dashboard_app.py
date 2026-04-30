from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tradingagents.dashboard.app import create_dashboard_app
from tradingagents.dashboard.storage import AnalysisRepository


@pytest.mark.unit
def test_dashboard_home_lists_saved_runs(tmp_path, sample_record):
    repository = AnalysisRepository(tmp_path)
    stored = repository.save(sample_record)
    app = create_dashboard_app(tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "NVDA" in response.text
    assert stored["decision_summary"] in response.text


@pytest.mark.unit
def test_dashboard_detail_page_renders_reports(tmp_path, sample_record):
    repository = AnalysisRepository(tmp_path)
    stored = repository.save(sample_record)
    app = create_dashboard_app(tmp_path)
    client = TestClient(app)

    response = client.get(f"/runs/{stored['run_id']}")

    assert response.status_code == 200
    assert "최종 포트폴리오 결정" in response.text
    assert "Maintain the current NVDA position" in response.text
