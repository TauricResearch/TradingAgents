#!/usr/bin/env python3
"""
Test script for embedding configuration functionality.

This script tests the new separated embedding configuration feature,
including different provider combinations and graceful fallback.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.default_config import DEFAULT_CONFIG


def test_memory_disabled():
    """Test memory with disabled configuration."""
    print("\n=== Test 1: Memory Disabled ===")
    config = {
        "embedding_provider": "none",
        "enable_memory": False,
    }

    memory = FinancialSituationMemory("test_disabled", config)

    assert not memory.is_enabled(), "Memory should be disabled"
    assert memory.get_memories("test") == [], "Should return empty list"

    result = memory.add_situations([("situation", "recommendation")])
    assert not result, "add_situations should return False when disabled"

    print("✅ Test passed: Memory correctly disabled")


def test_memory_openai_config():
    """Test memory with OpenAI configuration."""
    print("\n=== Test 2: OpenAI Configuration ===")
    config = {
        "embedding_provider": "openai",
        "embedding_backend_url": "https://api.openai.com/v1",
        "embedding_model": "text-embedding-3-small",
        "enable_memory": True,
    }

    memory = FinancialSituationMemory("test_openai", config)

    # Note: Will be disabled if no API key, but should initialize structure
    print(f"Memory enabled: {memory.is_enabled()}")
    print(f"Embedding provider: {memory.embedding_provider}")
    print(f"Embedding model: {memory.embedding_model}")
    print(f"Backend URL: {memory.embedding_backend_url}")

    assert memory.embedding_provider == "openai"
    assert memory.embedding_model == "text-embedding-3-small"

    print("✅ Test passed: OpenAI configuration correct")


def test_memory_ollama_config():
    """Test memory with Ollama configuration."""
    print("\n=== Test 3: Ollama Configuration ===")
    config = {
        "embedding_provider": "ollama",
        "embedding_backend_url": "http://localhost:11434/v1",
        "embedding_model": "nomic-embed-text",
        "enable_memory": True,
    }

    memory = FinancialSituationMemory("test_ollama", config)

    print(f"Memory enabled: {memory.is_enabled()}")
    print(f"Embedding provider: {memory.embedding_provider}")
    print(f"Embedding model: {memory.embedding_model}")
    print(f"Backend URL: {memory.embedding_backend_url}")

    assert memory.embedding_provider == "ollama"
    assert memory.embedding_model == "nomic-embed-text"

    print("✅ Test passed: Ollama configuration correct")


def test_default_config():
    """Test default configuration."""
    print("\n=== Test 4: Default Configuration ===")
    config = DEFAULT_CONFIG.copy()

    print(f"Default embedding provider: {config.get('embedding_provider')}")
    print(f"Default embedding model: {config.get('embedding_model')}")
    print(f"Default embedding URL: {config.get('embedding_backend_url')}")
    print(f"Default enable_memory: {config.get('enable_memory')}")

    assert config.get("embedding_provider") == "openai"
    assert config.get("embedding_model") == "text-embedding-3-small"
    assert config.get("enable_memory") == True

    print("✅ Test passed: Default configuration correct")


def test_mixed_providers():
    """Test mixing chat and embedding providers."""
    print("\n=== Test 5: Mixed Providers (OpenRouter + OpenAI) ===")
    config = {
        # Chat with OpenRouter
        "llm_provider": "openrouter",
        "backend_url": "https://openrouter.ai/api/v1",
        "deep_think_llm": "deepseek/deepseek-chat-v3-0324:free",
        "quick_think_llm": "meta-llama/llama-3.3-8b-instruct:free",
        # Embeddings with OpenAI
        "embedding_provider": "openai",
        "embedding_backend_url": "https://api.openai.com/v1",
        "embedding_model": "text-embedding-3-small",
        "enable_memory": True,
    }

    memory = FinancialSituationMemory("test_mixed", config)

    print(f"Chat provider: {config['llm_provider']}")
    print(f"Chat backend: {config['backend_url']}")
    print(f"Embedding provider: {memory.embedding_provider}")
    print(f"Embedding backend: {memory.embedding_backend_url}")

    # Verify they're different
    assert config["backend_url"] != memory.embedding_backend_url
    assert memory.embedding_provider == "openai"

    print("✅ Test passed: Mixed providers configured correctly")


def test_graceful_fallback():
    """Test graceful fallback with invalid configuration."""
    print("\n=== Test 6: Graceful Fallback ===")
    config = {
        "embedding_provider": "openai",
        "embedding_backend_url": "https://invalid-url-for-testing.example/v1",
        "enable_memory": True,
    }

    memory = FinancialSituationMemory("test_fallback", config)

    # Should disable itself on connection failure
    print(f"Memory enabled after invalid URL: {memory.is_enabled()}")

    # These should not crash
    result = memory.get_memories("test situation")
    assert result == [], "Should return empty list on failure"

    add_result = memory.add_situations([("situation", "recommendation")])
    # May be False if disabled

    print("✅ Test passed: Graceful fallback working")


def test_backward_compatibility():
    """Test backward compatibility with old configuration."""
    print("\n=== Test 7: Backward Compatibility ===")

    # Old-style config (no explicit embedding settings)
    old_config = {
        "llm_provider": "openai",
        "backend_url": "https://api.openai.com/v1",
        "deep_think_llm": "gpt-4o",
        "quick_think_llm": "gpt-4o-mini",
    }

    # Should work without embedding settings
    memory = FinancialSituationMemory("test_backward", old_config)

    print(f"Provider from old config: {memory.embedding_provider}")
    print(f"Model inferred: {memory.embedding_model}")

    # Should use smart defaults
    assert memory.embedding_model is not None

    print("✅ Test passed: Backward compatibility maintained")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Testing Embedding Configuration Feature")
    print("=" * 60)

    tests = [
        test_memory_disabled,
        test_memory_openai_config,
        test_memory_ollama_config,
        test_default_config,
        test_mixed_providers,
        test_graceful_fallback,
        test_backward_compatibility,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ Test failed: {test_func.__name__}")
            print(f"   Error: {str(e)}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    run_all_tests()
