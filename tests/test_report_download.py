import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import db
from backend.app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def ensure_completed_job_fixture():
    """Ensure at least one completed job and report exists in the DB for download testing."""
    fixture_id = "fixture-download-test-job"
    if not db.get_job(fixture_id):
        db.create_job({
            "id": fixture_id,
            "ticker": "XAUUSD",
            "trade_date": "2024-05-15",
            "asset_type": "stock",
            "analysts": ["market", "news"],
            "status": "completed",
            "progress": 100,
            "current_stage": "Completed",
            "decision_signal": "Strong Buy",
        })
    if not db.get_report(fixture_id):
        db.save_report({
            "job_id": fixture_id,
            "final_state": "{}",
            "complete_report_md": "# Institutional Analysis: XAUUSD\n**Final Recommendation: Strong Buy**\nGold shows strong consolidation above $2350.",
            "executive_summary": "Gold shows strong consolidation above $2350.",
            "recommendation": "Strong Buy",
            "market_report_md": "## Technical Analysis\nBreakout above 50-day moving average.",
            "sentiment_report_md": "## Market Sentiment\nNet long exposure increasing among asset managers.",
            "news_report_md": "## Macroeconomic News\nFed policy outlook supports safe-haven flows.",
            "fundamentals_report_md": "## Fundamentals\nCentral bank gold accumulation remains resilient.",
        })
    return fixture_id

def test_report_download_complete():
    job_id = "fixture-download-test-job"

    # Download complete report
    res = client.get(f"/api/v1/reports/{job_id}/download")
    assert res.status_code == 200
    assert "text/markdown" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert "TradingAgents_XAUUSD" in res.headers["content-disposition"]
    assert len(res.content) > 50

def test_report_download_tabs():
    job_id = "fixture-download-test-job"

    for tab in ["market", "sentiment", "news", "fundamentals"]:
        res = client.get(f"/api/v1/reports/{job_id}/download?tab={tab}")
        assert res.status_code == 200
        assert "text/markdown" in res.headers["content-type"]
        assert tab.capitalize() in res.headers["content-disposition"]
        assert len(res.content) > 30

def test_report_download_filename_sanitization():
    # Test special characters in ticker (e.g. BTC/USD, GC=F) are sanitized safely in filename
    special_job_id = "fixture-special-ticker-job"
    db.create_job({
        "id": special_job_id,
        "ticker": "GC=F/PRO:1",
        "trade_date": "2024/05/15",
        "asset_type": "crypto",
        "analysts": ["market"],
        "status": "completed",
    })
    db.save_report({
        "job_id": special_job_id,
        "final_state": "{}",
        "complete_report_md": "# Gold Futures Report",
    })

    res = client.get(f"/api/v1/reports/{special_job_id}/download")
    assert res.status_code == 200
    disposition = res.headers["content-disposition"]
    assert "attachment" in disposition
    # Ensure slash and equals are stripped or sanitized
    assert "/" not in disposition.split("filename=")[1]
    assert "=" not in disposition.split("filename=")[1].replace('"', '')

def test_report_download_not_found():
    res = client.get("/api/v1/reports/non-existent-uuid-12345/download")
    assert res.status_code == 404
