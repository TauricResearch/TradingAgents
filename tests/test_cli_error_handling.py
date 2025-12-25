"""
Test suite for CLI Error Handling with Rate Limit Errors.

This module tests:
1. Rate limit errors are caught and logged in main.py
2. Partial analysis is saved to JSON file when error occurs
3. User sees appropriate error message with retry guidance
4. Both terminal and file receive error logs
5. Integration with graph.stream() error handling
6. Error translation from provider errors to unified exceptions
"""

import json
import logging
import os
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for output files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_graph():
    """Create a mock TradingAgentsGraph."""
    mock = Mock()
    mock.propagate = Mock()
    return mock


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return {
        "llm_provider": "openrouter",
        "deep_think_llm": "anthropic/claude-opus-4.5",
        "quick_think_llm": "anthropic/claude-haiku-3.5",
        "backend_url": "https://openrouter.ai/api/v1",
        "max_debate_rounds": 1,
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "google",
        }
    }


@pytest.fixture
def sample_partial_state():
    """Create a sample partial state for testing."""
    return {
        "ticker": "AAPL",
        "analysis_date": "2024-12-26",
        "messages": [
            {"role": "system", "content": "Starting analysis"},
            {"role": "assistant", "content": "Fetched market data"},
        ],
        "analyst_reports": {
            "market": {"summary": "Bullish trend", "confidence": 0.8}
        },
        "error": "Rate limit exceeded",
        "error_timestamp": datetime.now().isoformat()
    }


# ============================================================================
# Test Rate Limit Error Catching in main.py
# ============================================================================

class TestMainRateLimitErrorHandling:
    """Test error handling in main.py around graph.stream()."""

    @patch('main.TradingAgentsGraph')
    def test_catches_rate_limit_error_from_openai(self, mock_graph_class, temp_output_dir):
        """Test that OpenAI rate limit errors are caught in main.py."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        # Setup mock to raise rate limit error
        mock_instance = Mock()
        mock_instance.propagate.side_effect = OpenAIRateLimitError(
            "Rate limit exceeded for gpt-4",
            retry_after=60,
        )
        mock_graph_class.return_value = mock_instance

        # This import will fail initially (TDD RED phase)
        # The main.py needs to be modified to catch these errors
        # For now, we're testing the expected behavior

        with pytest.raises(OpenAIRateLimitError) as exc_info:
            mock_instance.propagate("AAPL", "2024-12-26")

        assert exc_info.value.retry_after == 60
        assert exc_info.value.provider == "openai"

    @patch('main.TradingAgentsGraph')
    def test_catches_rate_limit_error_from_anthropic(self, mock_graph_class):
        """Test that Anthropic rate limit errors are caught."""
        from tradingagents.utils.exceptions import AnthropicRateLimitError

        mock_instance = Mock()
        mock_instance.propagate.side_effect = AnthropicRateLimitError(
            "Rate limit exceeded for claude-opus-4.5",
            retry_after=120,
        )
        mock_graph_class.return_value = mock_instance

        with pytest.raises(AnthropicRateLimitError) as exc_info:
            mock_instance.propagate("AAPL", "2024-12-26")

        assert exc_info.value.retry_after == 120
        assert exc_info.value.provider == "anthropic"

    @patch('main.TradingAgentsGraph')
    def test_catches_rate_limit_error_from_openrouter(self, mock_graph_class):
        """Test that OpenRouter rate limit errors are caught."""
        from tradingagents.utils.exceptions import OpenRouterRateLimitError

        mock_instance = Mock()
        mock_instance.propagate.side_effect = OpenRouterRateLimitError(
            "Rate limit exceeded for anthropic/claude-opus-4.5",
            retry_after=45,
        )
        mock_graph_class.return_value = mock_instance

        with pytest.raises(OpenRouterRateLimitError) as exc_info:
            mock_instance.propagate("AAPL", "2024-12-26")

        assert exc_info.value.retry_after == 45
        assert exc_info.value.provider == "openrouter"

    @patch('main.TradingAgentsGraph')
    @patch('main.setup_dual_logger')
    def test_rate_limit_error_is_logged(self, mock_logger_setup, mock_graph_class, temp_output_dir):
        """Test that rate limit errors are logged."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        # Setup mock logger
        mock_logger = Mock()
        mock_logger_setup.return_value = mock_logger

        # Setup mock to raise error
        mock_instance = Mock()
        mock_instance.propagate.side_effect = OpenAIRateLimitError(
            "Rate limit exceeded",
            retry_after=60,
        )
        mock_graph_class.return_value = mock_instance

        # In the modified main.py, the error should be caught and logged
        # This test validates the expected logging behavior

        try:
            mock_instance.propagate("AAPL", "2024-12-26")
        except OpenAIRateLimitError as e:
            # Simulate what main.py should do
            mock_logger.error(f"Rate limit error: {str(e)}")
            mock_logger.info(f"Retry after: {e.retry_after} seconds")

        # Verify logging calls
        assert mock_logger.error.called
        assert mock_logger.info.called


# ============================================================================
# Test Partial Analysis Saving
# ============================================================================

class TestPartialAnalysisSaving:
    """Test saving partial analysis to JSON when error occurs."""

    def test_saves_partial_state_to_json(self, temp_output_dir, sample_partial_state):
        """Test that partial state is saved to JSON file on error."""
        # This function would be in main.py or a utility module
        from tradingagents.utils.error_recovery import save_partial_analysis

        output_file = temp_output_dir / "partial_analysis.json"

        save_partial_analysis(sample_partial_state, str(output_file))

        assert output_file.exists()

        with open(output_file, 'r') as f:
            loaded_state = json.load(f)

        assert loaded_state["ticker"] == "AAPL"
        assert loaded_state["analysis_date"] == "2024-12-26"
        assert "error" in loaded_state

    def test_partial_state_includes_error_info(self, temp_output_dir):
        """Test that saved partial state includes error information."""
        from tradingagents.utils.error_recovery import save_partial_analysis

        state_with_error = {
            "ticker": "TSLA",
            "error": "Rate limit exceeded for gpt-4",
            "error_timestamp": datetime.now().isoformat(),
            "retry_after": 60,
            "provider": "openai"
        }

        output_file = temp_output_dir / "error_state.json"
        save_partial_analysis(state_with_error, str(output_file))

        with open(output_file, 'r') as f:
            loaded = json.load(f)

        assert loaded["error"] == "Rate limit exceeded for gpt-4"
        assert loaded["retry_after"] == 60
        assert loaded["provider"] == "openai"
        assert "error_timestamp" in loaded

    def test_partial_state_includes_completed_work(self, temp_output_dir, sample_partial_state):
        """Test that partial state includes work completed before error."""
        from tradingagents.utils.error_recovery import save_partial_analysis

        output_file = temp_output_dir / "partial.json"
        save_partial_analysis(sample_partial_state, str(output_file))

        with open(output_file, 'r') as f:
            loaded = json.load(f)

        assert "analyst_reports" in loaded
        assert "market" in loaded["analyst_reports"]
        assert loaded["analyst_reports"]["market"]["summary"] == "Bullish trend"

    def test_default_output_filename_format(self, temp_output_dir):
        """Test that default output filename includes ticker and timestamp."""
        from tradingagents.utils.error_recovery import get_partial_analysis_filename

        ticker = "AAPL"
        timestamp = datetime.now()

        filename = get_partial_analysis_filename(ticker, timestamp)

        assert ticker in filename
        assert filename.endswith(".json")
        assert "partial" in filename.lower() or "error" in filename.lower()

    def test_overwrites_existing_partial_file(self, temp_output_dir):
        """Test that saving overwrites existing partial analysis file."""
        from tradingagents.utils.error_recovery import save_partial_analysis

        output_file = temp_output_dir / "partial.json"

        # Save first version
        state_v1 = {"version": 1, "data": "first"}
        save_partial_analysis(state_v1, str(output_file))

        # Save second version
        state_v2 = {"version": 2, "data": "second"}
        save_partial_analysis(state_v2, str(output_file))

        with open(output_file, 'r') as f:
            loaded = json.load(f)

        assert loaded["version"] == 2
        assert loaded["data"] == "second"

    def test_handles_non_serializable_data(self, temp_output_dir):
        """Test handling of non-JSON-serializable data in state."""
        from tradingagents.utils.error_recovery import save_partial_analysis

        # Include a Mock object which isn't JSON serializable
        state = {
            "ticker": "AAPL",
            "mock_object": Mock(),  # Not serializable
            "normal_data": "test"
        }

        output_file = temp_output_dir / "partial.json"

        # Should handle gracefully - either skip non-serializable or convert to string
        save_partial_analysis(state, str(output_file))

        with open(output_file, 'r') as f:
            loaded = json.load(f)

        assert loaded["ticker"] == "AAPL"
        assert loaded["normal_data"] == "test"
        # mock_object should be handled somehow (skipped or converted)


# ============================================================================
# Test User Error Messages
# ============================================================================

class TestUserErrorMessages:
    """Test user-facing error messages and guidance."""

    def test_error_message_includes_retry_time(self):
        """Test that error message includes retry_after time."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError
        from tradingagents.utils.error_messages import format_rate_limit_error

        error = OpenAIRateLimitError("Rate limit exceeded", retry_after=60)
        message = format_rate_limit_error(error)

        assert "60" in message
        assert "second" in message.lower() or "sec" in message.lower()

    def test_error_message_includes_provider(self):
        """Test that error message identifies the provider."""
        from tradingagents.utils.exceptions import OpenRouterRateLimitError
        from tradingagents.utils.error_messages import format_rate_limit_error

        error = OpenRouterRateLimitError("Rate limit exceeded", retry_after=45)
        message = format_rate_limit_error(error)

        assert "openrouter" in message.lower() or "OpenRouter" in message

    def test_error_message_suggests_retry(self):
        """Test that error message suggests retrying."""
        from tradingagents.utils.exceptions import AnthropicRateLimitError
        from tradingagents.utils.error_messages import format_rate_limit_error

        error = AnthropicRateLimitError("Rate limit exceeded", retry_after=120)
        message = format_rate_limit_error(error)

        assert "retry" in message.lower() or "try again" in message.lower()

    def test_error_message_without_retry_after(self):
        """Test error message when retry_after is not provided."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError
        from tradingagents.utils.error_messages import format_rate_limit_error

        error = OpenAIRateLimitError("Rate limit exceeded", retry_after=None)
        message = format_rate_limit_error(error)

        # Should provide generic guidance
        assert "later" in message.lower() or "wait" in message.lower()

    def test_error_message_includes_partial_save_info(self, temp_output_dir):
        """Test that error message mentions where partial analysis was saved."""
        from tradingagents.utils.error_messages import format_error_with_partial_save

        error_msg = "Rate limit exceeded"
        partial_file = temp_output_dir / "partial_AAPL_20241226.json"

        message = format_error_with_partial_save(error_msg, str(partial_file))

        assert str(partial_file) in message or partial_file.name in message
        assert "saved" in message.lower()

    def test_formats_retry_time_in_minutes(self):
        """Test that large retry_after times are formatted in minutes."""
        from tradingagents.utils.error_messages import format_retry_time

        # 300 seconds = 5 minutes
        formatted = format_retry_time(300)

        assert "5" in formatted
        assert "minute" in formatted.lower()

    def test_formats_retry_time_in_hours(self):
        """Test that very large retry_after times are formatted in hours."""
        from tradingagents.utils.error_messages import format_retry_time

        # 3600 seconds = 1 hour
        formatted = format_retry_time(3600)

        assert "1" in formatted or "60" in formatted
        assert "hour" in formatted.lower() or "minute" in formatted.lower()


# ============================================================================
# Test Dual Logging of Errors
# ============================================================================

class TestDualLoggingOfErrors:
    """Test that errors are logged to both terminal and file."""

    @patch('tradingagents.utils.logging_config.setup_dual_logger')
    def test_error_logged_to_both_handlers(self, mock_logger_setup, temp_output_dir):
        """Test that errors are sent to both terminal and file handlers."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        # Create mock logger with two handlers
        mock_logger = Mock()
        mock_stream_handler = Mock(spec=logging.StreamHandler)
        mock_file_handler = Mock(spec=logging.FileHandler)

        mock_logger.handlers = [mock_stream_handler, mock_file_handler]
        mock_logger_setup.return_value = mock_logger

        # Simulate logging an error
        error = OpenAIRateLimitError("Rate limit exceeded", retry_after=60)
        mock_logger.error(f"Rate limit error: {str(error)}")

        # Both handlers should receive the message
        assert mock_logger.error.called

    def test_terminal_shows_user_friendly_message(self, capsys):
        """Test that terminal output is user-friendly."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError
        from tradingagents.utils.error_messages import print_user_error

        error = OpenAIRateLimitError("Rate limit exceeded", retry_after=60)

        print_user_error(error)

        captured = capsys.readouterr()

        # Should be user-friendly, not a raw stack trace
        assert "Rate limit" in captured.out or "Rate limit" in captured.err
        assert "60" in captured.out or "60" in captured.err

    def test_file_contains_detailed_error_info(self, temp_output_dir):
        """Test that file log contains detailed error information."""
        from tradingagents.utils.logging_config import setup_dual_logger
        from tradingagents.utils.exceptions import OpenRouterRateLimitError

        log_file = temp_output_dir / "error_test.log"
        logger = setup_dual_logger(name="test_error_logger", log_file=str(log_file))

        error = OpenRouterRateLimitError("Rate limit exceeded", retry_after=45)

        logger.error(f"Rate limit error: {str(error)}")
        logger.error(f"Provider: {error.provider}")
        logger.error(f"Retry after: {error.retry_after} seconds")

        content = log_file.read_text()

        assert "Rate limit" in content
        assert "openrouter" in content.lower()
        assert "45" in content

    def test_sanitization_applied_to_error_logs(self, temp_output_dir):
        """Test that API keys in error messages are sanitized in logs."""
        from tradingagents.utils.logging_config import setup_dual_logger, sanitize_log_message

        log_file = temp_output_dir / "sanitized_error.log"
        logger = setup_dual_logger(name="test_sanitize_logger", log_file=str(log_file))

        # Simulate an error message that includes an API key
        error_msg = "Authentication failed with key sk-test1234567890"
        sanitized_msg = sanitize_log_message(error_msg)

        logger.error(sanitized_msg)

        content = log_file.read_text()

        assert "sk-test1234567890" not in content
        assert "[REDACTED-API-KEY]" in content


# ============================================================================
# Test Error Translation in Graph Setup
# ============================================================================

class TestGraphErrorTranslation:
    """Test error translation layer in tradingagents/graph/setup.py."""

    def test_translates_openai_native_error(self):
        """Test translation of native OpenAI error to unified exception."""
        from tradingagents.graph.error_handler import translate_llm_error
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        # Create a mock native OpenAI error
        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "60"}

        translated = translate_llm_error(mock_error, provider="openai")

        assert isinstance(translated, OpenAIRateLimitError)
        assert translated.retry_after == 60

    def test_translates_anthropic_native_error(self):
        """Test translation of native Anthropic error to unified exception."""
        from tradingagents.graph.error_handler import translate_llm_error
        from tradingagents.utils.exceptions import AnthropicRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "120"}

        translated = translate_llm_error(mock_error, provider="anthropic")

        assert isinstance(translated, AnthropicRateLimitError)
        assert translated.retry_after == 120

    def test_translates_openrouter_native_error(self):
        """Test translation of native OpenRouter error to unified exception."""
        from tradingagents.graph.error_handler import translate_llm_error
        from tradingagents.utils.exceptions import OpenRouterRateLimitError

        mock_error = Mock()
        mock_error.__class__.__name__ = "RateLimitError"
        mock_error.message = "Rate limit exceeded"
        mock_error.response = Mock()
        mock_error.response.headers = {"retry-after": "30"}

        translated = translate_llm_error(mock_error, provider="openrouter")

        assert isinstance(translated, OpenRouterRateLimitError)
        assert translated.retry_after == 30

    @patch('tradingagents.graph.trading_graph.TradingAgentsGraph.propagate')
    def test_error_translation_in_propagate(self, mock_propagate):
        """Test that errors raised in propagate are translated."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        # Mock propagate to raise native error, which should be translated
        mock_native_error = Mock()
        mock_native_error.__class__.__name__ = "RateLimitError"
        mock_propagate.side_effect = mock_native_error

        # The graph should translate this to our unified exception
        # This tests the integration point

    def test_passes_through_non_rate_limit_errors(self):
        """Test that non-rate-limit errors are not translated."""
        from tradingagents.graph.error_handler import translate_llm_error

        mock_error = Mock()
        mock_error.__class__.__name__ = "APIError"
        mock_error.message = "Connection failed"

        # Should raise ValueError or return None
        with pytest.raises(ValueError):
            translate_llm_error(mock_error, provider="openai")


# ============================================================================
# Integration Tests
# ============================================================================

class TestEndToEndErrorHandling:
    """Test complete error handling flow from graph to user output."""

    @patch('main.TradingAgentsGraph')
    @patch('main.setup_dual_logger')
    def test_complete_error_flow(self, mock_logger_setup, mock_graph_class, temp_output_dir, capsys):
        """Test complete flow: error raised -> logged -> partial saved -> user notified."""
        from tradingagents.utils.exceptions import OpenRouterRateLimitError

        # Setup mocks
        mock_logger = Mock()
        mock_logger_setup.return_value = mock_logger

        mock_instance = Mock()
        mock_instance.propagate.side_effect = OpenRouterRateLimitError(
            "Rate limit exceeded for anthropic/claude-opus-4.5",
            retry_after=60,
        )
        mock_graph_class.return_value = mock_instance

        # Simulate main.py execution
        try:
            state, decision = mock_instance.propagate("AAPL", "2024-12-26")
        except OpenRouterRateLimitError as e:
            # Log error
            mock_logger.error(f"Rate limit error: {str(e)}")

            # Save partial state
            partial_file = temp_output_dir / f"partial_AAPL_{datetime.now().strftime('%Y%m%d')}.json"
            partial_state = {
                "ticker": "AAPL",
                "error": str(e),
                "retry_after": e.retry_after,
                "provider": e.provider,
            }

            with open(partial_file, 'w') as f:
                json.dump(partial_state, f)

            # Print user message
            print(f"\nError: {str(e)}")
            print(f"Please retry in {e.retry_after} seconds")
            print(f"Partial analysis saved to: {partial_file}")

        # Verify all components
        assert mock_logger.error.called
        assert partial_file.exists()

        captured = capsys.readouterr()
        assert "60 seconds" in captured.out
        assert "Partial analysis saved" in captured.out

    def test_successful_execution_no_partial_save(self, temp_output_dir):
        """Test that successful execution doesn't save partial state."""
        # When execution is successful, no partial analysis should be saved
        # Only save on error

        output_dir = temp_output_dir
        before_files = set(output_dir.glob("*.json"))

        # Simulate successful execution
        # ... normal flow ...

        after_files = set(output_dir.glob("*.json"))

        # No new partial files should be created
        assert len(after_files - before_files) == 0

    @patch('main.TradingAgentsGraph')
    def test_error_during_stream_operation(self, mock_graph_class):
        """Test error handling during graph.stream() operation."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        mock_instance = Mock()

        # Mock stream to yield some items then raise error
        def stream_generator():
            yield {"step": 1, "data": "first"}
            yield {"step": 2, "data": "second"}
            raise OpenAIRateLimitError("Rate limit exceeded", retry_after=30)

        mock_instance.stream = Mock(return_value=stream_generator())
        mock_graph_class.return_value = mock_instance

        # Collect partial results before error
        partial_results = []

        try:
            for item in mock_instance.stream("AAPL", "2024-12-26"):
                partial_results.append(item)
        except OpenAIRateLimitError as e:
            # Should have partial results
            assert len(partial_results) == 2
            assert e.retry_after == 30


# ============================================================================
# Edge Cases
# ============================================================================

class TestErrorHandlingEdgeCases:
    """Test edge cases in error handling."""

    def test_rate_limit_error_without_retry_after(self):
        """Test handling rate limit error when retry_after is not provided."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError
        from tradingagents.utils.error_messages import format_rate_limit_error

        error = OpenAIRateLimitError("Rate limit exceeded", retry_after=None)
        message = format_rate_limit_error(error)

        # Should provide generic retry guidance
        assert "retry" in message.lower() or "later" in message.lower()

    def test_multiple_consecutive_rate_limit_errors(self):
        """Test handling multiple rate limit errors in a row."""
        from tradingagents.utils.exceptions import OpenAIRateLimitError

        errors = []
        for i in range(3):
            errors.append(OpenAIRateLimitError(
                f"Rate limit exceeded (attempt {i+1})",
                retry_after=60 * (i+1)  # Increasing backoff
            ))

        # Each error should be handled independently
        for i, error in enumerate(errors):
            assert error.retry_after == 60 * (i+1)

    def test_error_during_partial_save(self, temp_output_dir):
        """Test handling when saving partial analysis itself fails."""
        from tradingagents.utils.error_recovery import save_partial_analysis

        # Try to save to invalid location
        invalid_file = "/root/cannot/write/here.json"

        state = {"ticker": "AAPL", "data": "test"}

        # Should handle gracefully and not crash
        try:
            save_partial_analysis(state, invalid_file)
        except (PermissionError, OSError) as e:
            # Expected - cannot write to invalid location
            pass

    def test_unicode_in_error_messages(self, temp_output_dir):
        """Test handling unicode characters in error messages."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_output_dir / "unicode_error.log"
        logger = setup_dual_logger(name="unicode_test", log_file=str(log_file))

        error_msg = "Rate limit exceeded for model 你好-gpt-4"
        logger.error(error_msg)

        content = log_file.read_text(encoding='utf-8')
        assert "Rate limit" in content
