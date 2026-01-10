"""
Unit Tests for Semantic Fact Checker

Tests:
- NLI-based semantic contradiction detection
- Targeted validation (final arguments only)
- Hash-based caching
- "Revenue fell" vs "Revenue rose" detection
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.validation.semantic_fact_checker import (
    SemanticFactChecker,
    FactCheckResult,
    EntailmentLabel
)


class TestSemanticFactChecker(unittest.TestCase):
    """Test suite for semantic fact checking."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Use fallback mode (no NLI model) for testing
        self.checker = SemanticFactChecker(use_local_model=False)
    
    def test_validate_contradictory_revenue_claim(self):
        """CRITICAL: Test detection of semantic contradiction."""
        # Ground truth: Revenue GREW 5%
        # Claim: Revenue FELL 5%
        # Expected: CONTRADICTION
        
        arguments = ["Revenue fell by 5% last quarter"]
        ground_truth = {"revenue_growth_yoy": 0.05}  # Grew 5%
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertFalse(result.valid, "Contradictory claim should be invalid")
        self.assertEqual(result.label, EntailmentLabel.CONTRADICTION,
                        "Should detect contradiction")
        self.assertIn("mismatch", result.evidence.lower(),
                     "Evidence should mention direction mismatch")
    
    def test_validate_correct_revenue_claim(self):
        """Test validation of correct claim."""
        arguments = ["Revenue increased by approximately 5%"]
        ground_truth = {"revenue_growth_yoy": 0.05}
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertTrue(result.valid, "Correct claim should be valid")
        self.assertEqual(result.label, EntailmentLabel.ENTAILMENT,
                        "Should detect entailment")
    
    def test_validate_price_increase_claim(self):
        """Test price movement validation."""
        arguments = ["Stock price rose significantly"]
        ground_truth = {"price_change_pct": 0.10}  # 10% increase
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertTrue(result.valid, "Price increase claim should be valid")
    
    def test_validate_price_decrease_contradiction(self):
        """Test detection of price direction contradiction."""
        arguments = ["Stock price fell sharply"]
        ground_truth = {"price_change_pct": 0.10}  # Actually rose 10%
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertFalse(result.valid, "Contradictory price claim should be invalid")
        self.assertEqual(result.label, EntailmentLabel.CONTRADICTION)
    
    def test_validate_technical_indicator_claim(self):
        """Test technical indicator validation."""
        arguments = ["RSI is at 45.2"]
        ground_truth = {
            "indicators": {
                "RSI": 45.2
            }
        }
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertTrue(result.valid, "Correct RSI value should be valid")
        self.assertEqual(result.label, EntailmentLabel.ENTAILMENT)
    
    def test_validate_technical_indicator_mismatch(self):
        """Test detection of incorrect technical indicator value."""
        arguments = ["RSI is at 70"]
        ground_truth = {
            "indicators": {
                "RSI": 45.2
            }
        }
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertFalse(result.valid, "Incorrect RSI value should be invalid")
        self.assertEqual(result.label, EntailmentLabel.CONTRADICTION)
    
    def test_caching_same_argument(self):
        """Test that identical arguments are cached."""
        arguments = ["Revenue grew 5%"]
        ground_truth = {"revenue_growth_yoy": 0.05}
        trading_date = "2024-01-15"
        
        # First call - not cached
        results1 = self.checker.validate_arguments(arguments, ground_truth, trading_date)
        self.assertFalse(results1[arguments[0]].cached, "First call should not be cached")
        
        # Second call - should be cached
        results2 = self.checker.validate_arguments(arguments, ground_truth, trading_date)
        self.assertTrue(results2[arguments[0]].cached, "Second call should be cached")
    
    def test_caching_different_dates(self):
        """Test that cache is scoped by trading date."""
        arguments = ["Revenue grew 5%"]
        ground_truth = {"revenue_growth_yoy": 0.05}
        
        # Same argument, different dates
        results1 = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        results2 = self.checker.validate_arguments(arguments, ground_truth, "2024-01-16")
        
        # Both should not be cached (different dates)
        self.assertFalse(results1[arguments[0]].cached)
        self.assertFalse(results2[arguments[0]].cached)
    
    def test_targeted_validation_multiple_arguments(self):
        """Test validation of multiple arguments (targeted, not full conversation)."""
        arguments = [
            "Revenue grew 5%",
            "Earnings increased 10%",
            "Price rose 3%"
        ]
        
        ground_truth = {
            "revenue_growth_yoy": 0.05,
            "earnings_growth": 0.10,
            "price_change_pct": 0.03
        }
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        
        # All should be valid
        for arg in arguments:
            self.assertTrue(results[arg].valid, f"Argument '{arg}' should be valid")
    
    def test_qualitative_claim_neutral(self):
        """Test that qualitative claims return neutral."""
        arguments = ["The company has strong leadership"]
        ground_truth = {}
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertTrue(result.valid, "Qualitative claims should be valid (can't verify)")
        self.assertEqual(result.label, EntailmentLabel.NEUTRAL)
    
    def test_missing_ground_truth_data(self):
        """Test handling of missing ground truth data."""
        arguments = ["Revenue grew 5%"]
        ground_truth = {}  # No revenue data
        
        results = self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        result = results[arguments[0]]
        
        self.assertTrue(result.valid, "Should be valid when ground truth missing")
        self.assertEqual(result.label, EntailmentLabel.NEUTRAL)
    
    def test_cache_size_limit(self):
        """Test that cache respects size limit."""
        checker = SemanticFactChecker(use_local_model=False, cache_size=5)
        ground_truth = {"revenue_growth_yoy": 0.05}
        
        # Add 10 arguments (exceeds cache size of 5)
        for i in range(10):
            arguments = [f"Revenue grew {i}%"]
            checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        
        stats = checker.get_cache_stats()
        self.assertLessEqual(stats["size"], 5, "Cache should not exceed max size")
    
    def test_clear_cache(self):
        """Test cache clearing."""
        arguments = ["Revenue grew 5%"]
        ground_truth = {"revenue_growth_yoy": 0.05}
        
        self.checker.validate_arguments(arguments, ground_truth, "2024-01-15")
        self.assertGreater(len(self.checker.cache), 0, "Cache should have entries")
        
        self.checker.clear_cache()
        self.assertEqual(len(self.checker.cache), 0, "Cache should be empty after clear")
    
    def test_classify_argument_types(self):
        """Test argument classification."""
        test_cases = [
            ("Revenue grew 5%", "revenue"),
            ("Stock price rose", "price"),
            ("RSI is oversold", "technical"),
            ("Company has good management", "qualitative")
        ]
        
        for argument, expected_type in test_cases:
            result = self.checker._classify_argument(argument)
            self.assertEqual(result, expected_type,
                           f"'{argument}' should be classified as '{expected_type}'")


if __name__ == '__main__':
    unittest.main(verbosity=2)
