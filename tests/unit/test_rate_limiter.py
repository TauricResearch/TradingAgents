from unittest.mock import patch

from langchain_core.rate_limiters import InMemoryRateLimiter

from tradingagents.llm_clients import rate_limiter


def setup_function(_):
    rate_limiter.reset_rate_limiters()


def teardown_function(_):
    rate_limiter.reset_rate_limiters()


def _env(values: dict[str, str | None]):
    """Return a side_effect for get_env_value that reads from *values*."""

    def fake_get(key: str, default=None, **_kwargs):
        return values.get(key, default)

    return fake_get


def test_returns_none_when_rps_unconfigured():
    with patch.object(rate_limiter, "get_env_value", side_effect=_env({})):
        assert rate_limiter.get_rate_limiter("mid_think") is None


def test_unknown_tier_returns_none():
    with patch.object(rate_limiter, "get_env_value", side_effect=_env({})):
        assert rate_limiter.get_rate_limiter("ultra_think") is None


def test_returns_limiter_with_configured_rps():
    env = {"TRADINGAGENTS_MID_THINK_RATE_LIMIT_RPS": "0.5"}
    with patch.object(rate_limiter, "get_env_value", side_effect=_env(env)):
        limiter = rate_limiter.get_rate_limiter("mid_think")
    assert isinstance(limiter, InMemoryRateLimiter)
    assert limiter.requests_per_second == 0.5
    assert limiter.max_bucket_size == 1


def test_burst_and_check_interval_are_honored():
    env = {
        "TRADINGAGENTS_DEEP_THINK_RATE_LIMIT_RPS": "2",
        "TRADINGAGENTS_DEEP_THINK_RATE_LIMIT_BURST": "5",
        "TRADINGAGENTS_DEEP_THINK_RATE_LIMIT_CHECK_INTERVAL": "0.05",
    }
    with patch.object(rate_limiter, "get_env_value", side_effect=_env(env)):
        limiter = rate_limiter.get_rate_limiter("deep_think")
    assert limiter.requests_per_second == 2.0
    assert limiter.max_bucket_size == 5
    assert limiter.check_every_n_seconds == 0.05


def test_same_tier_returns_singleton():
    env = {"TRADINGAGENTS_QUICK_THINK_RATE_LIMIT_RPS": "1"}
    with patch.object(rate_limiter, "get_env_value", side_effect=_env(env)):
        first = rate_limiter.get_rate_limiter("quick_think")
        second = rate_limiter.get_rate_limiter("quick_think")
    assert first is second


def test_different_tiers_return_distinct_limiters():
    env = {
        "TRADINGAGENTS_QUICK_THINK_RATE_LIMIT_RPS": "1",
        "TRADINGAGENTS_MID_THINK_RATE_LIMIT_RPS": "0.5",
    }
    with patch.object(rate_limiter, "get_env_value", side_effect=_env(env)):
        quick = rate_limiter.get_rate_limiter("quick_think")
        mid = rate_limiter.get_rate_limiter("mid_think")
    assert quick is not mid
    assert quick.requests_per_second == 1.0
    assert mid.requests_per_second == 0.5


def test_zero_or_negative_rps_disables_limiter():
    for value in ("0", "-1", "abc", ""):
        rate_limiter.reset_rate_limiters()
        env = {"TRADINGAGENTS_SCANNER_RATE_LIMIT_RPS": value}
        with patch.object(rate_limiter, "get_env_value", side_effect=_env(env)):
            assert rate_limiter.get_rate_limiter("scanner") is None
