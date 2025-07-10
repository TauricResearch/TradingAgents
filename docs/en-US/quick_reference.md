# TradingAgents Quick Reference Card

## 🚀 Quick Start

### 1. Change LLM Provider
```python
# Edit main.py
config["llm_provider"] = "google"  # or "openai", "anthropic"
config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
config["deep_think_llm"] = "gemini-2.0-flash"
config["quick_think_llm"] = "gemini-2.0-flash"
```

### 2. Modify Debate Rounds
```python
# Edit main.py or default_config.py
config["max_debate_rounds"] = 3  # Increase to 3 rounds
config["max_risk_discuss_rounds"] = 2  # Risk discussion 2 rounds
```

### 3. Enable/Disable Online Tools
```python
config["online_tools"] = True   # Enable online APIs
config["online_tools"] = False  # Use local data
```

## 📁 Key File Locations

| Content to Modify | File Path | Specific Location |
|------------------|-----------|-------------------|
| **System Config** | `tradingagents/default_config.py` | Entire file |
| **Runtime Config** | `main.py` | Lines 15-22 |
| **Market Analyst Prompts** | `tradingagents/agents/analysts/market_analyst.py` | Lines 24-50 |
| **Fundamentals Analyst Prompts** | `tradingagents/agents/analysts/fundamentals_analyst.py` | Lines 23-26 |
| **News Analyst Prompts** | `tradingagents/agents/analysts/news_analyst.py` | Lines 20-23 |
| **Social Media Analyst Prompts** | `tradingagents/agents/analysts/social_media_analyst.py` | Lines 19-22 |
| **Bull Researcher Prompts** | `tradingagents/agents/researchers/bull_researcher.py` | Lines 25-43 |
| **Bear Researcher Prompts** | `tradingagents/agents/researchers/bear_researcher.py` | Lines 25-43 |
| **Trader Prompts** | `tradingagents/agents/trader/trader.py` | Lines 30-36 |
| **Reflection System Prompts** | `tradingagents/graph/reflection.py` | Lines 15-47 |
| **Cache Config** | `tradingagents/dataflows/cache_manager.py` | Lines 20-35 |

## 🎯 Common Modification Templates

### 1. Professional Prompt Template
```python
system_message = f"""
You are a professional {role_name} with the following characteristics:

Expertise Areas:
- {domain_1}
- {domain_2}
- {domain_3}

Analysis Requirements:
1. Provide detailed analysis reasoning
2. Include risk warnings
3. Summarize key indicators in table format

Output Format:
{output_format}

Important Notes:
- Avoid simply saying "trends are mixed"
- Provide specific data support
- Consider market-specific factors
"""
```

### 2. Risk Control Template
```python
system_message = f"""
You are a risk-conscious {role_name}.

Risk Control Principles:
1. Risk first, returns second
2. Strict stop-loss, protect capital
3. Diversified investment, reduce risk
4. Data-driven, rational decisions

Must Include:
- Risk assessment level (Low/Medium/High)
- Recommended stop-loss points
- Maximum position suggestion
- Risk warning description

Decision Format:
Final Recommendation: **BUY/HOLD/SELL**
Risk Level: **Low/Medium/High**
Stop-Loss Point: **Specific price**
Suggested Position: **Percentage**
"""
```

### 3. Technical Analysis Template
```python
system_message = f"""
You are a professional technical analyst focusing on the following indicators:

Core Indicators:
- Moving Averages: SMA, EMA
- Momentum Indicators: RSI, MACD
- Volatility Indicators: Bollinger Bands, ATR
- Volume Indicators: VWMA

Analysis Framework:
1. Trend identification (Up/Down/Sideways)
2. Support and resistance levels
3. Buy/sell signal identification
4. Risk-reward ratio calculation

Output Requirements:
- Clear trend judgment
- Specific entry/exit points
- Technical indicator divergence analysis
- Volume-price relationship analysis
"""
```

## ⚙️ Configuration Parameters Quick Reference

### LLM Configuration
```python
"llm_provider": "openai" | "google" | "anthropic"
"deep_think_llm": "model_name"  # Deep thinking model
"quick_think_llm": "model_name"  # Quick thinking model
"backend_url": "API_address"
```

#### Google Models Quick Reference
```python
# Fast Models: gemini-2.0-flash-lite, gemini-2.0-flash ⭐, gemini-2.5-flash-preview-05-20
# Deep Models: gemini-2.0-flash ⭐, gemini-2.5-flash-preview-05-20, gemini-2.5-pro-preview-06-05

# Google API Setup
export GOOGLE_API_KEY="your_key_here"
```

### Debate Configuration
```python
"max_debate_rounds": 1-5        # Debate rounds
"max_risk_discuss_rounds": 1-3  # Risk discussion rounds
"max_recur_limit": 100          # Recursion limit
```

### Tool Configuration
```python
"online_tools": True | False    # Whether to use online tools
"data_cache_dir": "cache_directory_path"
"results_dir": "results_output_directory"
```

### Cache Configuration
```python
# In cache_manager.py
'us_stock_data': {'ttl_hours': 2}     # US stock cache 2 hours
'china_stock_data': {'ttl_hours': 1}  # A-share cache 1 hour
```

## 🔧 Common Commands

### Test Configuration
```bash
# Run basic tests
cd tests && python test_cache_manager.py

# Run integration tests
cd tests && python test_integration.py

# Run performance tests
cd tests && python test_performance.py
```

### Backup and Restore
```bash
# Backup configuration files
cp tradingagents/default_config.py tradingagents/default_config.py.backup

# Backup prompt files
cp tradingagents/agents/trader/trader.py tradingagents/agents/trader/trader.py.backup

# Restore files
cp tradingagents/default_config.py.backup tradingagents/default_config.py
```

### Git Management
```bash
# Check modification status
git status

# Commit configuration changes
git add tradingagents/default_config.py
git commit -m "feat: Update LLM configuration to Google Gemini"

# Commit prompt changes
git add tradingagents/agents/trader/trader.py
git commit -m "feat: Optimize trader prompts, add risk control"
```

## 🚨 Important Notes

### ⚠️ Must Do Before Modification
1. **Backup Files**: Always backup original files before modification
2. **Test Environment**: Validate modifications in test environment
3. **Version Control**: Use Git to track all changes

### ⚠️ Common Errors
1. **Forgot to Restart**: Need to restart application after config changes
2. **Path Errors**: Ensure file paths are correct
3. **Syntax Errors**: Python syntax must be correct
4. **Encoding Issues**: Use UTF-8 encoding for content

### ⚠️ Performance Considerations
1. **Prompt Length**: Avoid overly long prompts (recommend <4000 tokens)
2. **API Call Frequency**: Be aware of API call limits
3. **Cache Settings**: Set reasonable cache TTL times

## 🆘 Troubleshooting

### Issue: Configuration not taking effect
```python
# Solution: Force reload configuration
from tradingagents.dataflows.config import reload_config
reload_config()
```

### Issue: API call failures
```python
# Solution: Check API keys and network connection
import os
print("OpenAI API Key:", os.getenv("OPENAI_API_KEY", "Not set"))
print("Google API Key:", os.getenv("GOOGLE_API_KEY", "Not set"))
```

### Issue: High memory usage
```python
# Solution: Enable cache cleanup
config["cache_settings"]["cache_size_limit_mb"] = 500  # Limit cache size
config["cache_settings"]["cache_cleanup_interval"] = 1800  # Clean every 30 minutes
```

## 📞 Getting Help

1. **View Detailed Documentation**: `docs/en-US/configuration_guide.md`
2. **Run Tests**: Test files in `tests/` directory
3. **View Examples**: `examples/` directory (if available)
4. **GitHub Issues**: Submit issues in project repository

---

💡 **Tip**: Recommend bookmarking this document for easy reference!
