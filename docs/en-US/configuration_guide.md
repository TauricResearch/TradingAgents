# TradingAgents Configuration and Prompt Modification Guide

## 📖 Overview

This document provides a comprehensive guide for new users to modify configurations and customize prompts in the TradingAgents project. Through this guide, you will learn:
- How to modify system configuration parameters
- How to configure multi-market support (US stocks and China A-shares)
- How to setup database integration (MongoDB and Redis)
- How to configure multiple LLM providers (DashScope, OpenAI, Google, Anthropic)
- How to customize prompts for various agents
- How to add new features and configurations

## 🌟 New Features Overview

### 🇨🇳 China A-Share Market Support
- **TongDaXin API Integration**: Real-time A-share data access
- **Market Selection**: Interactive CLI market selection
- **Exchange Support**: Shanghai, Shenzhen, ChiNext, STAR Market
- **Intelligent Caching**: Optimized data retrieval and storage

### 🤖 DashScope (Alibaba Cloud) Integration
- **Qwen Model Series**: qwen-turbo, qwen-plus, qwen-max, qwen-max-longcontext
- **Embedding Service**: DashScope embeddings for memory system
- **Intelligent Fallback**: Automatic fallback to OpenAI when unavailable

### 🗄️ Database Integration
- **MongoDB**: Persistent data storage and analytics
- **Redis**: High-performance caching
- **Adaptive Cache**: Intelligent cache management with automatic fallback

## 🔧 Configuration File Locations and Descriptions

### 1. Main Configuration Files

#### 📁 `tradingagents/default_config.py`
**Purpose**: Core configuration file defining all default parameters

```python
DEFAULT_CONFIG = {
    # Directory configuration
    "project_dir": "Project root directory path",
    "results_dir": "Results output directory",
    "data_dir": "Data storage directory", 
    "data_cache_dir": "Cache directory",
    
    # LLM model configuration
    "llm_provider": "dashscope",        # LLM provider: "dashscope", "openai", "google", "anthropic"
    "deep_think_llm": "qwen-plus",      # Deep thinking model
    "quick_think_llm": "qwen-turbo",    # Quick thinking model
    "backend_url": "https://dashscope.aliyuncs.com/api/v1",  # API backend URL
    
    # Debate and discussion settings
    "max_debate_rounds": 1,             # Maximum debate rounds
    "max_risk_discuss_rounds": 1,       # Maximum risk discussion rounds
    "max_recur_limit": 100,             # Maximum recursion limit
    
    # Tool settings
    "online_tools": True,               # Whether to use online tools
}
```

**Modification Method**:
1. Directly edit the `tradingagents/default_config.py` file
2. Modify the corresponding configuration values
3. Restart the application for changes to take effect

#### 📁 `main.py`
**Purpose**: Runtime configuration override, allows temporary parameter adjustments without modifying default config

```python
# Create custom configuration
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"                    # Use Google models
config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
config["deep_think_llm"] = "gemini-2.0-flash"      # Deep thinking model
config["quick_think_llm"] = "gemini-2.0-flash"     # Quick thinking model
config["max_debate_rounds"] = 2                      # Increase debate rounds
config["online_tools"] = True                        # Enable online tools
```

**Modification Method**:
1. Edit the config section in `main.py`
2. Add or modify configuration items to override
3. Save and run

### 2. Dynamic Configuration Management

#### 📁 `tradingagents/dataflows/config.py`
**Purpose**: Provides dynamic configuration get/set functionality

```python
# Get current configuration
config = get_config()

# Dynamically modify configuration
set_config({
    "llm_provider": "anthropic",
    "max_debate_rounds": 3
})
```

## 🌟 New Features Configuration

### 1. Environment Variables Configuration (`.env`)

#### 📁 `.env` File Setup
**Purpose**: Configure API keys and database settings

**Required API Keys**:

**For US Stock Analysis**:
```env
# Choose one LLM provider
OPENAI_API_KEY=your_openai_api_key_here
# OR
GOOGLE_API_KEY=your_google_api_key_here
# OR
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# FinnHub - Required for financial data
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**For China A-Share Analysis**:
```env
# DashScope - Required for Chinese stock analysis
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# FinnHub - Required for financial data
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**For DashScope LLM Provider**:
```env
# DashScope - Required for Qwen models
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# FinnHub - Required for financial data
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**Optional API Keys**:
```env
# OpenAI - Optional fallback
OPENAI_API_KEY=your_openai_api_key_here

# Google AI - For Gemini models
GOOGLE_API_KEY=your_google_api_key_here

# Anthropic - For Claude models
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

**Database Configuration (Optional)**:
```env
# MongoDB - For persistent data storage
MONGODB_ENABLED=false
MONGODB_HOST=localhost
MONGODB_PORT=27018
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your_mongodb_password
MONGODB_DATABASE=tradingagents

# Redis - For high-performance caching
REDIS_ENABLED=false
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_PASSWORD=your_redis_password
REDIS_DB=0
```

### 2. Market Selection Configuration

#### 📁 CLI Market Selection
**Purpose**: Configure supported markets and data sources

**Supported Markets**:
1. **US Stock Market**
   - Format: 1-5 letter symbols (e.g., AAPL, SPY)
   - Data Source: Yahoo Finance
   - Validation: `^[A-Z]{1,5}$`

2. **China A-Share Market**
   - Format: 6-digit codes (e.g., 000001, 600036)
   - Data Source: TongDaXin API
   - Validation: `^\d{6}$`
   - Exchanges: Shanghai (60xxxx), Shenzhen (00xxxx), ChiNext (30xxxx), STAR (68xxxx)

**Configuration in Code**:
```python
# Market-specific configuration
market_config = {
    "us_stock": {
        "data_source": "yahoo_finance",
        "pattern": r'^[A-Z]{1,5}$'
    },
    "china_a_share": {
        "data_source": "tongdaxin",
        "pattern": r'^\d{6}$'
    }
}
```

### 3. Database Integration Configuration

#### 📁 MongoDB Configuration
**Purpose**: Persistent data storage and analytics

**Setup Steps**:
1. **Start MongoDB**:
   ```bash
   docker run -d -p 27017:27017 --name mongodb mongo
   ```

2. **Enable in .env**:
   ```env
   MONGODB_ENABLED=true
   ```

3. **Configuration Options**:
   ```python
   mongodb_config = {
       "host": "localhost",
       "port": 27018,
       "database": "tradingagents",
       "username": "admin",
       "password": "your_password"
   }
   ```

#### 📁 Redis Configuration
**Purpose**: High-performance caching

**Setup Steps**:
1. **Start Redis**:
   ```bash
   docker run -d -p 6379:6379 --name redis redis
   ```

2. **Enable in .env**:
   ```env
   REDIS_ENABLED=true
   ```

3. **Configuration Options**:
   ```python
   redis_config = {
       "host": "localhost",
       "port": 6380,
       "password": "your_password",
       "db": 0
   }
   ```

### 4. LLM Provider Configuration

#### 📁 DashScope (Alibaba Cloud) Configuration
**Purpose**: Chinese-optimized LLM provider

**Supported Models**:
- `qwen-turbo`: Fast response, suitable for quick tasks
- `qwen-plus`: Balanced performance and cost (Recommended)
- `qwen-max`: Best performance for complex analysis
- `qwen-max-longcontext`: Ultra-long context support

**Configuration Example**:
```python
dashscope_config = {
    "llm_provider": "dashscope",
    "deep_think_llm": "qwen-plus",
    "quick_think_llm": "qwen-turbo",
    "backend_url": "https://dashscope.aliyuncs.com/api/v1"
}
```

**API Key Setup**:
1. Visit: https://dashscope.aliyun.com/
2. Register Alibaba Cloud account
3. Enable DashScope service
4. Get API key
5. Set in .env: `DASHSCOPE_API_KEY=your_key`

#### 📁 Multi-LLM Fallback Configuration
**Purpose**: Intelligent fallback between LLM providers

**Fallback Priority**:
1. Primary: DashScope (if configured)
2. Secondary: OpenAI (if configured)
3. Tertiary: Google AI (if configured)
4. Fallback: Anthropic (if configured)

**Configuration**:
```python
fallback_config = {
    "primary_provider": "dashscope",
    "fallback_providers": ["openai", "google", "anthropic"],
    "auto_fallback": True,
    "retry_attempts": 3
}
```

## 🤖 Agent Prompt Modification Guide

### 1. Analyst Prompts

#### 📁 Market Analyst (`tradingagents/agents/analysts/market_analyst.py`)

**Location**: `system_message` variable at lines 24-50

**Current Prompt**:
```python
system_message = (
    """You are a trading assistant tasked with analyzing financial markets. 
    Your role is to select the **most relevant indicators** for a given market 
    condition or trading strategy from the following list..."""
)
```

**Modification Example**:
```python
system_message = (
    """You are a professional market analyst specializing in financial market analysis.
    Your task is to select the most relevant indicators from the following list,
    providing analysis for specific market conditions or trading strategies.
    Goal: Choose up to 8 indicators that provide complementary insights without redundancy..."""
)
```

#### 📁 Fundamentals Analyst (`tradingagents/agents/analysts/fundamentals_analyst.py`)

**Location**: `system_message` variable at lines 23-26

**Key Modification Points**:
- Analysis depth requirements
- Report format requirements
- Focus financial metrics

#### 📁 News Analyst (`tradingagents/agents/analysts/news_analyst.py`)

**Location**: `system_message` variable at lines 20-23

**Key Modification Points**:
- News source preferences
- Analysis time range
- Types of news to focus on

#### 📁 Social Media Analyst (`tradingagents/agents/analysts/social_media_analyst.py`)

**Location**: `system_message` variable at lines 19-22

**Key Modification Points**:
- Sentiment analysis depth
- Social media platform preferences
- Sentiment weight settings

### 2. Researcher Prompts

#### 📁 Bull Researcher (`tradingagents/agents/researchers/bull_researcher.py`)

**Location**: `prompt` variable at lines 25-43

**Current Prompt Structure**:
```python
prompt = f"""You are a Bull Analyst advocating for investing in the stock.

Key points to focus on:
- Growth Potential: Highlight market opportunities, revenue projections, and scalability
- Competitive Advantages: Emphasize unique products, strong branding, or market dominance
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence
- Bear Counterpoints: Critically analyze bear arguments with specific data and sound reasoning
"""
```

**Modification Suggestions**:
- Adjust analysis focus
- Modify argumentation strategy
- Customize rebuttal logic

#### 📁 Bear Researcher (`tradingagents/agents/researchers/bear_researcher.py`)

**Key Modification Points**:
- Risk identification focus
- Pessimistic scenario analysis
- Strategy for countering bull arguments

### 3. Trader Prompts

#### 📁 Trader (`tradingagents/agents/trader/trader.py`)

**Location**: System message in `messages` array at lines 30-36

**Current Prompt**:
```python
{
    "role": "system",
    "content": f"""You are a trading agent analyzing market data to make 
    investment decisions. Based on your analysis, provide a specific 
    recommendation to buy, sell, or hold. End with a firm decision and 
    always conclude your response with 'FINAL TRANSACTION PROPOSAL: 
    **BUY/HOLD/SELL**' to confirm your recommendation.""",
}
```

**Modification Example**:
```python
{
    "role": "system", 
    "content": f"""You are a professional trading agent responsible for analyzing 
    market data and making investment decisions.
    
    Decision Requirements:
    1. Provide detailed analysis reasoning
    2. Consider risk management
    3. Must end with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'
    
    Historical Lessons: {past_memory_str}""",
}
```

### 4. Risk Management Prompts

#### 📁 Conservative Debater (`tradingagents/agents/risk_mgmt/conservative_debator.py`)
#### 📁 Aggressive Debater (`tradingagents/agents/risk_mgmt/aggresive_debator.py`)
#### 📁 Neutral Debater (`tradingagents/agents/risk_mgmt/neutral_debator.py`)

**Key Modification Points**:
- Risk tolerance settings
- Debate style adjustments
- Decision weight allocation

### 5. Reflection System Prompts

#### 📁 Reflection System (`tradingagents/graph/reflection.py`)

**Location**: `_get_reflection_prompt` method at lines 15-47

**Current Prompt Structure**:
```python
return """
You are an expert financial analyst tasked with reviewing trading 
decisions/analysis and providing a comprehensive, step-by-step analysis.

1. Reasoning: Analyze whether each trading decision was correct
2. Improvement: Propose revisions for incorrect decisions  
3. Summary: Summarize lessons learned from successes and failures
4. Query: Extract key insights into concise sentences
"""
```

## 🎯 Prompt Modification Best Practices

### 1. Pre-modification Preparation

1. **Backup Original Files**:
   ```bash
   cp tradingagents/agents/trader/trader.py tradingagents/agents/trader/trader.py.backup
   ```

2. **Understand Agent Roles**: Ensure modifications align with expected agent functionality

3. **Prepare Test Environment**: Validate modifications in test environment

### 2. Prompt Modification Techniques

#### 🔍 **Structured Prompts**
```python
system_message = f"""
Role Definition: You are a {role_name}

Main Tasks:
1. {task_1}
2. {task_2}
3. {task_3}

Analysis Requirements:
- Depth: {analysis_depth}
- Format: {output_format}
- Focus: {focus_areas}

Output Format:
{output_template}

Constraints:
- {constraint_1}
- {constraint_2}
"""
```

#### ⚙️ **Parameterized Prompts**
```python
def create_analyst_prompt(
    role="Market Analyst",
    analysis_depth="Detailed",
    time_horizon="1 week",
    risk_tolerance="Moderate",
    output_language="English"
):
    return f"""
You are a professional {role}, please analyze based on the following parameters:

Analysis Depth: {analysis_depth}
Time Horizon: {time_horizon}  
Risk Preference: {risk_tolerance}
Output Language: {output_language}

Please provide corresponding market analysis and investment recommendations based on these parameters.
"""
```

### 3. Common Modification Scenarios

#### 📈 **Adjusting Analysis Focus**
```python
# Original: General market analysis
system_message = "Analyze overall market trends..."

# Modified: Focus on specific industry
system_message = "Analyze technology stock market trends, focusing on AI, semiconductor, and cloud computing industries..."
```

#### 🎯 **Modifying Decision Style**
```python
# Original: Conservative
"provide conservative investment recommendations..."

# Modified: Aggressive  
"provide aggressive growth-oriented investment recommendations with higher risk tolerance..."
```

## 🔧 New Configuration Items

### 1. Cache Configuration (`tradingagents/dataflows/cache_manager.py`)

```python
# Add new cache configuration in cache_manager.py
self.cache_config = {
    'us_stock_data': {
        'ttl_hours': 2,      # US stock data cached for 2 hours
        'description': 'US stock historical data'
    },
    'china_stock_data': {
        'ttl_hours': 1,      # A-share data cached for 1 hour  
        'description': 'A-share historical data'
    },
    # Add new cache type
    'crypto_data': {
        'ttl_hours': 0.5,    # Crypto data cached for 30 minutes
        'description': 'Cryptocurrency data'
    }
}
```

### 2. API Configuration

```python
# Add new API configuration in default_config.py
DEFAULT_CONFIG = {
    # Existing configuration...
    
    # New API configuration
    "api_keys": {
        "finnhub": "your_finnhub_api_key",
        "alpha_vantage": "your_alpha_vantage_key",
        "polygon": "your_polygon_key"
    },
    
    # API limit configuration
    "api_limits": {
        "finnhub_calls_per_minute": 60,
        "alpha_vantage_calls_per_minute": 5,
        "polygon_calls_per_minute": 100
    }
}
```

## 🚀 Quick Start Examples

### 1. Switch to Google Models

```python
# Edit main.py
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
config["deep_think_llm"] = "gemini-2.0-flash"
config["quick_think_llm"] = "gemini-2.0-flash"
```

#### 🚀 Supported Google Models

**Fast Thinking Models (Quick Analysis)**:
- `gemini-2.0-flash-lite` - Cost efficiency and low latency
- `gemini-2.0-flash` - Next generation features, speed, and thinking ⭐ **Recommended**
- `gemini-2.5-flash-preview-05-20` - Adaptive thinking, cost efficiency

**Deep Thinking Models (Complex Analysis)**:
- `gemini-2.0-flash-lite` - Cost efficiency and low latency
- `gemini-2.0-flash` - Next generation features, speed, and thinking ⭐ **Current Default**
- `gemini-2.5-flash-preview-05-20` - Adaptive thinking, cost efficiency
- `gemini-2.5-pro-preview-06-05` - Professional-grade performance

#### 🔑 Google API Key Setup

**Method 1: Environment Variable (Recommended)**
```bash
export GOOGLE_API_KEY="your_google_api_key_here"
```

**Method 2: In Code**
```python
import os
os.environ["GOOGLE_API_KEY"] = "your_google_api_key_here"
```

**Method 3: .env File**
```
# Create .env file in project root
GOOGLE_API_KEY=your_google_api_key_here
```

#### 📋 Model Selection Examples

**High Performance Setup**:
```python
config["deep_think_llm"] = "gemini-2.5-pro-preview-06-05"  # Best reasoning
config["quick_think_llm"] = "gemini-2.0-flash"  # Fast response
```

**Cost-Optimized Setup**:
```python
config["deep_think_llm"] = "gemini-2.0-flash-lite"  # Economical
config["quick_think_llm"] = "gemini-2.0-flash-lite"  # Economical
```

**Balanced Setup (Current Default)**:
```python
config["deep_think_llm"] = "gemini-2.0-flash"  # Good performance
config["quick_think_llm"] = "gemini-2.0-flash"  # Good speed
```

### 2. Add Risk Control

```python
# Edit tradingagents/agents/trader/trader.py
messages = [
    {
        "role": "system",
        "content": f"""You are a professional trading agent with strict risk control awareness.

        Trading Principles:
        1. Risk first, returns second
        2. Strict stop-loss, protect capital
        3. Diversified investment, reduce risk
        4. Data-driven, rational decisions

        Decision Process:
        1. Analyze market trends and technical indicators
        2. Assess fundamental and news impact
        3. Calculate risk-reward ratio
        4. Set stop-loss and take-profit points
        5. Make final trading decision

        Output Requirements:
        - Must include risk assessment
        - Must set stop-loss points
        - Must end with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'
        
        Historical Experience: {past_memory_str}""",
    },
    context,
]
```

## 📝 Important Notes

1. **Backup Important**: Always backup original files before modification
2. **Test Validation**: Validate modifications in test environment
3. **Version Control**: Use Git to manage configuration changes
4. **Documentation Updates**: Update related documentation promptly
5. **Team Collaboration**: Sync configuration changes with team members

## 🔗 Quick File Index

| Function | File Path | Description |
|----------|-----------|-------------|
| Main Config | `tradingagents/default_config.py` | System default configuration |
| Runtime Config | `main.py` | Runtime configuration override |
| Dynamic Config | `tradingagents/dataflows/config.py` | Configuration management interface |
| Market Analyst | `tradingagents/agents/analysts/market_analyst.py` | Technical analysis prompts |
| Fundamentals Analyst | `tradingagents/agents/analysts/fundamentals_analyst.py` | Fundamental analysis prompts |
| News Analyst | `tradingagents/agents/analysts/news_analyst.py` | News analysis prompts |
| Social Media Analyst | `tradingagents/agents/analysts/social_media_analyst.py` | Sentiment analysis prompts |
| Bull Researcher | `tradingagents/agents/researchers/bull_researcher.py` | Bull analysis prompts |
| Bear Researcher | `tradingagents/agents/researchers/bear_researcher.py` | Bear analysis prompts |
| Trader | `tradingagents/agents/trader/trader.py` | Trading decision prompts |
| Reflection System | `tradingagents/graph/reflection.py` | Reflection analysis prompts |
| Cache Config | `tradingagents/dataflows/cache_manager.py` | Cache management configuration |

Through this guide, you should be able to easily modify the TradingAgents project's configuration and prompts to meet your specific needs.
