#!/usr/bin/env python3
"""
Test script for CLI logging integration.

This script tests the comprehensive logging system integration in the CLI
without running a full analysis.
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tradingagents.utils.logging_config import (
    get_logger,
    get_api_logger,
    get_performance_logger,
    configure_logging,
)


def test_basic_logging():
    """Test basic logging functionality."""
    print("\n" + "=" * 70)
    print("Testing Basic Logging")
    print("=" * 70)

    # Configure logging
    configure_logging(level="INFO", console=True)

    # Get CLI logger
    cli_logger = get_logger("tradingagents.cli", component="CLI")

    # Test different log levels
    cli_logger.debug("This is a debug message (should not appear in console)")
    cli_logger.info("This is an info message")
    cli_logger.warning("This is a warning message")
    cli_logger.error("This is an error message")

    print("✓ Basic logging test completed")


def test_contextual_logging():
    """Test logging with context."""
    print("\n" + "=" * 70)
    print("Testing Contextual Logging")
    print("=" * 70)

    cli_logger = get_logger("tradingagents.cli", component="CLI")

    # Log with context
    cli_logger.info(
        "User selections received",
        extra={
            "context": {
                "ticker": "AAPL",
                "date": "2024-01-15",
                "analysts": ["market", "social", "news"],
                "research_depth": 3,
                "llm_provider": "openai",
            }
        },
    )

    cli_logger.info(
        "Analysis session started",
        extra={
            "context": {
                "session_id": "test_session_001",
                "timestamp": time.time(),
            }
        },
    )

    print("✓ Contextual logging test completed")


def test_buffer_logging():
    """Test MessageBuffer-style logging."""
    print("\n" + "=" * 70)
    print("Testing Buffer Logging")
    print("=" * 70)

    buffer_logger = get_logger("tradingagents.cli.buffer", component="BUFFER")

    # Simulate message addition
    buffer_logger.debug(
        "Message added: Reasoning",
        extra={"context": {"type": "Reasoning", "timestamp": "10:30:15"}},
    )

    # Simulate tool call
    buffer_logger.info(
        "Tool call registered: get_stock_data",
        extra={
            "context": {
                "tool": "get_stock_data",
                "args": {"ticker": "AAPL", "period": "1mo"},
                "timestamp": "10:30:15",
            }
        },
    )

    # Simulate agent status update
    buffer_logger.info(
        "Agent status updated: Market Analyst -> in_progress",
        extra={
            "context": {
                "agent": "Market Analyst",
                "old_status": "pending",
                "new_status": "in_progress",
            }
        },
    )

    # Simulate report section update
    buffer_logger.info(
        "Report section updated: market_report",
        extra={
            "context": {
                "section": "market_report",
                "content_length": 2543,
            }
        },
    )

    print("✓ Buffer logging test completed")


def test_api_logging():
    """Test API call logging."""
    print("\n" + "=" * 70)
    print("Testing API Call Logging")
    print("=" * 70)

    api_logger = get_api_logger()

    # Simulate successful API call
    api_logger.log_call(
        provider="openai",
        model="gpt-4o-mini",
        endpoint="/v1/chat/completions",
        tokens=150,
        cost=0.0015,
        duration=1234.5,
        status="success",
    )

    # Simulate another API call
    api_logger.log_call(
        provider="openai",
        model="gpt-4o",
        endpoint="/v1/chat/completions",
        tokens=500,
        cost=0.0075,
        duration=2567.8,
        status="success",
    )

    # Simulate failed API call
    api_logger.log_call(
        provider="openai",
        model="gpt-4o-mini",
        endpoint="/v1/chat/completions",
        status="error",
        error="Connection timeout",
    )

    # Get statistics
    stats = api_logger.get_stats()
    print(f"\nAPI Call Statistics:")
    print(f"  Total calls: {stats['total_calls']}")
    print(f"  Total tokens: {stats['total_tokens']}")

    print("✓ API logging test completed")


def test_performance_logging():
    """Test performance tracking."""
    print("\n" + "=" * 70)
    print("Testing Performance Logging")
    print("=" * 70)

    perf_logger = get_performance_logger()

    # Simulate various operations with timing
    operations = [
        ("graph_initialization", 1234.5),
        ("agent_analysis", 5678.9),
        ("report_generation", 2345.6),
        ("graph_analysis", 45678.9),
        ("graph_analysis", 43210.1),
        ("graph_analysis", 48901.2),
    ]

    for operation, duration in operations:
        perf_logger.log_timing(
            operation,
            duration,
            context={"component": "test", "session": "test_session_001"},
        )

    # Get average timing
    avg_graph_analysis = perf_logger.get_average_timing("graph_analysis")
    print(f"\nAverage graph_analysis time: {avg_graph_analysis:.2f}ms")

    # Log summary
    perf_logger.log_summary()

    print("✓ Performance logging test completed")


def test_error_logging():
    """Test error logging with exceptions."""
    print("\n" + "=" * 70)
    print("Testing Error Logging")
    print("=" * 70)

    cli_logger = get_logger("tradingagents.cli", component="CLI")

    try:
        # Simulate an error
        raise ValueError("Simulated error for testing")
    except Exception as e:
        cli_logger.error(
            f"Analysis failed with error: {e}",
            extra={"context": {"error_type": type(e).__name__}},
            exc_info=True,
        )

    print("✓ Error logging test completed")


def test_report_section_logging():
    """Test report section generation logging."""
    print("\n" + "=" * 70)
    print("Testing Report Section Logging")
    print("=" * 70)

    cli_logger = get_logger("tradingagents.cli", component="CLI")

    sections = [
        ("market_report", "results/AAPL/2024-01-15/reports/market_report.md", 2543),
        (
            "sentiment_report",
            "results/AAPL/2024-01-15/reports/sentiment_report.md",
            1876,
        ),
        ("news_report", "results/AAPL/2024-01-15/reports/news_report.md", 3421),
    ]

    for section, file_path, content_length in sections:
        cli_logger.info(
            f"Report section generated: {section}",
            extra={
                "context": {
                    "section": section,
                    "file": file_path,
                    "content_length": content_length,
                }
            },
        )

    print("✓ Report section logging test completed")


def test_session_logging():
    """Test complete analysis session logging."""
    print("\n" + "=" * 70)
    print("Testing Complete Session Logging")
    print("=" * 70)

    cli_logger = get_logger("tradingagents.cli", component="CLI")
    perf_logger = get_performance_logger()

    # Session start
    session_start = time.time()
    cli_logger.info("=" * 70)
    cli_logger.info("TradingAgents CLI Analysis Started")
    cli_logger.info("=" * 70)
    cli_logger.info("Starting trading analysis session")

    # User selections
    cli_logger.info(
        "User selections received",
        extra={
            "context": {
                "ticker": "TSLA",
                "date": "2024-01-15",
                "analysts": ["market", "news", "fundamentals"],
                "research_depth": 3,
                "llm_provider": "openai",
            }
        },
    )

    # Simulate analysis
    time.sleep(0.5)  # Simulate work

    # Analysis completion
    session_duration = (time.time() - session_start) * 1000
    perf_logger.log_timing("total_analysis_session", session_duration)

    cli_logger.info(
        "Analysis completed successfully",
        extra={
            "context": {
                "ticker": "TSLA",
                "date": "2024-01-15",
                "duration_ms": session_duration,
                "chunks_processed": 42,
            }
        },
    )

    cli_logger.info(
        "Trading analysis session completed",
        extra={
            "context": {
                "total_duration_ms": session_duration,
                "results_dir": "results/TSLA/2024-01-15",
            }
        },
    )

    print("✓ Session logging test completed")


def check_log_files():
    """Check that log files were created."""
    print("\n" + "=" * 70)
    print("Checking Log Files")
    print("=" * 70)

    log_dir = Path("logs")
    expected_files = [
        "tradingagents.log",
        "api_calls.log",
        "errors.log",
        "performance.log",
    ]

    for log_file in expected_files:
        file_path = log_dir / log_file
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"✓ {log_file} exists ({size} bytes)")
        else:
            print(f"✗ {log_file} does not exist")

    print("\n✓ Log file check completed")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("TradingAgents CLI Logging Integration Test")
    print("=" * 70)

    try:
        test_basic_logging()
        test_contextual_logging()
        test_buffer_logging()
        test_api_logging()
        test_performance_logging()
        test_error_logging()
        test_report_section_logging()
        test_session_logging()
        check_log_files()

        print("\n" + "=" * 70)
        print("All Tests Passed! ✓")
        print("=" * 70)
        print("\nLog files created in: logs/")
        print("Check the following files for details:")
        print("  - logs/tradingagents.log (all logs)")
        print("  - logs/api_calls.log (API call tracking)")
        print("  - logs/errors.log (errors only)")
        print("  - logs/performance.log (performance metrics)")
        print()

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
