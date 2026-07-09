"""Tests for expanded wrong-identity detection."""

import pytest

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.evidence import (
    EvidenceGateError,
    _find_wrong_identity_hits,
    _get_wrong_identity_hints,
    _names_are_related,
    evaluate_and_enrich_evidence,
)


def _a_share_profile():
    return {
        "ticker": "000001.SZ",
        "symbol": "000001",
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "full_name": "平安银行股份有限公司",
        "industry": "银行",
        "exchange": "深圳证券交易所",
    }


def _yfinance_profile():
    return {
        "ticker": "002396.SZ",
        "symbol": "002396",
        "ts_code": "002396.SZ",
        "name": "FUJIAN STAR-NET COMMUNICATION C",
        "full_name": "Fujian Star-net Communication Co., LTD.",
        "industry": "Communication Equipment",
        "exchange": "深圳证券交易所",
        "profile_source": "yfinance",
    }


# ---------------------------------------------------------------------------
# _get_wrong_identity_hints
# ---------------------------------------------------------------------------


class TestGetWrongIdentityHints:
    def test_includes_built_in(self):
        hints = _get_wrong_identity_hints()
        assert "恒瑞医药" in hints
        assert "安洁科技" in hints

    def test_includes_config_additions(self):
        set_config({"wrong_identity_hints": ["中信证券", "招商银行"]})
        hints = _get_wrong_identity_hints()
        assert "中信证券" in hints
        assert "招商银行" in hints
        assert "恒瑞医药" in hints  # built-in still present
        set_config({"wrong_identity_hints": []})

    def test_comma_separated_string(self):
        set_config({"wrong_identity_hints": "中信证券,招商银行"})
        hints = _get_wrong_identity_hints()
        assert "中信证券" in hints
        set_config({"wrong_identity_hints": []})


# ---------------------------------------------------------------------------
# _names_are_related
# ---------------------------------------------------------------------------


class TestNamesAreRelated:
    def test_identical(self):
        assert _names_are_related("平安银行", {"平安银行"}) is True

    def test_substring(self):
        assert _names_are_related("平安", {"平安银行"}) is True

    def test_superset(self):
        assert _names_are_related("平安银行股份有限公司", {"平安银行"}) is True

    def test_unrelated(self):
        assert _names_are_related("中信证券", {"平安银行"}) is False

    def test_empty_profile_names(self):
        assert _names_are_related("中信证券", {""}) is False

    def test_cross_language_not_related(self):
        """Chinese vs English names should NOT be considered related."""
        assert _names_are_related("星网锐捷", {"FUJIAN STAR-NET"}) is False


# ---------------------------------------------------------------------------
# _find_wrong_identity_hits — expanded detection
# ---------------------------------------------------------------------------


class TestFindWrongIdentityHits:
    def test_detects_unrelated_name_bound_to_code(self):
        """000001.SZ(中信证券) should be flagged when profile is 平安银行."""
        profile = _a_share_profile()
        items = [{"title": "000001.SZ（中信证券）发布年报", "source": "tavily"}]
        hits = _find_wrong_identity_hits(items, profile)
        assert "中信证券" in hits

    def test_allows_correct_name_bound_to_code(self):
        """000001.SZ（平安银行） should NOT be flagged."""
        profile = _a_share_profile()
        items = [{"title": "000001.SZ（平安银行）发布年报", "source": "tavily"}]
        hits = _find_wrong_identity_hits(items, profile)
        assert "平安银行" not in hits

    def test_custom_hint_detected(self):
        """Custom hints from config should be detected."""
        set_config({"wrong_identity_hints": ["中信证券"]})
        profile = _a_share_profile()
        items = [{"title": "中信证券发布研报 000001.SZ 推荐", "source": "tavily"}]
        hits = _find_wrong_identity_hits(items, profile)
        assert "中信证券" in hits
        set_config({"wrong_identity_hints": []})

    def test_yfinance_chinese_alias_not_flagged(self):
        """Chinese name for yfinance English profile should NOT be flagged."""
        profile = _yfinance_profile()
        items = [{"title": "002396.SZ（星网锐捷）发布公告", "source": "tavily"}]
        hits = _find_wrong_identity_hits(items, profile)
        assert "星网锐捷" not in hits

    def test_yfinance_hint_still_flagged(self):
        """Known confusion names should be flagged even for yfinance profiles."""
        profile = _yfinance_profile()
        items = [{"title": "恒瑞医药 002396.SZ 研报", "source": "report"}]
        hits = _find_wrong_identity_hits(items, profile)
        assert "恒瑞医药" in hits

    def test_empty_items(self):
        hits = _find_wrong_identity_hits([], _a_share_profile())
        assert hits == set()


# ---------------------------------------------------------------------------
# Integration: config-driven hints affect evaluate_and_enrich_evidence
# ---------------------------------------------------------------------------


class TestIdentityIntegration:
    def test_custom_hint_causes_gate_failure(self, monkeypatch):
        monkeypatch.setattr(
            "tradingagents.dataflows.evidence._run_tavily_enrichment",
            lambda *args, **kwargs: [],
        )
        set_config({
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
            "wrong_identity_hints": ["中信证券"],
        })
        state = {
            "company_of_interest": "000001.SZ",
            "trade_date": "2026-05-07",
            "market_report": "market ok",
            "sentiment_report": "",
            "news_report": "### 中信证券研报\n000001.SZ 中信证券推荐买入\nLink: https://example.com/1\n",
            "fundamentals_report": "fundamentals ok",
            "canonical_company_profile": _a_share_profile(),
        }

        with pytest.raises(EvidenceGateError) as exc:
            evaluate_and_enrich_evidence(state)

        assert "身份冲突" in str(exc.value)
        assert "中信证券" in str(exc.value)
        set_config({"wrong_identity_hints": []})
