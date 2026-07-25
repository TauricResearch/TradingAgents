from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from tradingagents.agents.utils.agent_utils import resolve_instrument_identity
from tradingagents.dataflows.errors import ProviderRateLimitedError
from tradingagents.dataflows.yahoo import yahoo_rate_limit_error
from tradingagents.instruments import (
    AssetType,
    FundType,
    InstrumentDescriptor,
    InstrumentNotFoundError,
)
from tradingagents.persistence import Database, Repository
from tradingagents.services.analysis_service import DemoAnalysisService, _demo_snapshot
from tradingagents.web.jobs import JobManager, JobRetryError
from tradingagents.web.yahoo_resilience import CachedYahooProvider


def request():
    return {
        "symbol": "SPY",
        "asset_type": "fund",
        "analysis_date": "2026-07-21",
        "benchmark_symbol": "SPY",
        "analysts": ["market", "social", "news", "fundamentals"],
    }


class EmptyTicker:
    def history(self, **_kwargs):
        return pd.DataFrame()


class LimitedTicker:
    def history(self, **_kwargs):
        raise YFRateLimitError()


def provider(repository, *, identity=lambda _symbol: {}, ticker=EmptyTicker, now=None):
    now = now or datetime(2026, 7, 24, tzinfo=UTC)
    return CachedYahooProvider(
        repository,
        identity_resolver=identity,
        ticker_factory=lambda _symbol: ticker(),
        clock=lambda: now,
    )


def test_explicit_yfinance_identity_throttle_is_not_an_instrument_miss():
    resolve_instrument_identity.cache_clear()
    class LimitedIdentityTicker:
        @property
        def info(self):
            raise YFRateLimitError()

    with patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as ticker:
        ticker.return_value = LimitedIdentityTicker()
        with pytest.raises(ProviderRateLimitedError) as raised:
            resolve_instrument_identity("SPY", raise_rate_limited=True)
    assert raised.value.code == "PROVIDER_RATE_LIMITED"


def test_price_probe_throttle_has_stable_code_and_no_instrument_not_found(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    with pytest.raises(ProviderRateLimitedError) as raised:
        provider(repository, ticker=LimitedTicker).resolve("SPY", "fund", "2026-07-21")
    assert raised.value.public_detail()["code"] == "PROVIDER_RATE_LIMITED"
    assert raised.value.cache_status == "miss"


def test_retry_after_is_exposed_only_when_the_provider_supplies_it():
    response = type(
        "Response",
        (),
        {"status_code": 429, "headers": {"Retry-After": "120"}},
    )()
    error = RuntimeError("provider rejected request")
    error.response = response
    limited = yahoo_rate_limit_error(error)
    assert limited and limited.public_detail()["retry_after"] == "120"
    assert "retry_after" not in ProviderRateLimitedError("yahoo_finance").public_detail()


def test_empty_identity_and_empty_price_probe_remains_a_true_not_found(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    with pytest.raises(InstrumentNotFoundError):
        provider(repository).resolve("NOPE", "auto", "2026-07-21")


def test_identity_cache_hit_avoids_duplicate_yahoo_lookup(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    calls = 0

    def identity(_symbol):
        nonlocal calls
        calls += 1
        return {"company_name": "SPDR", "quote_type": "ETF", "currency": "USD"}

    cached = provider(repository, identity=identity)
    assert cached.resolve("SPY", "auto", "2026-07-21").descriptor.asset_type.value == "fund"
    assert cached.resolve("SPY", "auto", "2026-07-21").cache_status == "hit"
    assert calls == 1


def test_expired_cache_is_not_used_as_current_data_and_is_reported_on_throttle(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    now = datetime(2026, 7, 24, tzinfo=UTC)
    repository.put_provider_cache(
        provider="yahoo_finance",
        symbol="SPY",
        capability="identity",
        request_params={},
        normalized_payload={"company_name": "Old SPY", "quote_type": "ETF"},
        source_reference="fixture",
        retrieved_at=(now - timedelta(days=2)).isoformat(),
        effective_at="2026-07-22",
        expires_at=(now - timedelta(seconds=1)).isoformat(),
    )

    def limited(_symbol):
        raise ProviderRateLimitedError("yahoo_finance")

    with pytest.raises(ProviderRateLimitedError) as raised:
        provider(repository, identity=limited, now=now).resolve("SPY", "auto", "2026-07-21")
    assert raised.value.cache_status == "expired"


def test_normalized_fund_snapshot_cache_preserves_source_times_and_avoids_refetch(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    calls = 0

    class SnapshotTicker:
        def __init__(self, _symbol):
            self.info = {}
            self.funds_data = type("Funds", (), {
                "top_holdings": pd.DataFrame(),
                "sector_weightings": {},
                "asset_classes": {},
            })()

        def history(self, **_kwargs):
            nonlocal calls
            calls += 1
            index = pd.date_range("2026-07-20", "2026-07-21", tz="UTC")
            return pd.DataFrame({"Close": [100.0, 101.0]}, index=index)

    instrument = InstrumentDescriptor(
        "SPY", "SPY", AssetType.FUND, FundType.ETF, currency="USD"
    )
    yahoo = CachedYahooProvider(
        repository,
        ticker_factory=SnapshotTicker,
        clock=lambda: datetime(2026, 7, 24, tzinfo=UTC),
    )
    first, first_status = yahoo.fund_snapshot(instrument, "2026-07-21", "SPY")
    calls_after_first = calls
    second, second_status = yahoo.fund_snapshot(instrument, "2026-07-21", "SPY")
    assert first_status == "miss" and second_status == "hit"
    assert calls == calls_after_first
    assert second["observed_at"] == first["observed_at"]
    assert second["cache_status"] == "hit"
    cached = repository.get_provider_cache(
        "yahoo_finance", "SPY", "fund_snapshot",
        {"analysis_date": "2026-07-21", "benchmark_symbol": "SPY"},
    )
    assert cached and len(cached.payload_hash) == 64
    assert "raw" not in cached.normalized_payload


def test_demo_snapshot_tracks_the_requested_analysis_date():
    snapshot = _demo_snapshot("SPY", "fund", "2026-07-24")
    assert snapshot and snapshot["price_series"][-1]["date"] == "2026-07-24"


def test_rate_limited_job_persists_terminal_event_trust_and_zero_usage(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))

    def preflight(_job, _request):
        raise ProviderRateLimitedError("yahoo_finance")

    manager = JobManager(DemoAnalysisService(delay=0), repository=repository, preflight=preflight)
    job = manager.create(request())
    manager.threads[job.id].join(timeout=2)
    restored = manager.get(job.id)
    assert restored.status == "provider_rate_limited"
    assert restored.error["code"] == "PROVIDER_RATE_LIMITED"
    assert repository.list_events(job.id)[-1].event_type == "analysis.provider_rate_limited"
    assert repository.latest_trust(job_id=job.id).reason_codes == ("PROVIDER_RATE_LIMITED",)
    usage = repository.list_usage(job_id=job.id)
    assert len(usage) == 1
    assert (usage[0].requests, usage[0].input_tokens, usage[0].output_tokens, usage[0].retries) == (0, 0, 0, 0)
    replay = "".join(manager.event_stream(restored))
    assert "analysis.provider_rate_limited" in replay


def test_retry_creates_new_linked_job_and_never_mutates_rate_limited_parent(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    attempts = 0

    def preflight(_job, value):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderRateLimitedError("yahoo_finance")
        return value

    manager = JobManager(DemoAnalysisService(delay=0), repository=repository, preflight=preflight)
    parent = manager.create(request())
    manager.threads[parent.id].join(timeout=2)
    child = manager.retry(parent)
    manager.threads[child.id].join(timeout=2)
    assert manager.get(parent.id).status == "provider_rate_limited"
    assert child.id != parent.id
    assert child.record.retry_of_job_id == parent.id
    assert child.record.retry_attempt == 1
    with pytest.raises(JobRetryError):
        manager.retry(child)
