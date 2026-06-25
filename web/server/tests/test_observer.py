from web.server.observer import Observer


def test_observer_enriches_tool_call_with_timing():
    obs = Observer()
    event = obs.enrich("tool_call", {"tool": "get_stock_data", "args": "AAPL"})
    assert "observer_ts" in event
    assert "observer_seq" in event


def test_observer_tracks_tool_duration():
    obs = Observer()
    obs.enrich("tool_call", {"tool": "get_stock_data"})
    end = obs.enrich("tool_result", {"tool": "get_stock_data", "summary": "..."})
    assert "duration_ms" in end["data"]
