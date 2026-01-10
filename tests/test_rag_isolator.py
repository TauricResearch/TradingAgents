"""
Unit Tests for RAG Isolator

Tests:
- Prompt creation with strict RAG enforcement
- Context formatting
- Response validation (knowledge contamination detection)
- Fact grounding
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.dataflows.rag_isolator import RAGIsolator


class TestRAGIsolator(unittest.TestCase):
    """Test suite for RAGIsolator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.isolator = RAGIsolator(strict_mode=True)
        self.context = {
            "market_data": {
                "close": 102.5,
                "volume": 50000000,
                "indicators": {
                    "RSI": 45.2,
                    "MACD": 0.8,
                    "50_SMA": 100.3
                }
            },
            "news": [
                {"summary": "Company ASSET_042 reported quarterly earnings"},
                {"summary": "Product A sales exceeded expectations"}
            ],
            "fundamentals": {
                "revenue_growth": 0.05,
                "earnings": 1.2,
                "debt_to_equity": 0.3
            },
            "historical": {
                "1m_return": 0.03,
                "3m_return": 0.08,
                "6m_return": 0.15
            }
        }
    
    def test_create_isolated_prompt_strict_mode(self):
        """Test prompt creation in strict mode."""
        query = "Should I buy this asset?"
        prompt = self.isolator.create_isolated_prompt(query, self.context)
        
        prompt_text = prompt.format(query=query)
        
        # Check for strict mode instructions
        self.assertIn("ONLY the information provided", prompt_text)
        self.assertIn("DO NOT use any knowledge from your training data", prompt_text)
        self.assertIn("INSUFFICIENT DATA", prompt_text)
    
    def test_create_isolated_prompt_non_strict_mode(self):
        """Test prompt creation in non-strict mode."""
        isolator = RAGIsolator(strict_mode=False)
        query = "What is the trend?"
        prompt = isolator.create_isolated_prompt(query, self.context)
        
        prompt_text = prompt.format(query=query)
        
        # Should not have strict warnings
        self.assertNotIn("DO NOT use any knowledge from your training data", prompt_text)
    
    def test_format_context_market_data(self):
        """Test context formatting includes market data."""
        context_str = self.isolator._format_context(self.context)
        
        self.assertIn("MARKET DATA", context_str)
        self.assertIn("102.5", context_str)
        self.assertIn("RSI", context_str)
        self.assertIn("45.2", context_str)
    
    def test_format_context_news(self):
        """Test context formatting includes news."""
        context_str = self.isolator._format_context(self.context)
        
        self.assertIn("NEWS SUMMARY", context_str)
        self.assertIn("ASSET_042", context_str)
        self.assertIn("Product A", context_str)
    
    def test_format_context_fundamentals(self):
        """Test context formatting includes fundamentals."""
        context_str = self.isolator._format_context(self.context)
        
        self.assertIn("FUNDAMENTAL DATA", context_str)
        self.assertIn("Revenue Growth", context_str)
        self.assertIn("0.05", context_str)
    
    def test_format_context_historical(self):
        """Test context formatting includes historical performance."""
        context_str = self.isolator._format_context(self.context)
        
        self.assertIn("HISTORICAL PERFORMANCE", context_str)
        self.assertIn("1-Month Return", context_str)
        self.assertIn("0.03", context_str)
    
    def test_validate_response_clean(self):
        """Test validation of clean response (no violations)."""
        response = "Based on the RSI of 45.2 and positive revenue growth of 5%, the asset shows moderate strength."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertTrue(result["valid"], "Clean response should be valid")
        self.assertEqual(len(result["violations"]), 0, "Should have no violations")
        self.assertEqual(result["confidence"], 1.0, "Confidence should be 1.0")
    
    def test_validate_response_company_name_leak(self):
        """Test detection of company name leakage."""
        response = "This is clearly Apple based on the fundamentals."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertFalse(result["valid"], "Should be invalid")
        self.assertGreater(len(result["violations"]), 0, "Should have violations")
        self.assertIn("Apple", str(result["violations"]), "Should detect Apple mention")
    
    def test_validate_response_product_name_leak(self):
        """Test detection of product name leakage."""
        response = "iPhone sales are driving growth."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertFalse(result["valid"], "Should be invalid")
        self.assertIn("iPhone", str(result["violations"]), "Should detect iPhone mention")
    
    def test_validate_response_absolute_price_leak(self):
        """Test detection of absolute dollar prices."""
        response = "The stock is trading at $480 which is expensive."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertFalse(result["valid"], "Should be invalid")
        self.assertIn("$480", str(result["violations"]), "Should detect absolute price")
    
    def test_validate_response_knowledge_phrase_leak(self):
        """Test detection of pre-trained knowledge phrases."""
        response = "Based on my knowledge, this company typically performs well."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertFalse(result["valid"], "Should be invalid")
        self.assertTrue(
            any("knowledge" in v.lower() for v in result["violations"]),
            "Should detect knowledge phrase"
        )
    
    def test_validate_response_multiple_violations(self):
        """Test confidence reduction with multiple violations."""
        response = "Apple's iPhone sales at $500 are strong based on my knowledge."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertFalse(result["valid"], "Should be invalid")
        self.assertGreaterEqual(len(result["violations"]), 3, "Should have multiple violations")
        self.assertLess(result["confidence"], 1.0, "Confidence should be reduced")
    
    def test_create_fact_grounded_prompt_no_inference(self):
        """Test fact-grounded prompt without inference."""
        facts = [
            "Revenue grew 5% YoY",
            "Earnings per share: $1.20",
            "Debt-to-equity ratio: 0.3"
        ]
        query = "What is the revenue growth?"
        
        prompt = self.isolator.create_fact_grounded_prompt(query, facts, allow_inference=False)
        
        self.assertIn("Revenue grew 5% YoY", prompt)
        self.assertIn("Do not infer", prompt)
    
    def test_create_fact_grounded_prompt_with_inference(self):
        """Test fact-grounded prompt with inference allowed."""
        facts = [
            "Revenue grew 5% YoY",
            "Costs decreased 3%"
        ]
        query = "What happened to profit margins?"
        
        prompt = self.isolator.create_fact_grounded_prompt(query, facts, allow_inference=True)
        
        self.assertIn("may make logical inferences", prompt)
        self.assertIn("clearly state when you are inferring", prompt)
    
    def test_validate_response_case_insensitive(self):
        """Test that validation is case-insensitive."""
        response = "This is APPLE stock."
        result = self.isolator.validate_response(response, self.context)
        
        self.assertFalse(result["valid"], "Should detect case-insensitive company names")
    
    def test_empty_context(self):
        """Test handling of empty context."""
        empty_context = {}
        context_str = self.isolator._format_context(empty_context)
        
        # Should not crash, just return empty sections
        self.assertIsInstance(context_str, str)
    
    def test_partial_context(self):
        """Test handling of partial context (missing sections)."""
        partial_context = {
            "market_data": {
                "close": 100.0
            }
        }
        
        context_str = self.isolator._format_context(partial_context)
        
        self.assertIn("MARKET DATA", context_str)
        self.assertNotIn("NEWS SUMMARY", context_str)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
