#!/usr/bin/env python3
"""
Orchestrator configuration validation examples.

Demonstrates provider mismatch detection and timeout validation.
"""

import logging
import sys
from pathlib import Path

# Add parent directories to path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from orchestrator.config import OrchestratorConfig
from orchestrator.llm_runner import LLMRunner

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


def example_1_provider_mismatch():
    """Example 1: Provider mismatch detection."""
    print("=" * 60)
    print("Example 1: Provider Mismatch Detection")
    print("=" * 60)

    # Invalid: Google provider with OpenAI URL
    cfg = OrchestratorConfig(
        cache_dir="/tmp/orchestrator_validation_example",
        trading_agents_config={
            "llm_provider": "google",
            "backend_url": "https://api.openai.com/v1",
        },
    )

    runner = LLMRunner(cfg)
    signal = runner.get_signal("AAPL", "2024-01-02")

    print(f"\nConfiguration:")
    print(f"  Provider: google")
    print(f"  Base URL: https://api.openai.com/v1")
    print(f"\nResult:")
    print(f"  Degraded: {signal.degraded}")
    print(f"  Reason: {signal.reason_code}")
    print(f"  Message: {signal.metadata.get('error', 'N/A')}")
    print(f"  Expected patterns: {signal.metadata.get('data_quality', {}).get('expected_patterns', [])}")
    print()


def example_2_valid_configuration():
    """Example 2: Valid configuration (no mismatch)."""
    print("=" * 60)
    print("Example 2: Valid Configuration")
    print("=" * 60)

    # Valid: Anthropic provider with MiniMax Anthropic-compatible URL
    cfg = OrchestratorConfig(
        cache_dir="/tmp/orchestrator_validation_example",
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "selected_analysts": ["market"],
            "analyst_node_timeout_secs": 75.0,
        },
    )

    runner = LLMRunner(cfg)
    mismatch = runner._detect_provider_mismatch()

    print(f"\nConfiguration:")
    print(f"  Provider: anthropic")
    print(f"  Base URL: https://api.minimaxi.com/anthropic")
    print(f"  Selected analysts: ['market']")
    print(f"  Analyst timeout: 75.0s")
    print(f"\nResult:")
    print(f"  Mismatch detected: {mismatch is not None}")
    if mismatch:
        print(f"  Details: {mismatch}")
    else:
        print(f"  Status: Configuration is valid ✓")
    print()


def example_3_timeout_warning():
    """Example 3: Timeout configuration warning."""
    print("=" * 60)
    print("Example 3: Timeout Configuration Warning")
    print("=" * 60)

    # Warning: 4 analysts with insufficient timeout
    print("\nConfiguration:")
    print(f"  Provider: anthropic")
    print(f"  Base URL: https://api.minimaxi.com/anthropic")
    print(f"  Selected analysts: ['market', 'social', 'news', 'fundamentals']")
    print(f"  Analyst timeout: 75.0s (recommended: 120.0s)")
    print(f"\nExpected warning:")

    cfg = OrchestratorConfig(
        cache_dir="/tmp/orchestrator_validation_example",
        trading_agents_config={
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic",
            "selected_analysts": ["market", "social", "news", "fundamentals"],
            "analyst_node_timeout_secs": 75.0,
        },
    )

    # Warning will be logged during initialization
    runner = LLMRunner(cfg)
    print()


def example_4_multiple_mismatches():
    """Example 4: Multiple provider mismatch scenarios."""
    print("=" * 60)
    print("Example 4: Multiple Provider Mismatch Scenarios")
    print("=" * 60)

    scenarios = [
        ("xai", "https://api.minimaxi.com/anthropic"),
        ("ollama", "https://api.openai.com/v1"),
        ("openrouter", "https://api.anthropic.com/v1"),
    ]

    for provider, url in scenarios:
        cfg = OrchestratorConfig(
            cache_dir="/tmp/orchestrator_validation_example",
            trading_agents_config={
                "llm_provider": provider,
                "backend_url": url,
            },
        )

        runner = LLMRunner(cfg)
        signal = runner.get_signal("AAPL", "2024-01-02")

        print(f"\n  {provider} + {url}")
        print(f"    → Degraded: {signal.degraded}, Reason: {signal.reason_code}")


if __name__ == "__main__":
    example_1_provider_mismatch()
    example_2_valid_configuration()
    example_3_timeout_warning()
    example_4_multiple_mismatches()

    print("=" * 60)
    print("All examples completed")
    print("=" * 60)
