from tradingagents.graph.run_recorder import compute_cache_hit_ratio


def test_compute_cache_hit_ratio_handles_zero_and_nulls():
    assert compute_cache_hit_ratio(None, None) is None
    assert compute_cache_hit_ratio(0, 0) is None
    assert compute_cache_hit_ratio(30, 70) == 0.30
