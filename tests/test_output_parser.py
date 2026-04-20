"""Tests for structured output parsing with retry on malformed output."""

import unittest

from pydantic import ValidationError

from tradingagents.agents.output_parser import StructuredOutputParser, validate_agent_output
from tradingagents.agents.schemas import (
    AnalystReport,
    PortfolioDecision,
    RiskAssessment,
    TraderDecision,
    extract_fields,
)


VALID_ANALYST_JSON = (
    '{"summary": "Stock is up", "detailed_analysis": "Strong earnings beat",'
    ' "key_points": ["Revenue up 20%"], "confidence": 0.85}'
)

VALID_TRADER_JSON = (
    '{"action": "Buy", "reasoning": "Bullish trend", "confidence": 0.9,'
    ' "price_target": 150.0, "stop_loss": 130.0}'
)

VALID_RISK_JSON = (
    '{"stance": "Cautious", "argument": "Volatility is high",'
    ' "risk_factors": ["Market downturn"], "confidence": 0.6}'
)

VALID_PORTFOLIO_JSON = (
    '{"rating": "Buy", "executive_summary": "Strong buy",'
    ' "investment_thesis": "Solid fundamentals", "confidence": 0.8,'
    ' "price_target": 200.0, "time_horizon": "6 months"}'
)


class TestStructuredOutputParser(unittest.TestCase):
    """Test parse, retry, and extract_fields for all schema types."""

    def test_parse_valid_json(self):
        parser = StructuredOutputParser(AnalystReport)
        result = parser.parse(VALID_ANALYST_JSON)
        self.assertIsInstance(result, AnalystReport)
        self.assertEqual(result.confidence, 0.85)

    def test_parse_json_in_code_fence(self):
        text = f"```json\n{VALID_TRADER_JSON}\n```"
        parser = StructuredOutputParser(TraderDecision)
        result = parser.parse(text)
        self.assertEqual(result.action.value, "Buy")

    def test_parse_malformed_raises(self):
        parser = StructuredOutputParser(AnalystReport)
        with self.assertRaises((ValidationError, Exception)):
            parser.parse("This is not JSON at all")

    def test_parse_missing_required_field_raises(self):
        parser = StructuredOutputParser(TraderDecision)
        # Missing 'action' and 'reasoning'
        with self.assertRaises((ValidationError, Exception)):
            parser.parse('{"confidence": 0.5}')

    def test_parse_confidence_out_of_range_raises(self):
        parser = StructuredOutputParser(AnalystReport)
        bad = '{"summary": "x", "detailed_analysis": "x", "key_points": [], "confidence": 1.5}'
        with self.assertRaises((ValidationError, Exception)):
            parser.parse(bad)

    def test_retry_recovers_from_malformed_output(self):
        """Malformed first response → retry → valid JSON → success."""
        parser = StructuredOutputParser(AnalystReport)
        calls: list[str] = []

        def fake_llm(prompt: str) -> str:
            calls.append(prompt)
            return VALID_ANALYST_JSON

        result = parser.parse_with_retry("not json", fake_llm, max_retries=2)
        self.assertIsInstance(result, AnalystReport)
        self.assertEqual(len(calls), 1)  # one retry was needed

    def test_retry_exhausted_raises(self):
        """All retries return garbage → raises."""
        parser = StructuredOutputParser(TraderDecision)

        def always_bad(prompt: str) -> str:
            return "still not valid"

        with self.assertRaises(Exception):
            parser.parse_with_retry("bad", always_bad, max_retries=2)

    def test_retry_second_attempt_succeeds(self):
        """First retry still bad, second retry returns valid JSON."""
        parser = StructuredOutputParser(RiskAssessment)
        attempt = {"n": 0}

        def llm(prompt: str) -> str:
            attempt["n"] += 1
            if attempt["n"] < 2:
                return "still broken"
            return VALID_RISK_JSON

        result = parser.parse_with_retry("garbage", llm, max_retries=2)
        self.assertIsInstance(result, RiskAssessment)
        self.assertEqual(attempt["n"], 2)


class TestValidateAgentOutput(unittest.TestCase):
    """Test the convenience wrapper used by agent nodes."""

    def test_valid_output_returns_model_and_fields(self):
        model, fields = validate_agent_output(VALID_PORTFOLIO_JSON, PortfolioDecision)
        self.assertIsInstance(model, PortfolioDecision)
        self.assertEqual(fields["rating"], "Buy")
        self.assertIn("confidence", fields)

    def test_invalid_output_without_llm_returns_none(self):
        model, fields = validate_agent_output("garbage", AnalystReport, llm=None)
        self.assertIsNone(model)
        self.assertEqual(fields, {})


class TestExtractFields(unittest.TestCase):
    """Test structured field extraction from validated models."""

    def test_analyst_extract(self):
        m = AnalystReport.model_validate_json(VALID_ANALYST_JSON)
        f = extract_fields(m)
        self.assertIn("confidence", f)
        self.assertIn("key_points", f)
        self.assertNotIn("summary", f)  # text fields excluded

    def test_trader_extract_enum_to_str(self):
        m = TraderDecision.model_validate_json(VALID_TRADER_JSON)
        f = extract_fields(m)
        self.assertEqual(f["action"], "Buy")  # enum → string

    def test_none_values_omitted(self):
        m = TraderDecision(action="Buy", reasoning="bullish trend", confidence=0.5)
        f = extract_fields(m)
        self.assertNotIn("price_target", f)
        self.assertNotIn("stop_loss", f)
