#!/usr/bin/env python3
"""
Environment Setup Checker for TradingAgents
Checks if the necessary API keys are configured for your provider combination.
"""

import os
import sys
from pathlib import Path

# Try to import dotenv, but provide fallback if not available
try:
    from dotenv import load_dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

    def load_dotenv(path):
        """Simple fallback .env file parser if python-dotenv is not installed."""
        if not path.exists():
            return

        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=VALUE
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value


def check_api_keys():
    """Check which API keys are configured."""
    print("\n" + "=" * 70)
    print("TradingAgents - Environment Setup Checker")
    print("=" * 70)

    # Check for .env file
    env_file = Path(".env")
    env_example_file = Path(".env.example")

    print("\n0. Environment File Status:")
    print("-" * 70)

    if env_file.exists():
        print(f"   ✅ .env file found: {env_file.absolute()}")
        # Load .env file
        load_dotenv(env_file)
        if HAS_DOTENV:
            print(
                "      Loaded environment variables from .env file (using python-dotenv)"
            )
        else:
            print(
                "      Loaded environment variables from .env file (using built-in parser)"
            )
    else:
        print(f"   ⚠️  .env file not found: {env_file.absolute()}")
        if env_example_file.exists():
            print(f"      Hint: Copy .env.example to .env and add your API keys")
            print(f"      Command: cp .env.example .env")
        else:
            print(f"      Create a .env file with your API keys")

    # Check for common API keys (after loading .env)
    api_keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
    }

    print("\n1. API Keys Status:")
    print("-" * 70)

    for key_name, key_value in api_keys.items():
        if key_value:
            # Mask the key for security
            masked = (
                key_value[:8] + "..." + key_value[-4:] if len(key_value) > 12 else "***"
            )
            print(f"   ✅ {key_name}: {masked}")
        else:
            print(f"   ❌ {key_name}: Not set")

    print("\n2. Common Configuration Scenarios:")
    print("-" * 70)

    # Scenario 1: OpenRouter + OpenAI embeddings
    if api_keys["OPENROUTER_API_KEY"] and api_keys["OPENAI_API_KEY"]:
        print("   ✅ OpenRouter (chat) + OpenAI (embeddings) - READY")
    elif api_keys["OPENROUTER_API_KEY"] and not api_keys["OPENAI_API_KEY"]:
        print("   ⚠️  OpenRouter (chat) + OpenAI (embeddings) - MISSING OPENAI_API_KEY")
        print("      You need to set OPENAI_API_KEY for embeddings!")

    # Scenario 2: OpenAI everything
    if api_keys["OPENAI_API_KEY"]:
        print("   ✅ OpenAI (chat + embeddings) - READY")

    # Scenario 3: Anthropic + OpenAI embeddings
    if api_keys["ANTHROPIC_API_KEY"] and api_keys["OPENAI_API_KEY"]:
        print("   ✅ Anthropic (chat) + OpenAI (embeddings) - READY")
    elif api_keys["ANTHROPIC_API_KEY"] and not api_keys["OPENAI_API_KEY"]:
        print("   ⚠️  Anthropic (chat) + OpenAI (embeddings) - MISSING OPENAI_API_KEY")

    # Scenario 4: Google + OpenAI embeddings
    if api_keys["GOOGLE_API_KEY"] and api_keys["OPENAI_API_KEY"]:
        print("   ✅ Google (chat) + OpenAI (embeddings) - READY")
    elif api_keys["GOOGLE_API_KEY"] and not api_keys["OPENAI_API_KEY"]:
        print("   ⚠️  Google (chat) + OpenAI (embeddings) - MISSING OPENAI_API_KEY")

    print("\n3. How to Fix:")
    print("-" * 70)

    if not api_keys["OPENAI_API_KEY"]:
        print("\n   For OpenAI embeddings (recommended), set:")
        print("   export OPENAI_API_KEY='sk-...'")
        print("\n   Or add to your .env file:")
        print("   OPENAI_API_KEY=sk-...")

    if not api_keys["OPENROUTER_API_KEY"]:
        print("\n   For OpenRouter chat models, set:")
        print("   export OPENROUTER_API_KEY='sk-or-...'")
        print("\n   Or add to your .env file:")
        print("   OPENROUTER_API_KEY=sk-or-...")

    print("\n4. Configuration Example:")
    print("-" * 70)
    print("""
   For OpenRouter (chat) + OpenAI (embeddings):

   Option A: Set in terminal (temporary):

   export OPENROUTER_API_KEY="sk-or-v1-..."
   export OPENAI_API_KEY="sk-proj-..."

   Option B: Add to .env file (permanent - recommended):

   Create/edit .env file in this directory with:

   OPENROUTER_API_KEY=sk-or-v1-...
   OPENAI_API_KEY=sk-proj-...

   In your config:

   config = {
       # Chat with OpenRouter
       "llm_provider": "openrouter",
       "backend_url": "https://openrouter.ai/api/v1",
       "deep_think_llm": "deepseek/deepseek-chat-v3-0324:free",
       "quick_think_llm": "meta-llama/llama-3.3-8b-instruct:free",

       # Embeddings with OpenAI (separate!)
       "embedding_provider": "openai",
       "embedding_backend_url": "https://api.openai.com/v1",
       "embedding_model": "text-embedding-3-small",
       "enable_memory": True,
   }
    """)

    print("\n5. Alternative: Disable Memory")
    print("-" * 70)
    print("""
   If you don't want to use embeddings/memory, you can disable it:

   config = {
       "llm_provider": "openrouter",
       "backend_url": "https://openrouter.ai/api/v1",
       "enable_memory": False,  # Disable embeddings
   }

   This will run without memory but won't require an OpenAI API key.
    """)

    print("=" * 70)

    # Return status
    issues = []
    if not any(api_keys.values()):
        issues.append("No API keys found")

    return len(issues) == 0


if __name__ == "__main__":
    try:
        success = check_api_keys()

        if success:
            print("\n✅ Environment looks good! You have API keys configured.")
        else:
            print("\n⚠️  Please set the required API keys for your configuration.")

        print("\nFor more help, see: docs/EMBEDDING_CONFIGURATION.md\n")

    except Exception as e:
        print(f"\n❌ Error checking environment: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
