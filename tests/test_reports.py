from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tradingagents_service.api.app import create_app
import tradingagents_service.api.routes.reports as reports_routes


def test_reports_endpoint_lists_generated_markdown(monkeypatch, tmp_path):
    run_id = uuid4()
    report_path = tmp_path / "reports" / "IBM" / "2025-05-05" / f"{run_id}.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report\n", encoding="utf-8")
    monkeypatch.setattr(reports_routes, "REPORT_OUTPUT_ROOT", tmp_path)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/v1/reports")

    assert response.status_code == 200
    body = response.json()
    assert len(body["reports"]) == 1
    report = body["reports"][0]
    assert report["run_id"] == str(run_id)
    assert report["ticker"] == "IBM"
    assert report["trade_date"] == "2025-05-05"
    assert report["report_url"] == f"/v1/shadow-runs/{run_id}/report.md"
    assert report["bytes"] == len("# Report\n")
