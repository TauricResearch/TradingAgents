import unittest

from tradingagents import default_config
from tradingagents.dataflows.router import VENDOR_METHODS


class OfficialSourceRoutingTests(unittest.TestCase):
    def test_official_european_macro_provider_precedes_fred_fallback(self):
        self.assertIn("official_europe", VENDOR_METHODS["get_macro_indicators"])
        self.assertEqual(default_config.DEFAULT_CONFIG["data_vendors"]["macro_data"], "official_europe,fred")

    def test_configured_issuer_feed_precedes_yahoo_news_fallback(self):
        # Provenance order, first-party first: the issuer's own feed leads,
        # the licensed aggregators (marketaux, finnhub) sit next, and the
        # general-purpose Yahoo fallback stays behind them.
        chain = default_config.DEFAULT_CONFIG["data_vendors"]["news_data"]
        self.assertIn("issuer_rss", VENDOR_METHODS["get_news"])
        self.assertEqual(
            chain, "ureg_pdmr,issuer_rss,marketaux,finnhub,yfinance,alpha_vantage")
        # the configured first-party feed must precede the Yahoo fallback
        self.assertLess(chain.index("issuer_rss"), chain.index("yfinance"))
        self.assertTrue(default_config.DEFAULT_CONFIG["issuer_registry_path"].endswith("german_equities.json"))

    def test_german_pdmr_source_leads_the_insider_chain(self):
        # ureg_pdmr is the keyless authoritative Art. 19 MAR source for German
        # equities; it self-selects via the issuer registry, so it must lead
        # the insider chain (configured DE issuer) while staying absent from
        # the news tools (it only implements get_insider_transactions).
        self.assertIn("ureg_pdmr", VENDOR_METHODS["get_insider_transactions"])
        chain = default_config.DEFAULT_CONFIG["data_vendors"]["news_data"]
        self.assertEqual(chain.split(",")[0], "ureg_pdmr")
        self.assertLess(chain.index("ureg_pdmr"), chain.index("finnhub"))
        self.assertNotIn("ureg_pdmr", VENDOR_METHODS["get_news"])
        self.assertNotIn("ureg_pdmr", VENDOR_METHODS["get_global_news"])


if __name__ == "__main__":
    unittest.main()
