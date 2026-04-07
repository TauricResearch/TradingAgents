import unittest

from tradingagents.agents.utils.instrument_resolver import resolve_instrument
from tradingagents.graph.propagation import Propagator


class InstrumentResolverTests(unittest.TestCase):
    def test_resolves_us_symbol(self):
        profile = resolve_instrument("AAPL")
        self.assertEqual(profile.primary_symbol, "AAPL")
        self.assertEqual(profile.country, "US")

    def test_resolves_exchange_qualified_krx_symbol(self):
        profile = resolve_instrument("005930.KS")
        self.assertEqual(profile.primary_symbol, "005930.KS")
        self.assertEqual(profile.country, "KR")

    def test_resolves_numeric_krx_code(self):
        profile = resolve_instrument("005930")
        self.assertEqual(profile.primary_symbol, "005930.KS")

    def test_resolves_korean_company_name(self):
        profile = resolve_instrument("삼성전자")
        self.assertEqual(profile.primary_symbol, "005930.KS")

    def test_resolves_known_krx_english_name(self):
        profile = resolve_instrument("NAVER")
        self.assertEqual(profile.primary_symbol, "035420.KS")

    def test_resolves_known_krx_numeric_code(self):
        profile = resolve_instrument("035420")
        self.assertEqual(profile.primary_symbol, "035420.KS")

    def test_propagator_normalizes_instrument_into_state(self):
        state = Propagator().create_initial_state("삼성전자", "2026-01-15")
        self.assertEqual(state["company_of_interest"], "005930.KS")
        self.assertEqual(state["input_instrument"], "삼성전자")
        self.assertEqual(state["instrument_profile"]["country"], "KR")


if __name__ == "__main__":
    unittest.main()
