"""
Test script to validate multi-provider LLM support.

This script tests the LLM factory and provider initialization without
making actual API calls.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingagents.llm_factory import LLMFactory, get_llm_instance
from tradingagents.default_config import DEFAULT_CONFIG


def test_factory_creation():
    """Test that the factory can create instances for each provider."""
    print("Testing LLM Factory Creation...\n")
    
    providers = {
        "openai": {"model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"},
        "ollama": {"model": "llama3", "base_url": "http://localhost:11434"},
        "anthropic": {"model": "claude-3-haiku-20240307", "base_url": None},
        "google": {"model": "gemini-1.5-flash", "base_url": None},
    }
    
    results = {}
    
    for provider, params in providers.items():
        try:
            llm = LLMFactory.create_llm(
                provider=provider,
                model=params["model"],
                base_url=params["base_url"],
                temperature=0.7
            )
            results[provider] = "✅ SUCCESS"
            print(f"✅ {provider.upper()}: Created instance of {type(llm).__name__}")
        except ImportError as e:
            results[provider] = f"⚠️  MISSING PACKAGE: {str(e)}"
            print(f"⚠️  {provider.upper()}: {str(e)}")
        except Exception as e:
            results[provider] = f"❌ ERROR: {str(e)}"
            print(f"❌ {provider.upper()}: {str(e)}")
    
    print("\n" + "="*60)
    print("SUMMARY:")
    for provider, result in results.items():
        print(f"{provider.upper()}: {result}")
    print("="*60 + "\n")


def test_config_based_creation():
    """Test creating LLMs from config dictionaries."""
    print("Testing Config-Based LLM Creation...\n")
    
    configs = [
        {
            "name": "OpenAI",
            "config": {
                "llm_provider": "openai",
                "quick_think_llm": "gpt-4o-mini",
                "deep_think_llm": "gpt-4o",
                "backend_url": "https://api.openai.com/v1",
                "temperature": 0.7,
            }
        },
        {
            "name": "Ollama",
            "config": {
                "llm_provider": "ollama",
                "quick_think_llm": "llama3:8b",
                "deep_think_llm": "llama3:70b",
                "backend_url": "http://localhost:11434",
                "temperature": 0.7,
            }
        },
    ]
    
    for test_case in configs:
        name = test_case["name"]
        config = test_case["config"]
        
        try:
            quick_llm = get_llm_instance(config, model_type="quick_think")
            deep_llm = get_llm_instance(config, model_type="deep_think")
            print(f"✅ {name}: Created quick_think ({type(quick_llm).__name__}) and deep_think ({type(deep_llm).__name__})")
        except ImportError as e:
            print(f"⚠️  {name}: Missing package - {str(e)}")
        except Exception as e:
            print(f"❌ {name}: Error - {str(e)}")
    
    print()


def test_default_config():
    """Test the default configuration."""
    print("Testing Default Configuration...\n")
    
    try:
        provider = DEFAULT_CONFIG.get("llm_provider", "unknown")
        deep_model = DEFAULT_CONFIG.get("deep_think_llm", "unknown")
        quick_model = DEFAULT_CONFIG.get("quick_think_llm", "unknown")
        
        print(f"Default Provider: {provider}")
        print(f"Deep Think Model: {deep_model}")
        print(f"Quick Think Model: {quick_model}")
        
        # Try creating instances
        deep_llm = get_llm_instance(DEFAULT_CONFIG, model_type="deep_think")
        quick_llm = get_llm_instance(DEFAULT_CONFIG, model_type="quick_think")
        
        print(f"✅ Successfully created default LLM instances")
        print(f"   Deep: {type(deep_llm).__name__}")
        print(f"   Quick: {type(quick_llm).__name__}")
    except Exception as e:
        print(f"❌ Error with default config: {str(e)}")
    
    print()


def test_unsupported_provider():
    """Test handling of unsupported providers."""
    print("Testing Unsupported Provider Handling...\n")
    
    try:
        llm = LLMFactory.create_llm(
            provider="nonexistent_provider",
            model="some-model",
            temperature=0.7
        )
        print("❌ Should have raised ValueError for unsupported provider")
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
    
    print()


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("TRADINGAGENTS - MULTI-PROVIDER LLM SUPPORT TEST")
    print("="*60 + "\n")
    
    test_default_config()
    test_factory_creation()
    test_config_based_creation()
    test_unsupported_provider()
    
    print("="*60)
    print("TEST COMPLETE")
    print("="*60)
    print("\nNotes:")
    print("- ✅ = Success")
    print("- ⚠️  = Missing optional package (install if you want to use that provider)")
    print("- ❌ = Error (needs investigation)")
    print("\nTo install missing packages:")
    print("  pip install langchain-community  # For Ollama")
    print("  pip install langchain-groq       # For Groq")
    print("  pip install langchain-together   # For Together AI")
    print()


if __name__ == "__main__":
    main()
