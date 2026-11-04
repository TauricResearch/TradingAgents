"""NDTV Profit news vendor: result parsing, report tagging, peer comparison, window rules.

The crawl needs a browser and the network, so these tests feed the parsers fixtures
shaped like ndtvprofit.com's pages and stub the crawl.
"""
import unittest
from datetime import UTC, date, datetime, timedelta
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.dataflows.vendors.india as india
import tradingagents.dataflows.vendors.ndtv_profit as ndtv
import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError

_IST = india.IST


def _card(title: str, summary: str, link: str, when: datetime) -> str:
    stamp = when.astimezone(_IST).strftime("%b %d, %Y %H:%M") + " pm IST"  # the site's 24 h clock + "pm"
    return f"""<li class="FuY8bW_articleItem"><div class="FuY8bW_articleCard">
<div class="FuY8bW_articleBody"><a class="FuY8bW_articleTitle" href="{link}"><span>{title}</span></a>
<p class="FuY8bW_articleExcerpt">{summary}</p>
<nav class="FuY8bW_articleMeta"><ul><li><span class="FuY8bW_metaText">{stamp}</span></li>
<li><span class="FuY8bW_metaLink">Markets</span></li></ul></nav></div></div></li>"""


def _page(*cards: str) -> str:
    return f"<ul>{''.join(cards)}</ul>"


class _Both:
    """Enter several patches as one context manager."""

    def __init__(self, *patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.__enter__()

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.__exit__(*exc)


READOUT = "Reliance Industries Ltd. +9.40 (0.81%) NIFTY 50 +237.90 (1.05%)"


@pytest.mark.unit
class ParseTests(unittest.TestCase):
    def test_article_card_fields_and_ist_timestamp(self):
        when = datetime(2026, 10, 29, 16, 59, tzinfo=UTC)  # 22:29 IST
        (a,) = ndtv.parse_articles(_page(_card("Q2 Preview", "O2C strength.", "https://x/q2", when)))
        self.assertEqual((a["title"], a["summary"], a["link"]), ("Q2 Preview", "O2C strength.", "https://x/q2"))
        self.assertEqual(a["pub_date"], datetime(2026, 10, 29, 22, 29, tzinfo=_IST))
        self.assertEqual(a["publisher"], "NDTV Profit")

    def test_card_without_a_title_link_is_skipped(self):
        self.assertEqual(ndtv.parse_articles('<ul><li class="FuY8bW_articleItem"><p>no link</p></li></ul>'), [])

    def test_unreadable_timestamp_is_undated(self):
        self.assertIsNone(ndtv._pub_date("yesterday"))
        self.assertIsNone(ndtv._pub_date(None))

    def test_peer_readout(self):
        row = ndtv.parse_peer_readout(READOUT)
        self.assertEqual((row["a"], row["ac"], row["ap"]), ("Reliance Industries Ltd.", "+9.40", "0.81"))
        self.assertEqual((row["b"], row["bc"], row["bp"]), ("NIFTY 50", "+237.90", "1.05"))

    def test_peer_readout_with_a_fall(self):
        row = ndtv.parse_peer_readout("JSW Energy Ltd. -3.10 (-0.60%) NIFTY 50 -12.50 (-0.05%)")
        self.assertEqual((row["ac"], row["ap"], row["bc"], row["bp"]), ("-3.10", "-0.60", "-12.50", "-0.05"))

    def test_unreadable_peer_readout_is_none(self):
        self.assertIsNone(ndtv.parse_peer_readout(""))
        self.assertIsNone(ndtv.parse_peer_readout("Peer Comparison unavailable"))


@pytest.mark.unit
class SearchTermTests(unittest.TestCase):
    def test_bse_scrip_code_is_not_a_search_term(self):
        with mock.patch.object(india, "get_company_profile", return_value={}):
            self.assertEqual(india.search_terms("500325.BO"), [])

    def test_alphabetic_bse_ticker_is_searched(self):
        with mock.patch.object(india, "get_company_profile",
                               return_value={"longName": "Reliance Industries Limited"}):
            self.assertEqual(india.search_terms("RELIANCE.BO"), ["reliance industries", "reliance"])


@pytest.mark.unit
class GetNewsTests(unittest.TestCase):
    def setUp(self):
        self._saved = config_module._config
        cfg = default_config.DEFAULT_CONFIG.copy()
        cfg["data_vendors"] = dict(cfg["data_vendors"], news_data="ndtv_profit")
        set_config(cfg)
        self.now = datetime.now(UTC)
        self.today = date.today().isoformat()  # the local date is_historical judges a run by
        self.week_ago = (date.today() - timedelta(days=7)).isoformat()
        profile = mock.patch.object(india, "get_company_profile",
                                    return_value={"longName": "Reliance Industries Limited"})
        profile.start()
        self.addCleanup(profile.stop)

    def tearDown(self):
        config_module._config = self._saved

    def _crawled(self, readout=READOUT):
        hour = timedelta(hours=1)
        search = _page(
            _card("Reliance Industries Q2 Preview", "O2C strength.", "https://x/preview", self.now - hour),
            _card("Brokerages on Reliance Industries", "Targets raised.", "https://x/report", self.now - 3 * hour),
        )
        reports = _page(
            _card("Brokerages on Reliance Industries", "Targets raised.", "https://x/report", self.now - 3 * hour),
            _card("Reliance Industries target price cut by Nomura", "Lower estimates.", "https://x/nomura", self.now - 5 * hour),
            _card("Vedanta, JSW Energy in ICICI Securities review", "Targets.", "https://x/other", self.now - 2 * hour),
        )
        return {"search": search, "reports": reports, "peers": readout, "sector": "Petroleum Products • Large Cap"}

    def _stub(self, **kwargs):
        # the suite blocks sockets, which an event loop opens: run the crawl stub directly
        def fake(term, symbol):
            fake.calls.append((term, symbol))
            return self._crawled(**kwargs)
        fake.calls = []
        patches = (mock.patch.object(ndtv, "_crawl", new=fake),
                   mock.patch.object(ndtv, "_run", side_effect=lambda factory: factory()))
        return _Both(*patches), fake

    def test_stories_and_reports_in_the_shared_format_newest_first(self):
        patch, _ = self._stub()
        with patch:
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertTrue(out.startswith(f"## RELIANCE.NS News, from {self.week_ago} to {self.today}:\n\n"))
        self.assertIn("### Reliance Industries Q2 Preview (source: NDTV Profit)\n"
                      "O2C strength.\nLink: https://x/preview\n", out)
        # a search hit the reports page also lists is a report; so is a matching report only it lists
        self.assertIn("### Brokerages on Reliance Industries (source: NDTV Profit, research report)", out)
        self.assertIn("### Reliance Industries target price cut by Nomura (source: NDTV Profit, research report)", out)
        self.assertNotIn("ICICI Securities review", out)  # a report about other companies
        titles = [line for line in out.splitlines() if line.startswith("### ")]
        self.assertEqual([t.split(" (source")[0] for t in titles], [
            "### Reliance Industries Q2 Preview", "### Brokerages on Reliance Industries",
            "### Reliance Industries target price cut by Nomura",
        ])

    def test_peer_comparison_follows_the_news(self):
        patch, fake = self._stub()
        with patch:
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertIn("## Peer comparison, Reliance Industries Ltd. vs NIFTY 50 (NDTV Profit, latest session", out)
        self.assertIn("Sector / cap class: Petroleum Products • Large Cap", out)
        self.assertIn("Reliance Industries Ltd.: +9.40 (0.81%)", out)
        self.assertIn("NIFTY 50: +237.90 (1.05%)", out)
        self.assertEqual(fake.calls[0], ("reliance industries", "RELIANCE"))

    def test_peer_comparison_can_be_switched_off(self):
        cfg = config_module.get_config().copy()
        cfg["ndtv_peer_comparison"] = False
        set_config(cfg)
        patch, fake = self._stub()
        with patch:
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertNotIn("Peer comparison", out)
        self.assertEqual(fake.calls[0][1], None)  # the stock page is not opened

    def test_past_window_is_unavailable_and_peer_comparison_withheld(self):
        patch, fake = self._stub()
        with patch:
            out = router.route_to_vendor("get_news", "RELIANCE.NS", "2026-01-01", "2026-01-08")
        self.assertIn("NDTV Profit news unavailable", out)
        self.assertIn("Peer comparison (NDTV Profit)\n\nWithheld for 2026-01-08", out)
        self.assertNotIn("NIFTY 50: +237.90", out)
        self.assertEqual(fake.calls[0][1], None)

    def test_unreadable_peer_readout_adds_no_section(self):
        patch, _ = self._stub(readout="")
        with patch:
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertNotIn("Peer comparison", out)
        self.assertIn("Reliance Industries Q2 Preview", out)

    def test_non_indian_ticker_is_not_searched(self):
        patch, fake = self._stub()
        with patch:
            for ticker in ("NVDA", "RELIANCE", "7203.T"):
                with self.assertRaises(VendorUnavailableError):
                    ndtv.get_news_ndtv_profit(ticker, self.week_ago, self.today)
        self.assertEqual(fake.calls, [])

    def test_bse_scrip_code_without_a_name_is_unavailable(self):
        with mock.patch.object(india, "get_company_profile", return_value={}), \
                self.assertRaises(VendorUnavailableError):
            ndtv.get_news_ndtv_profit("500325.BO", self.week_ago, self.today)

    def test_non_indian_ticker_falls_through_to_the_next_vendor(self):
        cfg = config_module.get_config().copy()
        cfg["data_vendors"] = dict(cfg["data_vendors"], news_data="ndtv_profit,yfinance")
        set_config(cfg)
        with mock.patch.dict(router.VENDOR_METHODS["get_news"], {"yfinance": lambda *a: "YF news"}):
            self.assertEqual(router.route_to_vendor("get_news", "NVDA", self.week_ago, self.today), "YF news")

    def test_missing_crawl4ai_is_a_not_configured_vendor(self):
        with mock.patch.dict("sys.modules", {"crawl4ai": None}), self.assertRaises(VendorNotConfiguredError):
            ndtv.get_news_ndtv_profit("RELIANCE.NS", self.week_ago, self.today)

    def test_crawl_failure_is_vendor_unavailable(self):
        with mock.patch.object(ndtv, "_run", side_effect=OSError("browser died")):
            out = router.route_to_vendor("get_news", "RELIANCE.NS", self.week_ago, self.today)
        self.assertTrue(out.startswith("DATA_UNAVAILABLE"))


if __name__ == "__main__":
    unittest.main()
