import json
import uuid
from fastapi.testclient import TestClient

from backend.app.core.database import db
from backend.app.main import app

client = TestClient(app)

def _create_mock_job(job_id: str, ticker: str = "AAPL", status: str = "completed"):
    job_record = {
        "id": job_id,
        "ticker": ticker,
        "trade_date": "2026-09-18",
        "asset_type": "stock",
        "analysts": ["market", "news"],
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.6",
        "quick_think_llm": "gpt-5.6-luna",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "output_language": "English",
        "status": status,
        "progress": 100 if status == "completed" else 50,
        "current_stage": "Completed" if status == "completed" else "Running",
    }
    db.create_job(job_record)
    return job_record

def test_single_job_deletion_and_cascade():
    job_id = str(uuid.uuid4())
    _create_mock_job(job_id, ticker="NVDA", status="completed")

    # Add mock events and mock report
    db.add_event(job_id, "stage_change", {"stage": "Research", "progress": 50})
    db.add_event(job_id, "final_decision", {"rating": "BUY", "progress": 100})
    db.save_report({
        "job_id": job_id,
        "final_state": json.dumps({"test": "data"}),
        "complete_report_md": "# Test Report NVDA",
        "recommendation": "BUY",
        "entry_price": 120.0,
        "target_price": 150.0,
    })

    # Verify events and report exist prior to deletion
    assert len(db.get_events(job_id)) == 2
    assert db.get_report(job_id) is not None

    # Perform DELETE via API
    res = client.delete(f"/api/v1/jobs/{job_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == job_id
    assert "deleted successfully" in data["message"].lower()

    # Verify DB cascade cleanup: job, events, and report are gone
    assert db.get_job(job_id) is None
    assert len(db.get_events(job_id)) == 0
    assert db.get_report(job_id) is None

def test_delete_non_existent_job():
    fake_id = str(uuid.uuid4())
    res = client.delete(f"/api/v1/jobs/{fake_id}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

def test_active_job_delete_protection():
    job_id = str(uuid.uuid4())
    _create_mock_job(job_id, ticker="TSLA", status="running")

    # Deleting running job without force should fail with 400
    res = client.delete(f"/api/v1/jobs/{job_id}")
    assert res.status_code == 400
    assert "cannot delete" in res.json()["detail"].lower()

    # Verify job is NOT deleted
    assert db.get_job(job_id) is not None

    # Deleting running job with force=True should succeed
    res_force = client.delete(f"/api/v1/jobs/{job_id}?force=true")
    assert res_force.status_code == 200
    assert db.get_job(job_id) is None

def test_batch_delete_jobs():
    id_1 = str(uuid.uuid4())
    id_2 = str(uuid.uuid4())
    id_3 = str(uuid.uuid4())

    _create_mock_job(id_1, ticker="MSFT", status="completed")
    _create_mock_job(id_2, ticker="GOOGL", status="failed")
    _create_mock_job(id_3, ticker="AMZN", status="cancelled")

    payload = {"job_ids": [id_1, id_2, id_3], "force": False}
    res = client.post("/api/v1/jobs/batch-delete", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["deleted_count"] == 3
    assert set(data["job_ids"]) == {id_1, id_2, id_3}

    assert db.get_job(id_1) is None
    assert db.get_job(id_2) is None
    assert db.get_job(id_3) is None

def test_batch_delete_preserves_running_jobs_safely():
    id_done = str(uuid.uuid4())
    id_active = str(uuid.uuid4())

    _create_mock_job(id_done, ticker="SPY", status="completed")
    _create_mock_job(id_active, ticker="QQQ", status="running")

    # Without force, active job should be preserved safely
    payload = {"job_ids": [id_done, id_active], "force": False}
    res = client.post("/api/v1/jobs/batch-delete", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["deleted_count"] == 1
    assert data["job_ids"] == [id_done]

    assert db.get_job(id_done) is None
    assert db.get_job(id_active) is not None

    # Clean up
    db.delete_job(id_active)

def test_clear_jobs_by_status():
    id_f1 = str(uuid.uuid4())
    id_f2 = str(uuid.uuid4())
    id_c = str(uuid.uuid4())

    _create_mock_job(id_f1, ticker="META", status="failed")
    _create_mock_job(id_f2, ticker="AMD", status="failed")
    _create_mock_job(id_c, ticker="INTC", status="completed")

    res = client.delete("/api/v1/jobs?status=failed")
    assert res.status_code == 200
    data = res.json()
    assert data["deleted_count"] >= 2

    assert db.get_job(id_f1) is None
    assert db.get_job(id_f2) is None
    assert db.get_job(id_c) is not None

    # Clean up
    db.delete_job(id_c)

def test_clear_all_finished_jobs():
    id_comp = str(uuid.uuid4())
    id_fail = str(uuid.uuid4())
    id_canc = str(uuid.uuid4())

    _create_mock_job(id_comp, ticker="COIN", status="completed")
    _create_mock_job(id_fail, ticker="SOL-USD", status="failed")
    _create_mock_job(id_canc, ticker="ETH-USD", status="cancelled")

    res = client.delete("/api/v1/jobs?all_finished=true")
    assert res.status_code == 200
    data = res.json()
    assert data["deleted_count"] >= 3

    assert db.get_job(id_comp) is None
    assert db.get_job(id_fail) is None
    assert db.get_job(id_canc) is None

def test_clear_jobs_missing_params():
    res = client.delete("/api/v1/jobs")
    assert res.status_code == 400

def test_clear_jobs_forbids_active_status():
    # Attempting to bulk-clear running or queued jobs must return 400
    res_run = client.delete("/api/v1/jobs?status=running")
    assert res_run.status_code == 400
    assert "cannot bulk clear active jobs" in res_run.json()["detail"].lower()

    res_que = client.delete("/api/v1/jobs?status=queued")
    assert res_que.status_code == 400
    assert "cannot bulk clear active jobs" in res_que.json()["detail"].lower()

def test_clear_jobs_invalid_status():
    res = client.delete("/api/v1/jobs?status=invalid_random_status")
    assert res.status_code == 400
    assert "invalid status" in res.json()["detail"].lower()

def test_batch_delete_empty_list():
    res = client.post("/api/v1/jobs/batch-delete", json={"job_ids": [], "force": False})
    assert res.status_code == 200
    assert res.json()["deleted_count"] == 0
    assert res.json()["job_ids"] == []

def test_batch_delete_mixed_nonexistent():
    valid_id = str(uuid.uuid4())
    fake_id = str(uuid.uuid4())
    _create_mock_job(valid_id, ticker="NVDA", status="completed")

    res = client.post("/api/v1/jobs/batch-delete", json={"job_ids": [valid_id, fake_id], "force": False})
    assert res.status_code == 200
    data = res.json()
    assert data["deleted_count"] == 1
    assert data["job_ids"] == [valid_id]
    assert db.get_job(valid_id) is None
