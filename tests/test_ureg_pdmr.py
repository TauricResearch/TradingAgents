"""Offline tests for the keyless UReg PDMR vendor (ureg_pdmr).

Fixtures are real captures from unternehmensregister.de (tests/fixtures/):
- ureg_search_sap_p1.html: live search-result page (SAP SE, page 1) — 30
  publication rows of which exactly 18 are PDMR (category 80) and 12 are
  other capital-market categories (83), in German and English.
- ureg_pubhtml_de_alam.html / ureg_pubhtml_en_alam.html: the same person's
  PDMR disclosure served in German and English — the register emits both.

No network access: the entry point is tested with _search / fetch_detail
patched.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.vendors import ureg_pdmr as u

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class SearchRowExtractionTests(unittest.TestCase):
    def setUp(self):
        self.html = _fixture("ureg_search_sap_p1.html")
        self.rows = u._extract_pdmr_rows(self.html)

    def test_only_pdmr_category_rows_are_extracted(self):
        # the fixture page holds 30 publication rows (18 cat 80 + 12 cat 83);
        # the category filter must keep exactly the PDMR ones.
        self.assertEqual(len(self.rows), 18)
        for row in self.rows:
            self.assertTrue(row["payload"])

    def test_rows_carry_entity_and_iso_date(self):
        for row in self.rows:
            self.assertEqual(row["company"], "SAP SE")
            self.assertRegex(row["disclosure_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_rsc_decode_keeps_umlauts(self):
        # regression: unicode_escape decoding mangled "Münchener" into
        # "MÃ¼nchener"; json.loads must preserve diacritics.
        umlauts = [r for r in self.rows if "ö" in r["title"] or "Meldung" in r["title"]]
        self.assertTrue(umlauts, "expected German-titled (umlaut) rows in fixture")
        self.assertTrue(all("Ã" not in r["title"] for r in self.rows), "mojibake detected")


class PubHtmlParseTests(unittest.TestCase):
    def test_german_detail_parses_all_fields(self):
        f = u.parse_pub_html(_fixture("ureg_pubhtml_de_alam.html"))
        f["emittent"] = u._emittent_from_html(_fixture("ureg_pubhtml_de_alam.html"))
        self.assertEqual(f["person"], "Muhammad Alam")
        self.assertEqual(f["position"], "Vorstand")
        self.assertEqual(f["notification_type"], "Erstmeldung")
        self.assertEqual(f["emittent"], "SAP SE")
        self.assertEqual(f["lei"], "529900D6BF99LW9R2E68")
        self.assertEqual(f["isin"], "DE0007164600")
        self.assertEqual(f["price"], "176,6431 EUR")
        self.assertEqual(f["volume"], "34.485,73 EUR")
        self.assertEqual(f["transaction_date"], "11.09.2026")
        self.assertEqual(f["disclosure_date"], "14.09.2026")

    def test_english_detail_parses_all_fields(self):
        # the register serves the same disclosure in English — the parser
        # must not silently drop the fields it only knew in German.
        f = u.parse_pub_html(_fixture("ureg_pubhtml_en_alam.html"))
        f["emittent"] = u._emittent_from_html(_fixture("ureg_pubhtml_en_alam.html"))
        self.assertEqual(f["person"], "Muhammad Alam")
        self.assertEqual(f["position"], "Member of the managing body")
        self.assertEqual(f["notification_type"], "Initial notification")
        self.assertEqual(f["emittent"], "SAP SE")
        self.assertEqual(f["lei"], "529900D6BF99LW9R2E68")
        self.assertEqual(f["instrument_type"], "Share")
        self.assertEqual(f["isin"], "DE0007164600")
        self.assertEqual(f["price"], "0.0000 EUR")
        self.assertEqual(f["volume"], "0.0000 EUR")
        self.assertEqual(f["transaction_date"], "10.09.2026")
        self.assertEqual(f["disclosure_date"], "14.09.2026")

    def test_person_and_issuer_names_are_disambiguated(self):
        html = _fixture("ureg_pubhtml_de_alam.html")
        f = u.parse_pub_html(html)
        self.assertEqual(f["person"], "Muhammad Alam")
        self.assertEqual(u._emittent_from_html(html), "SAP SE")


class NormalizationTests(unittest.TestCase):
    def test_umlaut_fold_matches_case_and_punctuation_variants(self):
        # same official spelling, different case — must normalize to the
        # same key (the register mixes caps per issuer). Punctuation and
        # whitespace are collapsed identically on both sides.
        self.assertEqual(u._norm_name("Münchener Rückversicherungs-Gesellschaft"),
                         u._norm_name("MÜNCHENER RÜCKVERSICHERUNGS-GESELLSCHAFT"))
        self.assertEqual(u._norm_name("SAP SE"), u._norm_name("sap se"))
        self.assertEqual(u._norm_name("DEUTSCHE BANK AKTIENGESELLSCHAFT"),
                         u._norm_name("deutsche bank aktiengesellschaft"))
        self.assertEqual(u._norm_name("Volkswagen  Aktiengesellschaft"),
                         u._norm_name("volkswagen-aktiengesellschaft"))

    def test_eszett_folds_to_ss(self):
        # ß has no ASCII decomposition — it must fold before the NFKD/ASCII
        # step or it is silently dropped ("Straße" -> "strae").
        self.assertEqual(u._norm_name("Straße"), u._norm_name("Strasse"))

    def test_date_normalization(self):
        self.assertIsNone(u._to_iso_date(None))
        self.assertEqual(u._to_iso_date("2026-09-14"), "2026-09-14")
        self.assertEqual(u._to_iso_date("14.09.2026"), "2026-09-14")
        self.assertEqual(u._to_iso_date("11.09.2026"), "2026-09-11")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = Path(self.temp.name) / "german_equities.json"
        self.registry.write_text(json.dumps({
            "instruments": {
                "SAP.DE": {
                    "issuer": "SAP SE",
                    "ticker": "SAP.DE",
                    "isin": "DE0007164600",
                    "aliases": [],
                    "ureg_query_name": "SAP SE",
                    "ureg_entity_name": "SAP SE",
                },
                "SIEN.DE": {
                    "issuer": "Siemens AG",
                    "ticker": "SIEN.DE",
                    "aliases": ["SIE.DE"],
                    "ureg_query_name": "Siemens Aktiengesellschaft",
                    # NOTE: query name deliberately differs from the entity
                    # name — the register only matches the official form.
                    "ureg_entity_name": "Siemens Aktiengesellschaft",
                },
                "RHM.DE": {"issuer": "Rheinmetall AG"},  # no UReg identity
            }
        }), encoding="utf-8")
        self.config = patch.object(u, "get_config", return_value={
            "issuer_registry_path": str(self.registry),
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.temp.cleanup)

    def test_resolves_ureg_identity_for_configured_ticker(self):
        inst = u._load_instrument("SAP.DE")
        self.assertEqual(inst["ureg_query_name"], "SAP SE")
        self.assertEqual(inst["ureg_entity_name"], "SAP SE")

    def test_resolves_via_alias_and_case_insensitively(self):
        inst = u._load_instrument("sien.de")
        self.assertEqual(inst["ticker"], "SIEN.DE")
        self.assertEqual(inst["ureg_query_name"], "Siemens Aktiengesellschaft")

    def test_unconfigured_ticker_is_not_covered_by_this_vendor(self):
        with self.assertRaises(VendorNotConfiguredError):
            u._load_instrument("AAPL")

    def test_configured_ticker_without_ureg_identity_raises(self):
        with self.assertRaises(VendorNotConfiguredError):
            u._load_instrument("RHM.DE")

    def test_missing_registry_file_raises_not_configured(self):
        self.registry.unlink()
        with self.assertRaises(VendorNotConfiguredError):
            u._load_instrument("SAP.DE")


class EntryPointTests(unittest.TestCase):
    """get_ureg_pdmr_insider_transactions with _search/fetch_detail offline."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = Path(self.temp.name) / "german_equities.json"
        self.registry.write_text(json.dumps({
            "instruments": {
                "SAP.DE": {
                    "issuer": "SAP SE",
                    "ticker": "SAP.DE",
                    "ureg_query_name": "SAP SE",
                    "ureg_entity_name": "SAP SE",
                }
            }
        }), encoding="utf-8")
        self.config = patch.object(u, "get_config", return_value={
            "issuer_registry_path": str(self.registry),
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.temp.cleanup)

    def _row(self, company: str, date: str, payload: str) -> dict:
        return {
            "disclosure_date": date,
            "company": company,
            "language": "de",
            "payload": payload,
            "title": "Meldung und öffentliche Bekanntgabe der Geschäfte",
        }

    def _detail(self, payload: str) -> dict:
        return {
            "person": "Muhammad Alam",
            "position": "Vorstand",
            "notification_type": "Erstmeldung",
            "emittent": "SAP SE",
            "lei": "529900D6BF99LW9R2E68",
            "instrument_type": "Aktie",
            "isin": "DE0007164600",
            "transaction_type": "Veräußerung",
            "price": "176,6431 EUR",
            "volume": "34.485,73 EUR",
            "transaction_date": "11.09.2026",
            "location": "XETRA",
            "disclosure_date": "14.09.2026",
            "disclosed_via": "EQS Group AG",
        }

    def test_returns_entity_validated_pdmr_details(self):
        rows = [self._row("SAP SE", "2026-09-14", "P1"),
                self._row("SAP SE", "2026-08-26", "P2")]
        with patch.object(u, "_search", return_value=rows), \
             patch.object(u, "fetch_detail", side_effect=self._detail):
            out = u.get_ureg_pdmr_insider_transactions("SAP.DE")
        self.assertIn("SAP SE", out)
        self.assertIn("Muhammad Alam", out)
        self.assertIn("176,6431 EUR", out)
        self.assertIn("2026-09-14", out)
        self.assertIn("2026-08-26", out)
        self.assertIn("DE0007164600", out)

    def test_point_in_time_filter_excludes_later_disclosures(self):
        rows = [self._row("SAP SE", "2026-09-14", "P1"),
                self._row("SAP SE", "2026-08-26", "P2")]
        with patch.object(u, "_search", return_value=rows), \
             patch.object(u, "fetch_detail", side_effect=self._detail) as fd:
            out = u.get_ureg_pdmr_insider_transactions("SAP.DE", as_of_date="2026-08-26")
        self.assertNotIn("P1 details" , out)
        self.assertIn("2026-08-26", out)
        # only the in-window row's detail may be fetched
        self.assertEqual(fd.call_count, 1)
        self.assertEqual(fd.call_args.args[0], "P2")

    def test_rows_of_other_matched_companies_are_excluded(self):
        # fuzzy search can return rows of a different (matched) company;
        # they must never leak into this issuer's result.
        rows = [self._row("SAP SE", "2026-09-14", "P1"),
                self._row("SAP Business One Systems GmbH", "2026-09-14", "X1")]
        with patch.object(u, "_search", return_value=rows), \
             patch.object(u, "fetch_detail", side_effect=self._detail) as fd:
            out = u.get_ureg_pdmr_insider_transactions("SAP.DE")
        self.assertIn("excluded by entity validation", out)
        self.assertEqual(fd.call_count, 1)
        self.assertEqual(fd.call_args.args[0], "P1")

    def test_configured_emitter_without_pdmr_returns_terminal_absence(self):
        with patch.object(u, "_search", return_value=[]), \
             patch.object(u, "fetch_detail") as fd:
            out = u.get_ureg_pdmr_insider_transactions("SAP.DE")
        self.assertIn("no PDMR disclosures", out)
        self.assertIn("absence in this source only", out)
        fd.assert_not_called()

    def test_absence_with_entity_note_keeps_source_scope(self):
        # rows exist but only for another matched company
        rows = [self._row("SAP Business One Systems GmbH", "2026-09-14", "X1")]
        with patch.object(u, "_search", return_value=rows), \
             patch.object(u, "fetch_detail") as fd:
            out = u.get_ureg_pdmr_insider_transactions("SAP.DE")
        self.assertIn("no PDMR disclosures", out)
        self.assertIn("excluded by entity validation", out)
        fd.assert_not_called()

    def test_unconfigured_ticker_raises_not_configured(self):
        with self.assertRaises(VendorNotConfiguredError):
            u.get_ureg_pdmr_insider_transactions("AAPL")


if __name__ == "__main__":
    unittest.main()
