"""Opt-in, per-run news supplements preserve provenance and source failures."""
import json
from unittest.mock import patch

from tradingagents.dataflows.config import get_config, set_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows import router
from tradingagents.default_config import build_default_config


def test_explicit_snapshot_is_used_after_live_news_failure(tmp_path, monkeypatch):
    path = tmp_path / "news.json"
    path.write_text(json.dumps({
        "schema_version": 1, "ticker": "RHM.DE", "as_of": "2026-10-10",
        "items": [{"published_at": "2026-10-08", "title": "Verified issuer disclosure",
                   "source": "Rheinmetall AG", "url": "https://www.rheinmetall.com/test-disclosure",
                   "excerpt": "Fixture disclosure text.", "retrieved_at": "2026-10-10T10:00:00+00:00"}],
    }))
    monkeypatch.setenv("TRADINGAGENTS_NEWS_SUPPLEMENT", str(path))
    set_config(build_default_config())
    def unavailable(*args, **kwargs):
        raise VendorUnavailableError("live feed unavailable")
    with patch.dict(router.VENDOR_METHODS["get_news"], {"issuer_rss": unavailable, "yfinance": unavailable}):
        result = router.route_to_vendor("get_news", "RHM.DE", "2026-10-03", "2026-10-10")
    assert "WEB_RESEARCH_SUPPLEMENT" in result
    assert "2026-10-08" in result
    assert "https://www.rheinmetall.com/test-disclosure" in result
    assert "not a structured news feed" in result
    assert "live feed coverage remains unverified" in result


def _snapshot(tmp_path, **overrides):
    data = {
        "schema_version": 1, "ticker": "RHM.DE", "as_of": "2026-10-10",
        "items": [{"published_at": "2026-10-08", "title": "Disclosure",
                   "source": "Issuer", "url": "https://example.test/news",
                   "excerpt": "Evidence text", "retrieved_at": "2026-10-10T10:00:00+00:00"}],
        **overrides,
    }
    path = tmp_path / "supplement.json"
    path.write_text(json.dumps(data))
    set_config({"news_supplement_path": str(path)})
    return path


def test_snapshot_is_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_NEWS_SUPPLEMENT", raising=False)
    config = build_default_config()
    assert config["news_supplement_path"] is None
    assert "get_news" not in config["tool_vendors"]


def test_wrong_instrument_or_asof_is_rejected(tmp_path):
    import pytest
    from tradingagents.dataflows.vendors.news_supplement import get_news_supplement
    for overrides in ({"ticker": "OTHER"}, {"as_of": "2026-10-11"}):
        _snapshot(tmp_path, **overrides)
        with pytest.raises(VendorUnavailableError):
            get_news_supplement("RHM.DE", "2026-10-03", "2026-10-10")


def test_no_qualifying_items_is_typed_no_data(tmp_path):
    import pytest
    from tradingagents.dataflows.errors import NoMarketDataError
    from tradingagents.dataflows.vendors.news_supplement import get_news_supplement
    _snapshot(tmp_path)
    with pytest.raises(NoMarketDataError):
        get_news_supplement("RHM.DE", "2026-10-09", "2026-10-10")


def test_oversized_snapshot_is_rejected(tmp_path):
    import pytest
    from tradingagents.dataflows.vendors.news_supplement import get_news_supplement
    path = _snapshot(tmp_path)
    path.write_text(" " * 100001)
    with pytest.raises(VendorUnavailableError, match="100 KB"):
        get_news_supplement("RHM.DE", "2026-10-03", "2026-10-10")


def test_snapshot_is_not_read_when_live_news_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_NEWS_SUPPLEMENT", str(tmp_path / "does-not-exist.json"))
    set_config(build_default_config())
    with patch.dict(router.VENDOR_METHODS["get_news"], {"issuer_rss": lambda *a: "LIVE NEWS"}):
        assert router.route_to_vendor("get_news", "RHM.DE", "2026-10-03", "2026-10-10") == "LIVE NEWS"


def test_missing_snapshot_and_invalid_url_are_source_failures(tmp_path):
    import pytest
    from tradingagents.dataflows.vendors.news_supplement import get_news_supplement
    path = _snapshot(tmp_path)
    data = json.loads(path.read_text())
    data["items"][0]["url"] = "file:///etc/passwd"
    path.write_text(json.dumps(data))
    with pytest.raises(VendorUnavailableError, match="HTTPS"):
        get_news_supplement("RHM.DE", "2026-10-03", "2026-10-10")
    path.unlink()
    with pytest.raises(VendorUnavailableError):
        get_news_supplement("RHM.DE", "2026-10-03", "2026-10-10")
