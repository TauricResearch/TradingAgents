from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
import requests

from tradingagents.china_funds import (
    ACCEPTANCE_CATALOG,
    AmbiguousFundError,
    ChinaFundService,
    FundAction,
    evaluate_actions,
)
from tradingagents.china_funds.cache import CachedChinaFundProvider
from tradingagents.china_funds.domain import TransactionStatus
from tradingagents.china_funds.eastmoney import EastmoneyFundProvider
from tradingagents.china_funds.service import default_registry
from tradingagents.china_funds.synthetic import SyntheticChinaFundProvider
from tradingagents.china_funds.trust import assess_snapshot, relevant_trading_days_between
from tradingagents.dataflows.errors import ProviderRateLimitedError, ProviderTimedOutError
from tradingagents.persistence import Database, Repository
from tradingagents.trust import assess_result_evidence


@pytest.fixture
def service():
    return ChinaFundService(default_registry(SyntheticChinaFundProvider()))


def test_all_acceptance_funds_resolve_by_code_and_exact_name(service):
    assert len(ACCEPTANCE_CATALOG) == 20
    for item in ACCEPTANCE_CATALOG:
        by_code = service.resolve(item.code)
        by_name = service.resolve(item.name)
        assert by_code.code == by_name.code == item.code
        assert by_code.share_class == item.share_class


def test_partial_name_search_requires_disambiguation_and_share_classes_remain_distinct(service):
    with pytest.raises(AmbiguousFundError) as exc:
        service.resolve("纳斯达克100")
    assert len(exc.value.candidates) >= 3
    a_class = service.resolve("012920")
    c_class = service.resolve("012922")
    assert a_class.code != c_class.code
    assert a_class.share_class != c_class.share_class
    assert a_class.parent_product_id == c_class.parent_product_id


def test_snapshot_excludes_future_nav_and_has_deterministic_metrics(service):
    cutoff = "2026-07-22"
    snapshot = service.snapshot("003516", cutoff)
    assert snapshot.nav_history
    assert all(point.date <= cutoff for point in snapshot.nav_history)
    assert {item["name"] for item in snapshot.metrics} == {
        "total_return",
        "annualized_volatility",
        "maximum_drawdown",
    }
    assert snapshot.trust["level"] == "trusted"


def test_qdii_policy_records_lag_and_never_implies_known_execution_nav(service):
    saturday = date(2026, 7, 25)
    snapshot = service.snapshot("016453", saturday.isoformat())
    assert snapshot.identity.is_qdii
    assert snapshot.qdii_context["latest_market_move_reflected"] == "unknown"
    assert snapshot.qdii_context["overseas_market_cutoff"] <= saturday.isoformat()
    assert snapshot.trust["policy"]["qdii_nav_max_lag"] == 5


def test_action_gate_blocks_unknown_status_units_fees_and_unconfirmed_conversion(service):
    snapshot = service.snapshot("003516", date.today().isoformat())
    status = TransactionStatus("closed", "unknown", datetime.now(UTC).isoformat())
    degraded = replace(snapshot, transaction_status=status, fees=())
    degraded = replace(degraded, trust={**snapshot.trust, "executable": True, "level": "trusted"})
    result = evaluate_actions(degraded, intended_action="convert", sales_platform="example")
    assert not result.executable
    assert "SUBSCRIPTION_CLOSED" in result.blocked_actions["subscribe"]
    assert "CONFIRMED_UNITS_REQUIRED" in result.blocked_actions["redeem_partial"]
    assert "FEE_RULE_UNKNOWN" in result.blocked_actions["redeem_partial"]
    assert "PLATFORM_CONVERSION_UNCONFIRMED" in result.blocked_actions["convert"]


def test_conversion_requires_explicit_platform_support(service):
    snapshot = service.snapshot("012920", date.today().isoformat())
    target = service.snapshot("012922", date.today().isoformat())
    result = evaluate_actions(
        snapshot,
        intended_action="convert",
        confirmed_units="100.5",
        holding_days=100,
        minimum_holding_known=True,
        sales_platform="confirmed-fixture-platform",
        conversion_supported=True,
        target_snapshot=target,
    )
    assert result.executable
    assert FundAction.CONVERT in result.allowed_actions
    assert result.target_code == "012922"
    assert result.supporting_evidence
    assert result.friction


def test_conversion_rejects_missing_or_unrelated_target_share_class(service):
    source = service.snapshot("012920", date.today().isoformat())
    unrelated = service.snapshot("003516", date.today().isoformat())
    context = {
        "intended_action": "convert",
        "confirmed_units": "100",
        "holding_days": 100,
        "minimum_holding_known": True,
        "sales_platform": "confirmed-fixture-platform",
        "conversion_supported": True,
    }
    missing = evaluate_actions(source, **context)
    mismatch = evaluate_actions(source, target_snapshot=unrelated, **context)
    assert "CONVERSION_TARGET_REQUIRED" in missing.blocked_actions["convert"]
    assert "CONVERSION_TARGET_SHARE_CLASS_MISMATCH" in mismatch.blocked_actions["convert"]


def test_subscribe_amount_and_partial_redemption_fraction_are_required(service):
    snapshot = service.snapshot("003516", date.today().isoformat())
    subscribe = evaluate_actions(snapshot, intended_action="subscribe")
    assert "SUBSCRIPTION_AMOUNT_REQUIRED" in subscribe.blocked_actions["subscribe"]
    partial = evaluate_actions(
        snapshot,
        intended_action="redeem_partial",
        confirmed_units="100",
        holding_days=100,
    )
    assert "REDEMPTION_FRACTION_REQUIRED" in partial.blocked_actions["redeem_partial"]


def test_missing_holdings_lowers_global_trust_without_blocking_supported_action(service):
    snapshot = service.snapshot("003516", date.today().isoformat())
    degraded = replace(snapshot, holdings=(), trust={})
    degraded = replace(degraded, trust=assess_snapshot(degraded))
    assert degraded.trust["level"] == "usable_with_warning"
    assert not degraded.trust["executable"]

    evaluation = evaluate_actions(degraded, intended_action="subscribe", amount="1000")
    assert evaluation.executable
    assert FundAction.SUBSCRIBE in evaluation.allowed_actions

    _observation, persisted_trust = assess_result_evidence(
        {"china_fund_snapshot": degraded.to_dict()}
    )
    assert persisted_trust.level == "usable_with_warning"
    assert not persisted_trust.executable


def test_stale_transaction_status_blocks_transactions_but_not_hold(service):
    snapshot = service.snapshot("003516", date.today().isoformat())
    stale_status = replace(snapshot.transaction_status, observed_at="2026-01-01T00:00:00+00:00")
    degraded = replace(snapshot, transaction_status=stale_status, trust={})
    degraded = replace(degraded, trust=assess_snapshot(degraded))

    subscribe = evaluate_actions(degraded, intended_action="subscribe", amount="1000")
    hold = evaluate_actions(degraded, intended_action="hold")
    assert "TRANSACTION_STATUS_STALE" in subscribe.blocked_actions["subscribe"]
    assert not subscribe.executable
    assert hold.executable


def test_future_analysis_date_is_rejected_before_provider_access(service):
    future = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="cannot be in the future"):
        service.snapshot("003516", future.isoformat())


def test_normalized_capability_cache_hit_and_expired_fallback(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    cached_provider = CachedChinaFundProvider(SyntheticChinaFundProvider(), repository)
    cached_service = ChinaFundService(default_registry(cached_provider))
    cutoff = date.today().isoformat()

    first = cached_service.snapshot("003516", cutoff)
    second = cached_service.snapshot("003516", cutoff)
    assert first.capability_status["nav"] == "available"
    assert set(second.capability_status.values()) == {"cached"}
    assert first.evidence[0].retrieved_at == second.evidence[0].retrieved_at

    class FailingProvider:
        provider_id = "synthetic_phase3_fixture"

        def __getattr__(self, name):
            if name.startswith("fetch_"):
                return lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("synthetic provider outage")
                )
            raise AttributeError(name)

    cached_provider.provider = FailingProvider()
    with repository.database.connect() as conn:
        conn.execute(
            "UPDATE provider_cache SET expires_at=?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )

    expired = cached_service.snapshot("003516", cutoff)
    assert set(expired.capability_status.values()) == {"expired"}
    assert expired.trust["level"] == "insufficient"
    assert not expired.trust["executable"]
    assert expired.evidence
    assert all(item.freshness_status == "stale" for item in expired.evidence)
    assert any("CACHE_EXPIRED" in item.normalization_warnings for item in expired.evidence)


def test_relevant_trading_days_skip_configured_market_holidays():
    start = date(2026, 4, 3)
    end = date(2026, 4, 7)
    assert relevant_trading_days_between(start, end) == 1


class Response:
    def __init__(self, text, status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_eastmoney_adapter_parses_dates_status_profile_and_future_cutoff():
    search = '{"Datas":[{"CODE":"003516","NAME":"国泰融安多策略灵活配置混合A","FundBaseInfo":{"FTYPE":"混合型-灵活","JJGS":"国泰基金","JJJL":"Fixture Manager"}}]}'
    detail = (
        'var fS_name="国泰融安多策略灵活配置混合A";'
        'var fund_sourceRate="1.50";var fund_minsg="10";'
        'var Data_netWorthTrend=[{"x":1784649600000,"y":1.1},{"x":1784822400000,"y":1.2}];'
        "var Data_ACWorthTrend=[[1784649600000,1.1],[1784822400000,1.2]];"
        'var Data_currentFundManager=[{"name":"Fixture Manager"}];'
        'var Data_assetAllocation={"series":[{"name":"股票占净比","data":[80]}],"categories":["2026-06-30"]};'
    )
    status = 'var db={datas:[["003516","name","x","1","1","1","1","0","0","开放申购","开放赎回"]],count:["1"],showday:["2026-07-24","2026-07-23"]}'
    profile = '<table class="info w790"><tr><th>最高赎回费率</th><td>1.50%</td><th>业绩比较基准</th><td>沪深300指数收益率*60%</td></tr></table>'

    def get(url, **_kwargs):
        if "FundSearch" in url:
            return Response(search)
        if "pingzhongdata" in url:
            return Response(detail)
        if "Fund_JJJZ" in url:
            return Response(status)
        return Response(profile)

    provider = EastmoneyFundProvider(http_get=get)
    assert provider.fetch_identity("003516").value["fund_company"] == "国泰基金"
    nav = provider.fetch_nav("003516", "2026-07-22").value
    assert [point.date for point in nav] == ["2026-07-21"]
    transaction = provider.fetch_transaction_status("003516").value
    assert transaction.subscription == "开放申购" and transaction.redemption == "开放赎回"
    assert provider.fetch_benchmark("003516").value.disclosed_text == "沪深300指数收益率*60%"
    assert provider.fetch_fees("003516").value


def test_eastmoney_rate_limit_and_timeout_remain_explicit_provider_failures():
    limited = EastmoneyFundProvider(
        http_get=lambda *_args, **_kwargs: Response(
            "rate limited", status_code=429, headers={"Retry-After": "30"}
        )
    )
    with pytest.raises(ProviderRateLimitedError) as rate_error:
        limited.fetch_identity("003516")
    assert rate_error.value.provider == "eastmoney_public"
    assert rate_error.value.retry_after == "30"

    def timeout(*_args, **_kwargs):
        raise requests.Timeout("fixture timeout")

    timed_out = EastmoneyFundProvider(timeout_seconds=4, http_get=timeout)
    with pytest.raises(ProviderTimedOutError) as timeout_error:
        timed_out.fetch_nav("003516", date.today().isoformat())
    assert timeout_error.value.provider == "eastmoney_public"
    assert timeout_error.value.timeout_seconds == 4


def test_capability_failure_preserves_other_snapshot_groups():
    class PartialProvider(SyntheticChinaFundProvider):
        def fetch_disclosure(self, code):
            raise RuntimeError("fixture capability outage")

    service = ChinaFundService(default_registry(PartialProvider()))
    snapshot = service.snapshot("003516", date.today().isoformat())
    assert snapshot.nav_history
    assert snapshot.transaction_status is not None
    assert snapshot.capability_status["disclosure"] == "unavailable"
    assert not snapshot.holdings
    assert any("DISCLOSURE_UNAVAILABLE" in warning for warning in snapshot.warnings)


@pytest.mark.parametrize("lag,expected", [(2, "trusted"), (3, "insufficient")])
def test_domestic_nav_freshness_threshold_is_trading_day_based(service, lag, expected):
    cutoff = date.today()
    while cutoff.weekday() >= 5:
        cutoff -= timedelta(days=1)
    snapshot = service.snapshot("003516", cutoff.isoformat())
    latest = cutoff
    counted = 0
    while counted < lag:
        latest -= timedelta(days=1)
        if latest.weekday() < 5:
            counted += 1
    stale_history = (
        *snapshot.nav_history[:-1],
        replace(snapshot.nav_history[-1], date=latest.isoformat()),
    )
    result = assess_snapshot(replace(snapshot, nav_history=stale_history, trust={}))
    assert result["level"] == expected
