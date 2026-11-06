"""Tests for the external-scanner signal context (trading-workspace#37) —
news-gap-ml's leg-3 (technical) trigger hands its own scanner's finding to
TradingAgents' market analyst as context to reason about, not ground truth."""

import importlib.util
import sys
import unittest
from pathlib import Path

import pytest

from tradingagents.agents.context import get_external_signal_context_from_state
from tradingagents.graph.propagation import Propagator


def _load_decide_module():
    """scripts/decide.py isn't a package module (no scripts/__init__.py) —
    load it directly by path, same as running it as a script would."""
    path = Path(__file__).parent.parent / "scripts" / "decide.py"
    spec = importlib.util.spec_from_file_location("decide", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["decide"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class GetExternalSignalContextFromStateTests(unittest.TestCase):
    def test_absent_key_returns_empty(self):
        self.assertEqual(get_external_signal_context_from_state({}), "")

    def test_blank_string_returns_empty(self):
        self.assertEqual(get_external_signal_context_from_state({"external_signal_context": "   "}), "")

    def test_non_string_returns_empty(self):
        self.assertEqual(get_external_signal_context_from_state({"external_signal_context": None}), "")

    def test_present_value_is_returned(self):
        state = {"external_signal_context": "A separate technical scanner already flagged this stock today."}
        self.assertEqual(get_external_signal_context_from_state(state), state["external_signal_context"])


@pytest.mark.unit
class CreateInitialStateExternalSignalContextTests(unittest.TestCase):
    def test_defaults_to_empty(self):
        state = Propagator().create_initial_state("WIPRO.NS", "2026-07-15")
        self.assertEqual(state["external_signal_context"], "")

    def test_passed_value_threads_through(self):
        state = Propagator().create_initial_state(
            "WIPRO.NS", "2026-07-15", external_signal_context="scanner says long, score 78.5",
        )
        self.assertEqual(state["external_signal_context"], "scanner says long, score 78.5")


@pytest.mark.unit
class FormatExternalSignalContextTests(unittest.TestCase):
    def setUp(self):
        self.decide = _load_decide_module()

    def test_full_payload_includes_all_present_fields(self):
        raw = (
            '{"side": "long", "action": "entry", "score": 78.5, "structure": "uptrend", '
            '"rsi14": 62.3, "ema20": 121.5, "ema50": 118.2, "atr14": 3.1, '
            '"entry_price": 123.4, "stop_price": 120.0, "target_price": 130.0}'
        )
        result = self.decide._format_external_signal_context(raw)
        self.assertIn("long entry", result)
        self.assertIn("score 78.5/100", result)
        self.assertIn("structure=uptrend", result)
        self.assertIn("RSI14=62.3", result)
        self.assertIn("entry=123.4", result)
        self.assertIn("stop=120.0", result)
        self.assertIn("target=130.0", result)
        self.assertIn("not as ground truth", result)

    def test_missing_optional_fields_are_skipped_not_blank(self):
        result = self.decide._format_external_signal_context('{"side": "short", "action": "entry", "score": 40}')
        self.assertIn("short entry", result)
        self.assertNotIn("RSI14=", result)
        self.assertNotIn("Scanner detail:", result)  # no detail fields present at all

    def test_invalid_json_returns_empty_string_not_raise(self):
        result = self.decide._format_external_signal_context("not json")
        self.assertEqual(result, "")

    def test_empty_dict_still_produces_a_framing_sentence(self):
        result = self.decide._format_external_signal_context("{}")
        self.assertIn("A separate technical scanner already flagged this stock today", result)


if __name__ == "__main__":
    unittest.main()
