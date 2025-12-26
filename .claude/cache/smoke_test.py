"""Quick smoke test for OpenRouter integration."""
from spektiv.graph.trading_graph import TradingAgentsGraph
from spektiv.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
import os

load_dotenv()

# Verify API key is set
openrouter_key = os.getenv('OPENROUTER_API_KEY')
if openrouter_key:
    print(f'OPENROUTER_API_KEY: sk-or-...{openrouter_key[-4:]}')
else:
    print('ERROR: OPENROUTER_API_KEY not set')
    exit(1)

# Create OpenRouter config
config = DEFAULT_CONFIG.copy()
config['llm_provider'] = 'openrouter'
config['deep_think_llm'] = 'anthropic/claude-opus-4.5'
config['quick_think_llm'] = 'anthropic/claude-opus-4.5'
config['backend_url'] = 'https://openrouter.ai/api/v1'

# Test initialization
print('Initializing TradingAgentsGraph with OpenRouter...')
ta = TradingAgentsGraph(debug=False, config=config)
print('SUCCESS: TradingAgentsGraph initialized with OpenRouter!')
print(f'  Provider: {ta.config["llm_provider"]}')
print(f'  Deep LLM: {ta.config["deep_think_llm"]}')
print(f'  Quick LLM: {ta.config["quick_think_llm"]}')
print(f'  Backend: {ta.config["backend_url"]}')
