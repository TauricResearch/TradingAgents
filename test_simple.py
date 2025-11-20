"""
简化版 TradingAgents 测试
跳过可能有问题的全球新闻分析，只测试核心功能
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config for DeepSeek API
config = DEFAULT_CONFIG.copy()

# Configure DeepSeek API
config["llm_provider"] = "openai"  # DeepSeek uses OpenAI-compatible API
config["backend_url"] = "https://api.deepseek.com"  # DeepSeek API endpoint
config["deep_think_llm"] = "deepseek-reasoner"  # DeepSeek reasoning model (思考模式)
config["quick_think_llm"] = "deepseek-chat"  # DeepSeek chat model (非思考模式)
config["max_debate_rounds"] = 1  # Debate rounds

# Configure data vendors - 使用 yfinance 作为主要数据源
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "yfinance",          # 改用 yfinance 避免 API 限制
    "news_data": "yfinance",                 # 改用 yfinance 避免 API 限制
}

print("=" * 60)
print("初始化 TradingAgents (使用 DeepSeek API)")
print("=" * 60)
print(f"LLM Provider: {config['llm_provider']}")
print(f"Backend URL: {config['backend_url']}")
print(f"Deep Think Model: {config['deep_think_llm']}")
print(f"Quick Think Model: {config['quick_think_llm']}")
print("=" * 60)

# 只使用市场分析师，跳过新闻分析以避免 API 问题
# selected_analysts = ["market", "social", "fundamentals"]  # 跳过 "news"
selected_analysts = ["market"]  # 先只测试市场分析

print(f"\n选择的分析师: {selected_analysts}")
print("\n开始初始化 TradingAgents Graph...")

# Initialize with custom config
ta = TradingAgentsGraph(
    debug=True, 
    config=config,
    selected_analysts=selected_analysts
)

print("✓ TradingAgents Graph 初始化成功!")
print("\n开始分析 NVDA (英伟达) 在 2024-05-10 的交易决策...")
print("=" * 60)

# forward propagate
try:
    _, decision = ta.propagate("NVDA", "2024-05-10")
    print("\n" + "=" * 60)
    print("✅ 分析完成!")
    print("=" * 60)
    print(f"交易决策: {decision}")
    print("=" * 60)
except Exception as e:
    print(f"\n❌ 分析过程中出现错误: {e}")
    import traceback
    traceback.print_exc()
