from tradingagents.graph.trading_graph import TradingAgentsXGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# 從 .env 檔案載入環境變數（強制覆蓋系統環境變數）
load_dotenv(override=True)

# 建立自訂設定
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5-mini"  # 使用不同的模型
config["quick_think_llm"] = "gpt-5-mini"  # 使用不同的模型
config["max_debate_rounds"] = 1  # 增加辯論回合

# 設定資料供應商 (預設使用 yfinance 和 alpha_vantage)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # 選項: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # 選項: yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",     # 選項: openai, alpha_vantage, local
    "news_data": "alpha_vantage",            # 選項: openai, alpha_vantage, google, local
}

# 使用自訂設定進行初始化
ta = TradingAgentsXGraph(debug=True, config=config)

# 正向傳播
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# 記住錯誤並反思
# ta.reflect_and_remember(1000) # 參數為部位回報