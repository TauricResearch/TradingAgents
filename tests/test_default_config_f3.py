import pytest


@pytest.mark.unit
def test_default_config_has_f3_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    # Buffer / Redis
    assert C["sensing_redis_url"] == "redis://127.0.0.1:6379/0"
    assert C["sensing_ingest_stream"] == "ingest:raw"
    assert C["sensing_consumer_group"] == "triage"
    assert C["sensing_dead_stream"] == "ingest:dead"
    # Triage
    assert C["sensing_triage_consumers"] == 4
    assert C["sensing_triage_max_failures"] == 5
    # Dedupe
    assert C["sensing_dedupe_cosine_threshold"] == 0.92
    assert C["sensing_dedupe_window_hours"] == 24
    assert C["sensing_fingerprint_ttl_hours"] == 72
    # Watchlist gate
    assert C["sensing_watchlist_salience_threshold"] == 0.7
    assert C["sensing_watchlist_confidence_threshold"] == 0.8
    assert C["sensing_watchlist_ttl_days"] == 7
    # Adapter enablement (X off by default — see spec D8/R-F3-3)
    assert C["sensing_adapters_enabled"] == {
        "polygon_news": True, "telegram": True, "rss": True,
        "gdelt": True, "macro": True, "x": False,
    }
    # Salience cache
    assert C["sensing_salience_cache_ttl_seconds"] == 86400
    # Watchlist refresh inside triage consumer
    assert C["sensing_watchlist_refresh_seconds"] == 60
    # Embedder
    assert C["sensing_embedder_model"] == "sentence-transformers/all-MiniLM-L6-v2"
