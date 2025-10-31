"""
Quick test script to verify Ollama integration with TradingAgents.
This script tests the LLM factory and creates a simple instance.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("="*60)
print("Testing Ollama Integration with TradingAgents")
print("="*60)
print()

# Test 1: Import the factory
print("Test 1: Importing LLM Factory...")
try:
    from tradingagents.llm_factory import LLMFactory, get_llm_instance
    print("✅ LLM Factory imported successfully")
except Exception as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)

print()

# Test 2: Import default config
print("Test 2: Importing default config...")
try:
    from tradingagents.default_config import DEFAULT_CONFIG
    print("✅ Default config imported successfully")
    print(f"   Current provider: {DEFAULT_CONFIG['llm_provider']}")
    print(f"   Deep think model: {DEFAULT_CONFIG['deep_think_llm']}")
    print(f"   Quick think model: {DEFAULT_CONFIG['quick_think_llm']}")
except Exception as e:
    print(f"❌ Failed to import config: {e}")
    sys.exit(1)

print()

# Test 3: Create Ollama config
print("Test 3: Creating Ollama configuration...")
try:
    ollama_config = DEFAULT_CONFIG.copy()
    ollama_config["llm_provider"] = "ollama"
    ollama_config["deep_think_llm"] = "llama3"  # Using available model
    ollama_config["quick_think_llm"] = "llama3"  # Using available model
    ollama_config["backend_url"] = "http://localhost:11434"
    print("✅ Ollama config created")
    print(f"   Provider: {ollama_config['llm_provider']}")
    print(f"   Deep think: {ollama_config['deep_think_llm']}")
    print(f"   Quick think: {ollama_config['quick_think_llm']}")
    print(f"   Endpoint: {ollama_config['backend_url']}")
except Exception as e:
    print(f"❌ Failed to create config: {e}")
    sys.exit(1)

print()

# Test 4: Check if langchain-community is installed
print("Test 4: Checking for langchain-community package...")
try:
    from langchain_community.chat_models import ChatOllama
    print("✅ langchain-community is installed")
except ImportError:
    print("⚠️  langchain-community is NOT installed")
    print("   Installing now...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "langchain-community", "-q"])
        print("✅ langchain-community installed successfully")
    except Exception as e:
        print(f"❌ Failed to install: {e}")
        print("\nPlease install manually:")
        print("   pip install langchain-community")
        sys.exit(1)

print()

# Test 5: Create LLM instance using factory
print("Test 5: Creating Ollama LLM instance using factory...")
try:
    llm = get_llm_instance(ollama_config, model_type="quick_think")
    print(f"✅ LLM instance created: {type(llm).__name__}")
except Exception as e:
    print(f"❌ Failed to create LLM: {e}")
    print("\nMake sure Ollama is running:")
    print("   ollama serve")
    sys.exit(1)

print()

# Test 6: Test LLM with a simple query
print("Test 6: Testing LLM with a simple query...")
print("   Sending: 'What is 2+2? Answer with just the number.'")
try:
    response = llm.invoke("What is 2+2? Answer with just the number.")
    print(f"✅ LLM responded: {response.content}")
except Exception as e:
    print(f"❌ Failed to get response: {e}")
    print("\nMake sure Ollama is running and the model is available:")
    print("   ollama serve")
    print("   ollama pull llama3")
    sys.exit(1)

print()

# Test 7: Try creating TradingAgentsGraph with Ollama
print("Test 7: Creating TradingAgentsGraph with Ollama...")
try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    print("✅ Imported TradingAgentsGraph")
    
    # Create graph with Ollama config
    ta = TradingAgentsGraph(config=ollama_config, debug=False)
    print("✅ TradingAgentsGraph created successfully with Ollama!")
    print(f"   Deep thinking LLM: {type(ta.deep_thinking_llm).__name__}")
    print(f"   Quick thinking LLM: {type(ta.quick_thinking_llm).__name__}")
except Exception as e:
    print(f"❌ Failed to create TradingAgentsGraph: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("="*60)
print("🎉 ALL TESTS PASSED!")
print("="*60)
print()
print("✅ Ollama integration is working correctly!")
print()
print("You can now use TradingAgents with Ollama:")
print("""
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config['llm_provider'] = 'ollama'
config['deep_think_llm'] = 'llama3'
config['quick_think_llm'] = 'llama3'
config['backend_url'] = 'http://localhost:11434'

ta = TradingAgentsGraph(config=config, debug=True)
_, decision = ta.propagate("AAPL", "2024-05-10")
print(decision)
""")
