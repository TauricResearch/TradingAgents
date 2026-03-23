import sys
import unittest
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append("/Users/Ahmet/Repo/TradingAgents")

from agent_os.backend.services.langgraph_engine import LangGraphEngine

class TestLangGraphEngineExtraction(unittest.TestCase):
    def setUp(self):
        self.engine = LangGraphEngine()

    def test_extract_content_string(self):
        mock_obj = MagicMock()
        mock_obj.content = "hello world"
        self.assertEqual(self.engine._extract_content(mock_obj), "hello world")

    def test_extract_content_method(self):
        mock_obj = MagicMock()
        # Mocking a method
        def my_content():
            return "should not be called"
        mock_obj.content = my_content
        # Should fall back to str(mock_obj)
        result = self.engine._extract_content(mock_obj)
        self.assertTrue(result.startswith("<MagicMock"))

    def test_map_langgraph_event_llm_end_with_text_method(self):
        # Mocking output object with a text method
        mock_output = MagicMock()
        def my_text():
            return "bad"
        mock_output.text = my_text
        mock_output.content = None # Ensure it triggers fallback
        
        event = {
            "event": "on_chat_model_end",
            "run_id": "test_run",
            "name": "test_node",
            "data": {"output": mock_output},
            "metadata": {"langgraph_node": "test_node"}
        }
        
        # This used to raise TypeError
        result = self.engine._map_langgraph_event("run_123", event)
        self.assertIsNotNone(result)
        self.assertIsInstance(result["response"], str)
        # It's okay if it's empty, as long as it didn't crash

    def test_map_langgraph_event_llm_end_with_text_string(self):
        mock_output = MagicMock()
        mock_output.text = "good text"
        mock_output.content = None
        
        event = {
            "event": "on_chat_model_end",
            "run_id": "test_run",
            "name": "test_node",
            "data": {"output": mock_output},
            "metadata": {"langgraph_node": "test_node"}
        }
        
        result = self.engine._map_langgraph_event("run_123", event)
        self.assertEqual(result["response"], "good text")

if __name__ == "__main__":
    unittest.main()
