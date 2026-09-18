from fastapi.testclient import TestClient

from backend.app.core.cache import market_cache
from backend.app.core.database import db
from backend.app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "TradingAgents" in data["service"]

def test_config_options():
    response = client.get("/api/v1/config/options")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "models" in data
    assert "analysts" in data
    assert len(data["analysts"]) == 4

def test_job_lifecycle_and_concurrency():
    # 1. Create Job A (Stock)
    payload_a = {
        "ticker": "AAPL",
        "trade_date": "2024-05-10",
        "asset_type": "stock",
        "analysts": ["market", "news"],
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.6",
        "quick_think_llm": "gpt-5.6-luna",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1
    }
    res_a = client.post("/api/v1/jobs", json=payload_a)
    assert res_a.status_code == 201
    job_a = res_a.json()
    assert job_a["ticker"] == "AAPL"
    assert job_a["status"] in ("queued", "running")

    # 2. Create Job B (Crypto) concurrently
    payload_b = {
        "ticker": "BTC-USD",
        "trade_date": "2024-05-10",
        "asset_type": "crypto",
        "analysts": ["market", "social"],
        "llm_provider": "google",
        "deep_think_llm": "gemini-3.1-pro",
        "quick_think_llm": "gemini-3.1-flash",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1
    }
    res_b = client.post("/api/v1/jobs", json=payload_b)
    assert res_b.status_code == 201
    job_b = res_b.json()
    assert job_b["ticker"] == "BTC-USD"
    assert job_b["id"] != job_a["id"]

    # 3. List jobs
    list_res = client.get("/api/v1/jobs")
    assert list_res.status_code == 200
    jobs_list = list_res.json()["jobs"]
    ids = [j["id"] for j in jobs_list]
    assert job_a["id"] in ids
    assert job_b["id"] in ids

    # 4. Cancel Job B
    cancel_res = client.post(f"/api/v1/jobs/{job_b['id']}/cancel")
    assert cancel_res.status_code == 200

    # 5. Check events history
    db.add_event(job_a["id"], "stage_change", {"stage": "Test Stage", "progress": 50})
    events_res = client.get(f"/api/v1/jobs/{job_a['id']}/history")
    assert events_res.status_code == 200
    events = events_res.json()
    assert any(e["event_type"] == "stage_change" for e in events)

def test_shared_market_data_cache():
    # Verify cache isolation and sharing
    params = {"ticker": "TSLA", "range": "1y"}
    market_cache.set("technicals", params, {"rsi": 45.5, "macd": 1.2}, ttl_seconds=100)

    cached = market_cache.get("technicals", params)
    assert cached is not None
    assert cached["rsi"] == 45.5

    # Different params should miss
    miss = market_cache.get("technicals", {"ticker": "MSFT", "range": "1y"})
    assert miss is None

def test_full_analysis_pipeline_with_mock_graph(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    import backend.app.workers.runner as runner_module
    from backend.app.core.database import db

    # Create job in database
    job_id = "test-e2e-job-123"
    job_dict = {
        "id": job_id,
        "ticker": "NVDA",
        "trade_date": "2024-05-15",
        "asset_type": "stock",
        "analysts": ["market", "news"],
        "llm_provider": "mock_provider",
        "deep_think_llm": "mock-deep",
        "quick_think_llm": "mock-quick",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "output_language": "English",
    }
    db.create_job(job_dict)

    # Mock TradingAgentsGraph
    mock_graph_instance = MagicMock()
    mock_graph_instance.resolve_instrument_context.return_value = "NVDA - NVIDIA Corporation (NASDAQ)"
    mock_graph_instance.propagator.create_initial_state.return_value = {"ticker": "NVDA"}
    mock_graph_instance.propagator.get_graph_args.return_value = {}
    mock_graph_instance._memory_as_of.return_value = "2024-05-15"
    mock_graph_instance.memory_log.get_past_context.return_value = ""

    # Simulated graph streaming chunks
    chunks = [
        {"market_report": "### Technical Analysis\nRSI: 62.1\nBullish breakout detected."},
        {"news_report": "### News Sentiment\nQ1 earnings beat expectations by 15%."},
        {
            "investment_debate_state": {
                "current_response": "Bull Analyst: Accelerating AI datacenter revenue signals massive upside.",
                "count": 1,
                "judge_decision": "Overweight position recommended given secular AI tailwinds."
            }
        },
        {"trader_investment_plan": "Strategy: Long\nEntry Price: $120.50\nStop Loss: $110.00"},
        {
            "risk_debate_state": {
                "latest_speaker": "Conservative",
                "count": 1,
                "current_conservative_response": "Keep sizing moderate to withstand potential supply chain snags."
            }
        },
        {
            "final_trade_decision": "Recommendation: Strong Buy\nTarget Price: $150.00\nExecutive Summary: Exceptional Blackwell demand outweighs cyclical risks."
        }
    ]
    mock_graph_instance.graph.stream.return_value = iter(chunks)

    monkeypatch.setattr(runner_module, "TradingAgentsGraph", lambda *a, **kw: mock_graph_instance)

    # Execute job through job_manager
    import asyncio

    from backend.app.workers.job_manager import job_manager
    asyncio.run(job_manager._execute_job(job_dict))

    # Verify Job updated in DB
    updated_job = db.get_job(job_id)
    assert updated_job["status"] == "completed"
    assert updated_job["progress"] == 100
    assert updated_job["decision_signal"] == "Buy"

    # Verify Report API
    report_res = client.get(f"/api/v1/reports/{job_id}")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["recommendation"] == "Buy"
    assert report_data["entry_price"] == 120.50
    assert report_data["stop_loss"] == 110.00
    assert report_data["target_price"] == 150.00
    assert "NVDA" in report_data["ticker"]

    # Verify Report Tab API
    tab_res = client.get(f"/api/v1/reports/{job_id}/tabs/market")
    assert tab_res.status_code == 200
    tab_data = tab_res.json()
    assert "RSI: 62.1" in tab_data["content"]

    # Verify Memory API
    mem_res = client.get("/api/v1/memory/NVDA")
    assert mem_res.status_code == 200

def test_extract_price_level_utility():
    from backend.app.workers.runner import extract_price_level

    # Test range
    text_range = "Plan:\nEntry Price: $120.50 - $125.00\nStop Loss: $110.25\nTarget Price: $165.00"
    assert extract_price_level(text_range, ["Entry Price", "Entry"]) == 120.50
    assert extract_price_level(text_range, ["Stop Loss", "Stop"]) == 110.25
    assert extract_price_level(text_range, ["Target Price", "Price Target"]) == 165.00

    # Test formatted with comma
    text_comma = "Target Price: $1,250.75"
    assert extract_price_level(text_comma, ["Target Price"]) == 1250.75

    # Test missing
    assert extract_price_level("No levels here", ["Target"]) is None

def test_count_jobs_and_pagination():
    from backend.app.core.database import db

    total_initial = db.count_jobs()
    assert total_initial >= 1

    # List jobs pagination returns accurate total
    res = client.get("/api/v1/jobs?limit=2&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == total_initial
    assert len(data["jobs"]) <= 2

def test_thread_cancel_event_halts_runner():
    import threading
    from unittest.mock import MagicMock

    import backend.app.workers.runner as runner_module
    from backend.app.workers.runner import run_analysis_task

    cancel_event = threading.Event()
    cancel_event.set() # Already cancelled

    job_dict = {
        "id": "test-cancel-immediate",
        "ticker": "TSLA",
        "trade_date": "2024-05-15",
        "asset_type": "stock",
        "analysts": ["market"],
        "llm_provider": "mock",
    }

    mock_graph = MagicMock()
    # If not halted, this infinite iterator would never end
    def infinite_stream(*a, **kw):
        while True:
            yield {"stage": "loop"}
    mock_graph.graph.stream = infinite_stream
    runner_module.TradingAgentsGraph = lambda *a, **kw: mock_graph

    res = run_analysis_task(job_dict, cancel_event=cancel_event)
    assert res["status"] == "cancelled"

def test_api_keys_config_endpoints():
    # 1. GET keys status
    res = client.get("/api/v1/config/keys")
    assert res.status_code == 200
    data = res.json()
    assert "keys" in data
    assert any(k["provider"] == "openai" for k in data["keys"])
    assert any(k["provider"] == "fmp" for k in data["keys"])

    # 2. POST update a test key
    update_res = client.post(
        "/api/v1/config/keys",
        json={"keys": {"openai": "sk-proj-integration-test-key-12345"}}
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    openai_key = next(k for k in updated_data["keys"] if k["provider"] == "openai")
    assert openai_key["configured"] is True
    assert "..." in openai_key["preview"]
    assert openai_key["preview"].startswith("sk-")

    # 3. Clean up by clearing the test key
    cleanup_res = client.post(
        "/api/v1/config/keys",
        json={"keys": {"openai": ""}}
    )
    assert cleanup_res.status_code == 200
    cleaned_data = cleanup_res.json()
    openai_cleaned = next(k for k in cleaned_data["keys"] if k["provider"] == "openai")
    assert openai_cleaned["configured"] is False



