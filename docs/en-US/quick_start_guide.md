# TradingAgents Quick Start Guide

## 🚀 Overview

This guide will help you get started with TradingAgents quickly, including the new Chinese market features, database integration, and multi-LLM support.

## ⚡ Quick Setup (5 Minutes)

### 1. Prerequisites
```bash
# Python 3.8+ required
python --version

# Clone the repository
git clone https://github.com/your-repo/TradingAgents.git
cd TradingAgents

# Install dependencies
pip install -r requirements.txt
pip install pytdx beautifulsoup4  # For Chinese market support
```

### 2. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your API keys
nano .env  # or use your preferred editor
```

**Minimum Required Configuration**:

**For US Stock Analysis Only**:
```env
# OpenAI or Google AI (Choose one)
OPENAI_API_KEY=your_openai_api_key_here
# OR
GOOGLE_API_KEY=your_google_api_key_here

# FinnHub (Required for financial data)
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**For China A-Share Analysis OR DashScope LLM**:
```env
# DashScope (Required for Chinese stocks or Qwen models)
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# FinnHub (Required for financial data)
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**Note**:
- **DashScope API key is only required when**:
  - Analyzing Chinese A-share stocks (uses TongDaXin data + DashScope embeddings)
  - Choosing DashScope as your LLM provider (Qwen models)
- **For US stocks with OpenAI/Google models**: DashScope is not needed

### 3. First Run
```bash
# Start the application
python -m cli.main

# Follow the interactive prompts:
# 1. Select Market: US Stock or China A-Share
# 2. Enter ticker symbol (e.g., AAPL or 000001)
# 3. Choose analysis date
# 4. Select analysts team
# 5. Choose LLM provider (DashScope recommended)
# 6. Run analysis
```

## 🌟 Feature Overview

### 🇺🇸 US Stock Analysis
- **Supported Symbols**: AAPL, SPY, TSLA, NVDA, MSFT, etc.
- **Data Source**: Yahoo Finance
- **Format**: 1-5 letter symbols
- **Example**: `AAPL` (Apple Inc.)

### 🇨🇳 China A-Share Analysis
- **Supported Exchanges**: 
  - Shanghai (60xxxx): `600036` (China Merchants Bank)
  - Shenzhen (00xxxx): `000001` (Ping An Bank)
  - ChiNext (30xxxx): `300001` (Technology stocks)
  - STAR Market (68xxxx): `688001` (Innovation companies)
- **Data Source**: TongDaXin API
- **Format**: 6-digit numeric codes

### 🤖 Multi-LLM Support
- **DashScope (Alibaba Cloud)**: Qwen models, Chinese-optimized
- **OpenAI**: GPT-4o, GPT-4o-mini, o1, o3 series
- **Google AI**: Gemini 2.0/2.5 Flash series
- **Anthropic**: Claude 3.5/4 series

## 📋 Step-by-Step Walkthrough

### Step 1: Market Selection
```
? Select Stock Market:
  US Stock - Examples: SPY, AAPL, TSLA
❯ China A-Share - Examples: 000001, 600036, 000858
```

### Step 2: Ticker Input
```
Format requirement: 6-digit code (e.g., 600036, 000001)
Examples: 000001, 600036, 300001, 688001
? Enter China A-Share ticker symbol: 000001
✅ Valid A-share code: 000001 (will use TongDaXin data source)
```

### Step 3: Analysis Configuration
```
? Select your research depth:
❯ Light (1 round) - Quick analysis
  Medium (2 rounds) - Balanced analysis  
  Deep (3 rounds) - Comprehensive analysis

? Select your LLM Provider:
❯ DashScope (Alibaba Cloud)
  OpenAI
  Google AI
  Anthropic
```

### Step 4: Model Selection
```
? Select Your [Quick-Thinking LLM Engine]:
❯ Qwen-Turbo - Fast response, suitable for quick tasks
  Qwen-Plus - Balanced performance and cost
  Qwen-Max - Best performance for complex analysis

? Select Your [Deep-Thinking LLM Engine]:
❯ Qwen-Plus - Balanced performance and cost (Recommended)
  Qwen-Max - Best performance for complex analysis
  Qwen-Max-LongContext - Ultra-long context support
```

## 🗄️ Database Setup (Optional)

### Enable High-Performance Caching

**1. Start Database Services**:
```bash
# MongoDB for persistent storage
docker run -d -p 27017:27017 --name mongodb mongo

# Redis for high-performance caching
docker run -d -p 6379:6379 --name redis redis
```

**2. Enable in .env**:
```env
# Enable database caching
MONGODB_ENABLED=true
REDIS_ENABLED=true

# MongoDB configuration
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=tradingagents

# Redis configuration  
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

**3. Restart Application**:
```bash
python -m cli.main
# System will now use database caching for improved performance
```

## 🔧 Configuration Examples

### Example 1: US Stock Analysis with OpenAI
```env
# Only need OpenAI and FinnHub for US stocks
OPENAI_API_KEY=your_openai_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI Selections**:
- Market: US Stock
- Ticker: AAPL
- LLM Provider: OpenAI
- Models: GPT-4o-mini (quick), o1 (deep)

**Note**: DashScope not required for US stock analysis with OpenAI

### Example 2: US Stock Analysis with Google AI
```env
# Only need Google AI and FinnHub for US stocks
GOOGLE_API_KEY=your_google_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI Selections**:
- Market: US Stock
- Ticker: TSLA
- LLM Provider: Google AI
- Models: Gemini 2.0 Flash (quick), Gemini 2.5 Flash (deep)

**Note**: DashScope not required for US stock analysis with Google AI

### Example 3: China A-Share Analysis (DashScope Required)
```env
# DashScope required for Chinese stock analysis
DASHSCOPE_API_KEY=your_dashscope_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI Selections**:
- Market: China A-Share
- Ticker: 000001
- LLM Provider: DashScope
- Models: qwen-turbo (quick), qwen-plus (deep)

**Note**: DashScope API key is required for Chinese stock analysis (TongDaXin data + embeddings)

### Example 4: US Stocks with DashScope LLM (DashScope Required)
```env
# DashScope required when using Qwen models
DASHSCOPE_API_KEY=your_dashscope_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI Selections**:
- Market: US Stock
- Ticker: SPY
- LLM Provider: DashScope (Alibaba Cloud)
- Models: qwen-turbo (quick), qwen-plus (deep)

**Note**: DashScope API key is required when choosing DashScope as LLM provider

### Example 5: Full Features with Database
```env
# Choose based on your use case
OPENAI_API_KEY=your_openai_key          # For US stocks with OpenAI
# OR
DASHSCOPE_API_KEY=your_dashscope_key    # For Chinese stocks or DashScope LLM

FINNHUB_API_KEY=your_finnhub_key
MONGODB_ENABLED=true
REDIS_ENABLED=true
```

**Benefits**:
- Faster data retrieval
- Persistent analysis history
- Advanced caching strategies
- Usage analytics

## 🛠️ Troubleshooting

### Common Issues

**1. API Key Errors**:
```
Error: Invalid API key
Solution: Check .env file and ensure correct API key format
```

**2. TongDaXin Connection Issues**:
```
Error: TongDaXin API unavailable
Solution: System automatically falls back to cached data
```

**3. Database Connection Issues**:
```
Error: MongoDB/Redis connection failed
Solution: System falls back to file cache automatically
```

**4. Invalid Ticker Format**:
```
Error: Invalid ticker format
Solution: 
- US stocks: Use 1-5 letter symbols (AAPL)
- A-shares: Use 6-digit codes (000001)
```

### Debug Mode
```bash
# Enable debug logging
export TRADINGAGENTS_LOG_LEVEL=DEBUG
python -m cli.main
```

## 📊 Sample Analysis Output

### US Stock Analysis (AAPL)
```
📈 Analysis Results for AAPL (Apple Inc.)
Market: US Stock Exchange
Data Source: Yahoo Finance

🔍 Technical Analysis:
- Current Price: $150.25 (+2.3%)
- RSI: 65.2 (Neutral to Bullish)
- Moving Averages: Above 20-day and 50-day MA

💰 Fundamental Analysis:
- P/E Ratio: 28.5
- Revenue Growth: 8.2% YoY
- Market Cap: $2.4T

📰 News Sentiment: Positive (0.72/1.0)
🎯 Recommendation: BUY with target $165
```

### China A-Share Analysis (000001)
```
📈 Analysis Results for 000001 (平安银行)
Market: Shenzhen Stock Exchange
Data Source: TongDaXin API

🔍 Technical Analysis:
- Current Price: ¥12.85 (+1.8%)
- RSI: 58.3 (Neutral)
- Volume: Above average

💰 Fundamental Analysis:
- P/E Ratio: 5.2
- ROE: 12.8%
- Book Value: ¥15.20

📰 News Sentiment: Neutral (0.55/1.0)
🎯 Recommendation: HOLD with target ¥14.50
```

## 🎯 Next Steps

### Explore Advanced Features
1. **Custom Prompts**: Modify agent prompts for specific strategies
2. **Database Analytics**: Analyze historical performance
3. **Multi-Market Comparison**: Compare US and Chinese stocks
4. **Risk Management**: Configure risk parameters

### Learn More
- [Configuration Guide](configuration_guide.md) - Detailed configuration options
- [Architecture Guide](architecture_guide.md) - System architecture overview
- [API Documentation](api_documentation.md) - API reference

### Get Support
- GitHub Issues: Report bugs and feature requests
- Documentation: Comprehensive guides and examples
- Community: Join discussions and share strategies

---

🎉 **Congratulations!** You're now ready to analyze both US and Chinese markets with TradingAgents. The system provides intelligent fallbacks, multi-LLM support, and enterprise-grade caching for optimal performance.
