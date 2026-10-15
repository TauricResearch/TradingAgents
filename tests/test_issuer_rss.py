import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.vendors import issuer_rss


class IssuerRssTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp.name) / "issuers.json"
        self.registry_path.write_text(json.dumps({
            "instruments": {
                "RHM.DE": {
                    "issuer": "Rheinmetall AG",
                    "isin": "DE0007030009",
                    "mic": "XETR",
                    "currency": "EUR",
                    "yahoo_symbol": "RHM.DE",
                    "news_feed_url": "https://issuer.example/news.xml",
                }
            }
        }), encoding="utf-8")
        self.config = patch.object(issuer_rss, "get_config", return_value={
            "issuer_registry_path": str(self.registry_path),
            "news_article_limit": 10,
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.temp.cleanup)

    @patch.object(issuer_rss, "get_scrubbed")
    def test_returns_only_date_bounded_official_feed_items_with_identity(self, get):
        response = Mock()
        response.text = """<?xml version="1.0"?><rss version="2.0"><channel>
          <title>Rheinmetall News</title>
          <item><title>Earlier item</title><link>https://issuer.example/old</link><pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate></item>
          <item><title>New credit line</title><link>https://issuer.example/credit</link><pubDate>Thu, 08 Oct 2026 08:00:00 GMT</pubDate><description>Official announcement.</description></item>
          <item><title>Future item</title><link>https://issuer.example/future</link><pubDate>Sun, 11 Oct 2026 08:00:00 GMT</pubDate></item>
        </channel></rss>"""
        get.return_value = response

        result = issuer_rss.get_news_issuer_rss("RHM.DE", "2026-10-01", "2026-10-09")

        self.assertIn("Rheinmetall AG", result)
        self.assertIn("DE0007030009", result)
        self.assertIn("2026-10-08", result)
        self.assertIn("New credit line", result)
        self.assertNotIn("Earlier item", result)
        self.assertNotIn("Future item", result)
        self.assertEqual(get.call_args.args[0], "https://issuer.example/news.xml")

    def test_registry_resolves_public_isin_and_wkn_identifiers(self):
        instrument = issuer_rss._load_instrument("DE0007030009")
        self.assertEqual(instrument["ticker"], "RHM.DE")
        self.assertEqual(instrument["yahoo_symbol"], "RHM.DE")

    def test_registry_resolves_identity_without_configured_news_feed(self):
        self.registry_path.write_text(json.dumps({"instruments": {"RHM.DE": {
            "issuer": "Rheinmetall AG", "isin": "DE0007030009", "wkn": "703000",
            "mic": "XETR", "currency": "EUR", "yahoo_symbol": "RHM.DE"
        }}}), encoding="utf-8")
        instrument = issuer_rss._load_instrument("DE0007030009")
        self.assertEqual(instrument["isin"], "DE0007030009")
        self.assertIsNone(instrument.get("news_feed_url"))

    def test_missing_feed_is_not_reported_as_empty_official_news(self):
        self.registry_path.write_text(json.dumps({"instruments": {"RHM.DE": {"issuer": "Rheinmetall AG"}}}), encoding="utf-8")
        with self.assertRaises(VendorNotConfiguredError):
            issuer_rss.get_news_issuer_rss("RHM.DE", "2026-10-01", "2026-10-09")


if __name__ == "__main__":
    unittest.main()
