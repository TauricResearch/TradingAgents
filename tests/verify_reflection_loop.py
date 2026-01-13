
import unittest
import json
import os
import shutil
from unittest.mock import MagicMock

# We will let the real imports happen. If venv is used, they should succeed.
from tradingagents.graph.reflection import Reflector
from tradingagents.engines.regime_detector import DynamicIndicatorSelector, MarketRegime

class TestReflectionLoop(unittest.TestCase):

    def setUp(self):
        # Create a dummy Reflector (mocking LLM only)
        self.mock_llm = MagicMock()
        self.reflector = Reflector(self.mock_llm)
        
        # Clean up any existing config
        if os.path.exists("data_cache/runtime_config.json"):
            os.remove("data_cache/runtime_config.json")
            
    def tearDown(self):
        # Clean up
        if os.path.exists("data_cache/runtime_config.json"):
            os.remove("data_cache/runtime_config.json")

    def test_json_parsing(self):
        """Test if Reflector correctly parses JSON updates from LLM text."""
        llm_response = """
        Analysis: The strategy was too slow.
        Recommend: Lower RSI period.
        
        ```json
        {
            "UPDATE_PARAMETERS": {
                "rsi_period": 7,
                "stop_loss_pct": 0.05
            }
        }
        ```
        """
        updates = self.reflector._parse_parameter_updates(llm_response)
        self.assertEqual(updates["rsi_period"], 7)
        self.assertEqual(updates["stop_loss_pct"], 0.05)
        print("✅ JSON Parsing Test Passed")

    def test_persistence_and_loading(self):
        """Test if parameter updates are saved and then loaded by RegimeDetector logic."""
        updates = {"rsi_period": 99, "bollinger_period": 5}
        
        # 1. Apply Updates (Simulate Reflector Action)
        self.reflector._apply_parameter_updates(updates)
        
        # Verify file exists
        self.assertTrue(os.path.exists("data_cache/runtime_config.json"))
        
        # 2. Simulate Market Analyst Loading Logic
        loaded_overrides = {}
        with open("data_cache/runtime_config.json", 'r') as f:
            loaded_overrides = json.load(f)
            
        self.assertEqual(loaded_overrides["rsi_period"], 99)
        
        # 3. Test Component Overrides (Regime Detector)
        # Get defaults for TRENDING_UP
        defaults = DynamicIndicatorSelector.get_optimal_parameters(MarketRegime.TRENDING_UP)
        self.assertEqual(defaults["rsi_period"], 14) # Standard default matches logic
        
        # Get with overrides
        tuned = DynamicIndicatorSelector.get_optimal_parameters(MarketRegime.TRENDING_UP, overrides=loaded_overrides)
        self.assertEqual(tuned["rsi_period"], 99) # Should be overridden
        self.assertEqual(tuned["bollinger_period"], 5)
        self.assertEqual(tuned["macd_fast"], 12) # Should remain default
        
        print("✅ Persistence and Integration Test Passed")

    def test_archival(self):
        """Test if parameter updates are archived to results/TICKER/DATE."""
        updates = {"rsi_period": 77}
        dummy_state = {
            "company_of_interest": "TEST_TICKER",
            "trade_date": "2024-01-01"
        }
        
        # 1. Apply Updates with State
        self.reflector._apply_parameter_updates(updates, dummy_state)
        
        # Verify global persistence
        self.assertTrue(os.path.exists("data_cache/runtime_config.json"))
        
        # Verify archival
        archive_path = "results/TEST_TICKER/2024-01-01/runtime_config.json"
        print(f"Checking for archive at {archive_path}")
        self.assertTrue(os.path.exists(archive_path))
        
        with open(archive_path, 'r') as f:
            data = json.load(f)
            self.assertEqual(data["rsi_period"], 77)
            
        print("✅ Archival Logic Test Passed")
        
    def tearDown(self):
        # Clean up
        if os.path.exists("data_cache/runtime_config.json"):
            os.remove("data_cache/runtime_config.json")
        if os.path.exists("results/TEST_TICKER"):
            shutil.rmtree("results/TEST_TICKER")

if __name__ == '__main__':
    unittest.main()
