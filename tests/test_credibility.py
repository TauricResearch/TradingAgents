
from tradingagents.dataflows import config as _config_module
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.credibility import (
    attach_credibility,
    credibility_summary,
    score_credibility,
)

# ---------------------------------------------------------------------------
# score_credibility — domain classification
# ---------------------------------------------------------------------------


class TestScoreCredibility:
    def test_high_official_a_share_domain(self):
        item = {"url": "https://www.cninfo.com.cn/new/disclosure", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_szse_domain(self):
        item = {"url": "https://www.szse.cn/disclosure/", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_sec_gov(self):
        item = {"url": "https://sec.gov/cgi-bin/browse-edgar", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_reuters(self):
        item = {"url": "https://www.reuters.com/markets/", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_cls_cn_cailianpress(self):
        item = {"url": "https://www.cls.cn/detail/123", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_medium_yahoo_finance(self):
        item = {"url": "https://finance.yahoo.com/quote/AAPL", "publisher": ""}
        assert score_credibility(item) == "medium"

    def test_medium_eastmoney(self):
        item = {"url": "https://www.eastmoney.com/a/123.html", "publisher": ""}
        assert score_credibility(item) == "medium"

    def test_medium_seekingalpha(self):
        item = {"url": "https://seekingalpha.com/article/123", "publisher": ""}
        assert score_credibility(item) == "medium"

    def test_low_unknown_domain(self):
        item = {"url": "https://random-blog.example.com/post/1", "publisher": ""}
        assert score_credibility(item) == "low"

    def test_low_no_url(self):
        item = {"url": "", "publisher": ""}
        assert score_credibility(item) == "low"

    def test_low_no_item(self):
        assert score_credibility({}) == "low"

    def test_subdomain_matches_parent(self):
        """Subdomain of a high-credibility domain should also be high."""
        item = {"url": "https://data.cninfo.com.cn/finalpage/2026/PDF/123.PDF", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_publisher_field_used_as_fallback(self):
        """When URL is empty, publisher field should be checked."""
        item = {"url": "", "publisher": "reuters.com"}
        assert score_credibility(item) == "high"

    def test_www_prefix_stripped(self):
        item = {"url": "https://www.bloomberg.com/news/123", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_csrc_gov_cn(self):
        """CSRC official website should be high credibility [CSRC]."""
        item = {"url": "http://www.csrc.gov.cn/csrc/c100028/content.shtml", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_cs_com_cn(self):
        """中证网 — CSRC-designated disclosure platform [CSRC]."""
        item = {"url": "https://www.cs.com.cn/xwzx/hg/202605/t123.shtml", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_prnewswire(self):
        """PR Newswire — SEC 8-K filing channel [SEC]."""
        item = {"url": "https://www.prnewswire.com/news-releases/123.html", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_businesswire(self):
        """Business Wire — SEC 8-K filing channel [SEC]."""
        item = {"url": "https://www.businesswire.com/news/home/20260528/123", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_stcn_promoted(self):
        """证券时报 — promoted to high as CSRC-designated disclosure media [CSRC][Hurun]."""
        item = {"url": "https://www.stcn.com/article/detail/123.html", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_high_21jingji_promoted(self):
        """21世纪经济报道 — promoted to high as Hurun Top10 [Hurun]."""
        item = {"url": "https://www.21jingji.com/article/2026/0528/123.html", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_medium_jiemian(self):
        """界面新闻 — medium credibility [Hurun]."""
        item = {"url": "https://www.jiemian.com/article/123.html", "publisher": ""}
        assert score_credibility(item) == "medium"


# ---------------------------------------------------------------------------
# Custom domain overrides
# ---------------------------------------------------------------------------


class TestCredibilityOverrides:
    def test_custom_override_takes_priority(self, monkeypatch):
        set_config({"credibility_domain_overrides": {"myblog.com": "high"}})
        item = {"url": "https://myblog.com/post/1", "publisher": ""}
        assert score_credibility(item) == "high"

    def test_custom_override_can_downgrade(self, monkeypatch):
        set_config({"credibility_domain_overrides": {"reuters.com": "low"}})
        item = {"url": "https://reuters.com/markets/", "publisher": ""}
        assert score_credibility(item) == "low"

    def test_custom_override_subdomain(self, monkeypatch):
        set_config({"credibility_domain_overrides": {"example.com": "medium"}})
        item = {"url": "https://finance.example.com/quote/AAPL", "publisher": ""}
        assert score_credibility(item) == "medium"

    def teardown_method(self):
        # set_config merges dicts, so we must directly reset the nested dict
        _config_module._config["credibility_domain_overrides"] = {}


# ---------------------------------------------------------------------------
# attach_credibility
# ---------------------------------------------------------------------------


class TestAttachCredibility:
    def teardown_method(self):
        set_config({"credibility_enabled": True})
        _config_module._config["credibility_domain_overrides"] = {}

    def test_attaches_credibility_to_all_items(self):
        items = [
            {"url": "https://reuters.com/a", "publisher": ""},
            {"url": "https://random-blog.com/b", "publisher": ""},
        ]
        result = attach_credibility(items)
        assert result[0]["credibility"] == "high"
        assert result[1]["credibility"] == "low"
        assert result is items  # in-place mutation

    def test_empty_list(self):
        assert attach_credibility([]) == []

    def test_disabled_by_config(self):
        set_config({"credibility_enabled": False})
        items = [{"url": "https://reuters.com/a", "publisher": ""}]
        attach_credibility(items)
        assert "credibility" not in items[0]


# ---------------------------------------------------------------------------
# credibility_summary
# ---------------------------------------------------------------------------


class TestCredibilitySummary:
    def test_counts_all_tiers(self):
        items = [
            {"credibility": "high"},
            {"credibility": "high"},
            {"credibility": "medium"},
            {"credibility": "low"},
            {"credibility": "low"},
            {"credibility": "low"},
        ]
        summary = credibility_summary(items)
        assert summary == {"high": 2, "medium": 1, "low": 3}

    def test_empty_list(self):
        assert credibility_summary([]) == {"high": 0, "medium": 0, "low": 0}

    def test_missing_credibility_defaults_to_low(self):
        items = [{"title": "no credibility field"}]
        summary = credibility_summary(items)
        assert summary == {"high": 0, "medium": 0, "low": 1}
