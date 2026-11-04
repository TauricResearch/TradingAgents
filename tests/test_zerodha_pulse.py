"""Zerodha Pulse news vendor: page parsing, search matching, window rules, routing.

The crawl itself needs a browser and the network, so these tests feed the parser a
fixture shaped like pulse.zerodha.com and stub the crawl.
"""
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.dataflows.vendors.india as india
import tradingagents.dataflows.vendors.zerodha_pulse as pulse
import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorNotConfiguredError

_IST = india.IST


def _stamp(dt: datetime) -> str:
    return dt.astimezone(_IST).strftime("%I:%M %p, %d %b %Y")


def _page(now: datetime) -> str:
    recent, older = _stamp(now - timedelta(hours=1)), _stamp(now - timedelta(hours=20))
    return f"""
<ul id="news">
<li class="box item" id="item-1" data-search="reliance industries q2 preview o2c strength">
  <h2 class="title"><a href="https://ndtv.example/reliance-q2#publisher=newsstand">Reliance Industries Q2 Preview</a></h2>
  <div class="desc">O2C strength offsets retail weakness.</div>
  <span class="date" title="{recent}">1 hour ago</span><span class="feed">— NDTV Business</span>
  <ul class="similar"><li>
    <a href="https://ndtv.example/hdfc-pick" class="title2">Stock picks: HDFC Bank, Trent</a>
    <span class="date" title="{recent}">1 hour ago</span><span class="feed">— NDTV Business</span>
  </li></ul>
</li>
<li class="box item" id="item-2" data-search="air pollution alert chennai mumbai" data-pulse-hidden="1">
  <h2 class="title"><a href="https://toi.example/aqi">Air Pollution Alert</a></h2>
  <div class="desc">AQI is unhealthy.</div>
  <span class="date" title="{older}">20 hours ago</span><span class="feed">— Times of India</span>
</li>
<li class="box item" id="item-3" data-search="reliance retail expands" style="display: none;">
  <h2 class="title"><a href="https://et.example/retail">Reliance Retail expands</a></h2>
  <div class="desc">New stores.</div>
  <span class="date" title="{older}">20 hours ago</span><span class="feed">— Economic Times</span>
</li>
</ul>"""


@pytest.mark.unit
class ParseTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(UTC)
        self.articles = pulse.parse_page(_page(self.now))

    def test_parses_lead_and_similar_stories(self):
        titles = [a["title"] for a in self.articles]
        self.assertEqual(titles, [
            "Reliance Industries Q2 Preview", "Stock picks: HDFC Bank, Trent",
            "Air Pollution Alert", "Reliance Retail expands",
        ])
        lead = self.articles[0]
        self.assertEqual(lead["publisher"], "NDTV Business")
        self.assertEqual(lead["link"], "https://ndtv.example/reliance-q2")  # fragment dropped
        self.assertEqual(lead["summary"], "O2C strength offsets retail weakness.")

    def test_timestamps_are_ist(self):
        pub = self.articles[0]["pub_date"]
        self.assertEqual(pub.utcoffset(), timedelta(hours=5, minutes=30))
        self.assertAlmostEqual((self.now - pub).total_seconds(), 3600, delta=120)

    def test_hidden_boxes_are_not_visible(self):
        self.assertEqual([a["visible"] for a in self.articles], [True, True, False, False])

    def test_matches_visible_leads_and_titled_similar_stories(self):
        self.assertEqual([a["title"] for a in pulse.matches(self.articles, "Reliance Industries")],
                         ["Reliance Industries Q2 Preview"])
        # a similar story matches on its own title; a hidden lead does not match at all
        self.assertEqual([a["title"] for a in pulse.matches(self.articles, "hdfc bank")],
                         ["Stock picks: HDFC Bank, Trent"])
        self.assertEqual(pulse.matches(self.articles, "reliance retail"), [])

    def test_unparseable_timestamp_is_undated(self):
        self.assertIsNone(pulse._pub_date("yesterday"))
        self.assertIsNone(pulse._pub_date(None))


@pytest.mark.unit
class SearchTermTests(unittest.TestCase):
    def test_company_name_without_corporate_suffix_then_ticker_root(self):
        with mock.patch.object(india, "get_company_profile",
                               return_value={"longName": "Reliance Industries Limited"}):
            self.assertEqual(india.search_terms("RELIANCE.NS"), ["reliance industries", "reliance"])

    def test_falls_back_to_ticker_root_without_a_profile(self):
        with mock.patch.object(india, "get_company_profile", side_effect=RuntimeError("down")):
            self.assertEqual(india.search_terms("TCS.NS"), ["tcs"])

    def test_terms_shorter_than_the_search_minimum_are_dropped(self):
        with mock.patch.object(india, "get_company_profile", return_value={}):
            self.assertEqual(india.search_terms("X"), [])


@pytest.mark.unit
class GetNewsTests(unittest.TestCase):
    def setUp(self):
        self._saved = config_module._config
        cfg = default_config.DEFAULT_CONFIG.copy()
        cfg["data_vendors"] = dict(cfg["data_vendors"], news_data="zerodha_pulse")
        set_config(cfg)
        self.now = datetime.now(UTC)
        self.today = self.now.strftime("%Y-%m-%d")  # UTC, the date coverage_gap judges against
        self.week_ago = (self.now - timedelta(days=7)).strftime("%Y-%m-%d")
        profile = mock.patch.object(india, "get_company_profile",
                                    return_value={"longName": "Reliance Industries Limited"})
        profile.start()
        self.addCleanup(profile.stop)

    def tearDown(self):
        config_module._config = self._saved

    def _stub_crawl(self):
        html = _page(self.now)

        def fake_fetch(term):
            articles = pulse.parse_page(html)
            return pulse.matches(articles, term), articles
        return mock.patch.object(pulse, "fetch_matches", side_effect=fake_fetch)

    def test_output_matches_the_shared_news_format(self):
        with self._stub_crawl():
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertTrue(out.startswith(f"## RELIANCE.NS News, from {self.week_ago} to {self.today}:\n\n"))
        self.assertIn("### Reliance Industries Q2 Preview (source: NDTV Business)\n"
                      "O2C strength offsets retail weakness.\n"
                      "Link: https://ndtv.example/reliance-q2\n", out)

    def test_past_window_is_unavailable_not_empty(self):
        with self._stub_crawl():
            out = router.route_to_vendor("get_news", "RELIANCE.NS", "2026-01-01", "2026-01-08")
        self.assertIn("Zerodha Pulse news unavailable", out)
        self.assertIn("it only serves recent items", out)

    def test_no_match_in_a_covered_window_reads_as_no_news(self):
        # the fixture's oldest article is ~20 h old, so a window from its day is observed
        covered_from = (self.now - timedelta(hours=20)).strftime("%Y-%m-%d")
        with mock.patch.object(india, "get_company_profile", return_value={"longName": "Zzyzx Corp"}), \
                self._stub_crawl():
            out = router.route_to_vendor("get_news", "ZZYZX.NS", covered_from, self.today)
        self.assertEqual(out, f"No news found for ZZYZX.NS between {covered_from} and {self.today}")

    def test_week_window_beyond_one_day_of_coverage_is_unavailable(self):
        with mock.patch.object(india, "get_company_profile", return_value={"longName": "Zzyzx Corp"}), \
                self._stub_crawl():
            out = router.route_to_vendor("get_news", "ZZYZX.NS", self.week_ago, self.today)
        self.assertIn("it only serves recent items", out)

    def test_non_indian_ticker_is_not_searched(self):
        with mock.patch.object(pulse, "fetch_matches") as crawl:
            for ticker in ("NVDA", "RELIANCE", "7203.T"):
                with self.assertRaises(pulse.VendorUnavailableError):
                    pulse.get_news_pulse(ticker, self.week_ago, self.today)
        crawl.assert_not_called()

    def test_non_indian_ticker_falls_through_to_the_next_vendor(self):
        cfg = config_module.get_config().copy()
        cfg["data_vendors"] = dict(cfg["data_vendors"], news_data="zerodha_pulse,yfinance")
        set_config(cfg)
        with mock.patch.object(pulse, "fetch_matches") as crawl, \
                mock.patch.dict(router.VENDOR_METHODS["get_news"], {"yfinance": lambda *a: "YF news"}):
            self.assertEqual(router.route_to_vendor("get_news", "NVDA", self.week_ago, self.today), "YF news")
        crawl.assert_not_called()

    def test_bse_and_lowercase_suffixes_are_searched(self):
        with self._stub_crawl():
            for ticker in ("RELIANCE.BO", "reliance.ns"):
                out = router.route_to_vendor("get_news", ticker, self.week_ago, self.today)
                self.assertIn("Reliance Industries Q2 Preview", out)

    def test_missing_crawl4ai_is_a_not_configured_vendor(self):
        with mock.patch.dict("sys.modules", {"crawl4ai": None}), \
                self.assertRaises(VendorNotConfiguredError):
            pulse.get_news_pulse("RELIANCE.NS", self.week_ago, self.today)

    def test_crawl_failure_is_vendor_unavailable(self):
        with mock.patch.object(pulse, "fetch_matches", side_effect=OSError("browser died")):
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertTrue(out.startswith("DATA_UNAVAILABLE"))


if __name__ == "__main__":
    unittest.main()
