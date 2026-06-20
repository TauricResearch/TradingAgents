import os
import unittest
from unittest.mock import patch

import pytest

from tradingagents.default_config import (
    DEFAULT_CONFIG,
    _apply_env_overrides,
    _coerce,
)


@pytest.mark.unit
class CoerceTests(unittest.TestCase):
    def test_bool_true_variants(self):
        for v in ("true", "True", "1", "yes", "on"):
            self.assertTrue(_coerce(v, True))

    def test_bool_false_variants(self):
        for v in ("false", "0", "no", "off"):
            self.assertFalse(_coerce(v, True))

    def test_int_coercion(self):
        self.assertEqual(_coerce("42", 1), 42)

    def test_float_coercion(self):
        self.assertEqual(_coerce("3.14", 1.0), 3.14)

    def test_string_fallback(self):
        self.assertEqual(_coerce("hello", "world"), "hello")


@pytest.mark.unit
class ApplyEnvOverridesTests(unittest.TestCase):
    @patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": "openai"})
    def test_overrides_provider(self):
        config = {"llm_provider": "sensenova"}
        _apply_env_overrides(config)
        self.assertEqual(config["llm_provider"], "openai")

    @patch.dict(os.environ, {"TRADINGAGENTS_CHECKPOINT_ENABLED": "true"})
    def test_overrides_bool(self):
        config = {"checkpoint_enabled": False}
        _apply_env_overrides(config)
        self.assertTrue(config["checkpoint_enabled"])

    @patch.dict(os.environ, {"TRADINGAGENTS_TEMPERATURE": "0.7"})
    def test_overrides_float(self):
        config = {"temperature": 0.0}
        _apply_env_overrides(config)
        self.assertEqual(config["temperature"], 0.7)

    @patch.dict(os.environ, {"UNRELATED_VAR": "foo"})
    def test_ignores_unrelated_vars(self):
        config = {"llm_provider": "sensenova"}
        _apply_env_overrides(config)
        self.assertEqual(config["llm_provider"], "sensenova")


@pytest.mark.unit
class DefaultConfigTests(unittest.TestCase):
    def test_has_expected_keys(self):
        expected = {
            "llm_provider", "deep_think_llm", "quick_think_llm",
            "max_debate_rounds", "max_risk_discuss_rounds",
            "checkpoint_enabled", "output_language", "benchmark_map",
        }
        for key in expected:
            self.assertIn(key, DEFAULT_CONFIG)

    def test_defaults_are_sane(self):
        self.assertEqual(DEFAULT_CONFIG["llm_provider"], "sensenova")
        self.assertEqual(DEFAULT_CONFIG["max_debate_rounds"], 1)
        self.assertEqual(DEFAULT_CONFIG["checkpoint_enabled"], False)
        self.assertEqual(DEFAULT_CONFIG["output_language"], "Chinese")

    def test_benchmark_map_has_default(self):
        self.assertIn("", DEFAULT_CONFIG["benchmark_map"])
        self.assertEqual(DEFAULT_CONFIG["benchmark_map"][""], "SPY")


if __name__ == "__main__":
    unittest.main()
