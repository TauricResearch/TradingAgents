# TradingAgents 配置与提示词修改指南

## 📖 概述

本文档为TradingAgents项目的新手用户提供详细的配置修改和提示词定制指南。通过本指南，您将了解：
- 如何修改系统配置参数
- 如何配置多市场支持（美股和A股）
- 如何设置数据库集成（MongoDB和Redis）
- 如何配置多LLM提供商（百炼、OpenAI、Google、Anthropic）
- 如何定制各个智能体的提示词
- 如何添加新的功能和配置

## 🌟 新功能概览

### 🇨🇳 中国A股市场支持
- **通达信API集成**: 实时A股数据获取
- **市场选择**: 交互式CLI市场选择
- **交易所支持**: 上交所、深交所、创业板、科创板
- **智能缓存**: 优化的数据获取和存储

### 🤖 百炼(DashScope)集成
- **通义千问模型系列**: qwen-turbo, qwen-plus, qwen-max, qwen-max-longcontext
- **Embedding服务**: 百炼embedding用于记忆系统
- **智能回退**: 百炼不可用时自动回退到OpenAI

### 🗄️ 数据库集成
- **MongoDB**: 持久化数据存储和分析
- **Redis**: 高性能缓存
- **自适应缓存**: 智能缓存管理和自动回退

## 🔧 配置文件位置与说明

### 1. 主配置文件

#### 📁 `tradingagents/default_config.py`
**作用**: 项目的核心配置文件，定义所有默认参数

```python
DEFAULT_CONFIG = {
    # 目录配置
    "project_dir": "项目根目录路径",
    "results_dir": "结果输出目录",
    "data_dir": "数据存储目录", 
    "data_cache_dir": "缓存目录",
    
    # LLM模型配置
    "llm_provider": "dashscope",        # LLM提供商: "dashscope", "openai", "google", "anthropic"
    "deep_think_llm": "qwen-plus",      # 深度思考模型
    "quick_think_llm": "qwen-turbo",    # 快速思考模型
    "backend_url": "https://dashscope.aliyuncs.com/api/v1",  # API后端地址
    
    # 辩论与讨论设置
    "max_debate_rounds": 1,             # 最大辩论轮数
    "max_risk_discuss_rounds": 1,       # 最大风险讨论轮数
    "max_recur_limit": 100,             # 最大递归限制
    
    # 工具设置
    "online_tools": True,               # 是否使用在线工具
}
```

**修改方法**:
1. 直接编辑 `tradingagents/default_config.py` 文件
2. 修改对应的配置值
3. 重启应用生效

#### 📁 `main.py`
**作用**: 运行时配置覆盖，可以在不修改默认配置的情况下临时调整参数

```python
# 创建自定义配置
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"                    # 使用Google模型
config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
config["deep_think_llm"] = "gemini-2.0-flash"      # 深度思考模型
config["quick_think_llm"] = "gemini-2.0-flash"     # 快速思考模型
config["max_debate_rounds"] = 2                      # 增加辩论轮数
config["online_tools"] = True                        # 启用在线工具
```

**修改方法**:
1. 编辑 `main.py` 文件中的config部分
2. 添加或修改需要覆盖的配置项
3. 保存并运行

### 2. 动态配置管理

#### 📁 `tradingagents/dataflows/config.py`
**作用**: 提供配置的动态获取和设置功能

```python
# 获取当前配置
config = get_config()

# 动态修改配置
set_config({
    "llm_provider": "anthropic",
    "max_debate_rounds": 3
})
```

## 🌟 新功能配置详解

### 1. 环境变量配置 (`.env`)

#### 📁 `.env` 文件设置
**作用**: 配置API密钥和数据库设置

**必需的API密钥**:

**仅分析美股时**:
```env
# 选择一个LLM提供商
OPENAI_API_KEY=your_openai_api_key_here
# 或者
GOOGLE_API_KEY=your_google_api_key_here
# 或者
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# FinnHub - 金融数据必需
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**分析中国A股时**:
```env
# 百炼 - 中国股票分析必需
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# FinnHub - 金融数据必需
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**使用百炼LLM提供商时**:
```env
# 百炼 - 通义千问模型必需
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# FinnHub - 金融数据必需
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**数据库配置（可选）**:
```env
# MongoDB - 持久化数据存储
MONGODB_ENABLED=false
MONGODB_HOST=localhost
MONGODB_PORT=27018
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your_mongodb_password
MONGODB_DATABASE=tradingagents

# Redis - 高性能缓存
REDIS_ENABLED=false
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_PASSWORD=your_redis_password
REDIS_DB=0
```

### 2. 市场选择配置

#### 📁 CLI市场选择
**作用**: 配置支持的市场和数据源

**支持的市场**:
1. **美股市场**
   - 格式: 1-5位字母代码 (如 AAPL, SPY)
   - 数据源: Yahoo Finance
   - 验证: `^[A-Z]{1,5}$`

2. **中国A股市场**
   - 格式: 6位数字代码 (如 000001, 600036)
   - 数据源: 通达信API
   - 验证: `^\d{6}$`
   - 交易所: 上交所(60xxxx), 深交所(00xxxx), 创业板(30xxxx), 科创板(68xxxx)

**代码中的配置**:
```python
# 市场特定配置
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

### 3. 数据库集成配置

#### 📁 MongoDB配置
**作用**: 持久化数据存储和分析

**设置步骤**:
1. **启动MongoDB**:
   ```bash
   docker run -d -p 27017:27017 --name mongodb mongo
   ```

2. **在.env中启用**:
   ```env
   MONGODB_ENABLED=true
   ```

3. **配置选项**:
   ```python
   mongodb_config = {
       "host": "localhost",
       "port": 27018,
       "database": "tradingagents",
       "username": "admin",
       "password": "your_password"
   }
   ```

#### 📁 Redis配置
**作用**: 高性能缓存

**设置步骤**:
1. **启动Redis**:
   ```bash
   docker run -d -p 6379:6379 --name redis redis
   ```

2. **在.env中启用**:
   ```env
   REDIS_ENABLED=true
   ```

3. **配置选项**:
   ```python
   redis_config = {
       "host": "localhost",
       "port": 6380,
       "password": "your_password",
       "db": 0
   }
   ```

### 4. LLM提供商配置

#### 📁 百炼(DashScope)配置
**作用**: 中文优化的LLM提供商

**支持的模型**:
- `qwen-turbo`: 快速响应，适合快速任务
- `qwen-plus`: 平衡性能和成本（推荐）
- `qwen-max`: 复杂分析的最佳性能
- `qwen-max-longcontext`: 超长上下文支持

**配置示例**:
```python
dashscope_config = {
    "llm_provider": "dashscope",
    "deep_think_llm": "qwen-plus",
    "quick_think_llm": "qwen-turbo",
    "backend_url": "https://dashscope.aliyuncs.com/api/v1"
}
```

**API密钥设置**:
1. 访问: https://dashscope.aliyun.com/
2. 注册阿里云账号
3. 开通百炼服务
4. 获取API密钥
5. 在.env中设置: `DASHSCOPE_API_KEY=your_key`

#### 📁 多LLM回退配置
**作用**: LLM提供商之间的智能回退

**回退优先级**:
1. 主要: 百炼（如果配置）
2. 次要: OpenAI（如果配置）
3. 第三: Google AI（如果配置）
4. 回退: Anthropic（如果配置）

**配置**:
```python
fallback_config = {
    "primary_provider": "dashscope",
    "fallback_providers": ["openai", "google", "anthropic"],
    "auto_fallback": True,
    "retry_attempts": 3
}
```

## 🤖 智能体提示词修改指南

### 1. 分析师提示词

#### 📁 市场分析师 (`tradingagents/agents/analysts/market_analyst.py`)

**位置**: 第24-50行的 `system_message` 变量

**当前提示词**:
```python
system_message = (
    """You are a trading assistant tasked with analyzing financial markets. 
    Your role is to select the **most relevant indicators** for a given market 
    condition or trading strategy from the following list..."""
)
```

**修改示例**:
```python
system_message = (
    """您是一位专业的市场分析师，专门分析金融市场。您的任务是从以下指标列表中
    选择最相关的指标，为特定的市场条件或交易策略提供分析。目标是选择最多8个
    提供互补信息且无冗余的指标..."""
)
```

#### 📁 基本面分析师 (`tradingagents/agents/analysts/fundamentals_analyst.py`)

**位置**: 第23-26行的 `system_message` 变量

**修改要点**:
- 分析深度要求
- 报告格式要求
- 关注的财务指标

#### 📁 新闻分析师 (`tradingagents/agents/analysts/news_analyst.py`)

**位置**: 第20-23行的 `system_message` 变量

**修改要点**:
- 新闻来源偏好
- 分析时间范围
- 关注的新闻类型

#### 📁 社交媒体分析师 (`tradingagents/agents/analysts/social_media_analyst.py`)

**位置**: 第19-22行的 `system_message` 变量

**修改要点**:
- 情感分析深度
- 社交媒体平台偏好
- 情感权重设置

### 2. 研究员提示词

#### 📁 多头研究员 (`tradingagents/agents/researchers/bull_researcher.py`)

**位置**: 第25-43行的 `prompt` 变量

**当前提示词结构**:
```python
prompt = f"""You are a Bull Analyst advocating for investing in the stock.

Key points to focus on:
- Growth Potential: 突出公司的市场机会、收入预测和可扩展性
- Competitive Advantages: 强调独特产品、强势品牌或主导市场地位
- Positive Indicators: 使用财务健康、行业趋势和最新正面新闻作为证据
- Bear Counterpoints: 用具体数据和合理推理批判性分析空头论点
"""
```

**修改建议**:
- 调整分析重点
- 修改论证策略
- 自定义反驳逻辑

#### 📁 空头研究员 (`tradingagents/agents/researchers/bear_researcher.py`)

**修改要点**:
- 风险识别重点
- 悲观情景分析
- 反驳多头论点的策略

### 3. 交易员提示词

#### 📁 交易员 (`tradingagents/agents/trader/trader.py`)

**位置**: 第30-36行的 `messages` 数组中的system消息

**当前提示词**:
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

**修改示例**:
```python
{
    "role": "system", 
    "content": f"""您是一位专业的交易智能体，负责分析市场数据并做出投资决策。
    基于您的分析，请提供具体的买入、卖出或持有建议。
    
    决策要求：
    1. 提供详细的分析理由
    2. 考虑风险管理
    3. 必须以'最终交易建议: **买入/持有/卖出**'结束
    
    过往经验教训：{past_memory_str}""",
}
```

### 4. 风险管理提示词

#### 📁 保守派辩论者 (`tradingagents/agents/risk_mgmt/conservative_debator.py`)
#### 📁 激进派辩论者 (`tradingagents/agents/risk_mgmt/aggresive_debator.py`)
#### 📁 中性派辩论者 (`tradingagents/agents/risk_mgmt/neutral_debator.py`)

**修改要点**:
- 风险容忍度设置
- 辩论风格调整
- 决策权重分配

### 5. 反思系统提示词

#### 📁 反思系统 (`tradingagents/graph/reflection.py`)

**位置**: 第15-47行的 `_get_reflection_prompt` 方法

**当前提示词结构**:
```python
return """
You are an expert financial analyst tasked with reviewing trading 
decisions/analysis and providing a comprehensive, step-by-step analysis.

1. Reasoning: 分析每个交易决策是否正确
2. Improvement: 对错误决策提出修正建议  
3. Summary: 总结成功和失败的经验教训
4. Query: 将关键洞察提取为简洁的句子
"""
```

## 🎯 提示词修改最佳实践

### 1. 修改前的准备工作

1. **备份原文件**:
   ```bash
   cp tradingagents/agents/trader/trader.py tradingagents/agents/trader/trader.py.backup
   ```

2. **了解智能体角色**: 确保修改符合智能体的预期功能

3. **测试环境准备**: 在测试环境中验证修改效果

### 2. 提示词修改技巧

#### 🔍 **结构化提示词**
```python
system_message = f"""
角色定义：您是一位{role_name}

主要任务：
1. {task_1}
2. {task_2}
3. {task_3}

分析要求：
- 深度：{analysis_depth}
- 格式：{output_format}
- 重点：{focus_areas}

输出格式：
{output_template}

注意事项：
- {constraint_1}
- {constraint_2}
"""
```

#### 🌐 **多语言支持**
```python
# 中文提示词示例
system_message_cn = """
您是一位专业的股票分析师，具有以下特点：

专业领域：
- 技术分析：均线、MACD、RSI等指标分析
- 基本面分析：财务报表、行业趋势、公司治理
- 市场情绪：新闻分析、社交媒体情绪、投资者行为

分析框架：
1. 数据收集：获取相关市场数据
2. 指标计算：计算技术和基本面指标
3. 趋势识别：识别短期和长期趋势
4. 风险评估：评估潜在风险和机会
5. 投资建议：提供明确的买入/持有/卖出建议

输出要求：
- 使用中文进行分析
- 提供详细的分析理由
- 包含风险提示
- 以表格形式总结关键指标
"""
```

#### ⚙️ **参数化提示词**
```python
def create_analyst_prompt(
    role="市场分析师",
    analysis_depth="详细",
    time_horizon="1周",
    risk_tolerance="中等",
    output_language="中文"
):
    return f"""
您是一位专业的{role}，请根据以下参数进行分析：

分析深度：{analysis_depth}
时间范围：{time_horizon}  
风险偏好：{risk_tolerance}
输出语言：{output_language}

请基于这些参数提供相应的市场分析和投资建议。
"""
```

### 3. 常见修改场景

#### 📈 **调整分析重点**
```python
# 原始：通用市场分析
system_message = "分析整体市场趋势..."

# 修改：专注特定行业
system_message = "专门分析科技股市场趋势，重点关注AI、半导体、云计算行业..."
```

#### 🎯 **修改决策风格**
```python
# 原始：保守型
"provide conservative investment recommendations..."

# 修改：激进型  
"provide aggressive growth-oriented investment recommendations with higher risk tolerance..."
```

#### 🌍 **本地化适配**
```python
# 原始：美股市场
"analyze US stock market trends..."

# 修改：A股市场
"分析中国A股市场趋势，考虑中国特色的市场因素，如政策影响、国企改革、科创板等..."
```

## 🔧 新增配置项

### 1. 缓存配置 (`tradingagents/dataflows/cache_manager.py`)

```python
# 在cache_manager.py中添加新的缓存配置
self.cache_config = {
    'us_stock_data': {
        'ttl_hours': 2,      # 美股数据缓存2小时
        'description': '美股历史数据'
    },
    'china_stock_data': {
        'ttl_hours': 1,      # A股数据缓存1小时  
        'description': 'A股历史数据'
    },
    # 添加新的缓存类型
    'crypto_data': {
        'ttl_hours': 0.5,    # 加密货币数据缓存30分钟
        'description': '加密货币数据'
    }
}
```

### 2. API配置

```python
# 在default_config.py中添加新的API配置
DEFAULT_CONFIG = {
    # 现有配置...
    
    # 新增API配置
    "api_keys": {
        "finnhub": "your_finnhub_api_key",
        "alpha_vantage": "your_alpha_vantage_key",
        "polygon": "your_polygon_key"
    },
    
    # API限制配置
    "api_limits": {
        "finnhub_calls_per_minute": 60,
        "alpha_vantage_calls_per_minute": 5,
        "polygon_calls_per_minute": 100
    }
}
```

## 🚀 快速开始示例

### 1. 切换到Google模型

```python
# 编辑 main.py
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
config["deep_think_llm"] = "gemini-2.0-flash"
config["quick_think_llm"] = "gemini-2.0-flash"
```

#### 🚀 支持的Google模型

**快速思考模型（快速分析）**：
- `gemini-2.0-flash-lite` - 成本效率和低延迟
- `gemini-2.0-flash` - 下一代功能、速度和思考能力 ⭐ **推荐**
- `gemini-2.5-flash-preview-05-20` - 自适应思考、成本效率

**深度思考模型（复杂分析）**：
- `gemini-2.0-flash-lite` - 成本效率和低延迟
- `gemini-2.0-flash` - 下一代功能、速度和思考能力 ⭐ **当前默认**
- `gemini-2.5-flash-preview-05-20` - 自适应思考、成本效率
- `gemini-2.5-pro-preview-06-05` - 专业级性能

#### 🔑 Google API密钥设置

**方法1: 环境变量（推荐）**
```bash
export GOOGLE_API_KEY="your_google_api_key_here"
```

**方法2: 代码中设置**
```python
import os
os.environ["GOOGLE_API_KEY"] = "your_google_api_key_here"
```

**方法3: .env文件**
```
# 在项目根目录创建.env文件
GOOGLE_API_KEY=your_google_api_key_here
```

#### 📋 模型选择示例

**高性能配置**：
```python
config["deep_think_llm"] = "gemini-2.5-pro-preview-06-05"  # 最佳推理能力
config["quick_think_llm"] = "gemini-2.0-flash"  # 快速响应
```

**成本优化配置**：
```python
config["deep_think_llm"] = "gemini-2.0-flash-lite"  # 经济实惠
config["quick_think_llm"] = "gemini-2.0-flash-lite"  # 经济实惠
```

**平衡配置（当前默认）**：
```python
config["deep_think_llm"] = "gemini-2.0-flash"  # 良好性能
config["quick_think_llm"] = "gemini-2.0-flash"  # 良好速度
```

### 2. 修改为中文分析师

```python
# 编辑 tradingagents/agents/analysts/market_analyst.py
system_message = (
    """您是一位专业的中文市场分析师，专门分析中国A股和美股市场。

    您的主要任务：
    1. 选择最相关的技术指标（最多8个）
    2. 提供详细的中文市场分析
    3. 考虑中国特色的市场因素

    技术指标类别：

    移动平均线：
    - close_50_sma: 50日简单移动平均线，中期趋势指标
    - close_200_sma: 200日简单移动平均线，长期趋势基准
    - close_10_ema: 10日指数移动平均线，短期趋势响应

    请用中文提供详细且细致的趋势分析，避免简单地说"趋势混合"。
    在报告末尾添加Markdown表格来组织关键要点。"""
)
```

### 2. 添加风险控制

```python
# 编辑 tradingagents/agents/trader/trader.py
messages = [
    {
        "role": "system",
        "content": f"""您是一位专业的交易智能体，具有严格的风险控制意识。

        交易原则：
        1. 风险第一，收益第二
        2. 严格止损，保护本金
        3. 分散投资，降低风险
        4. 基于数据，理性决策

        决策流程：
        1. 分析市场趋势和技术指标
        2. 评估基本面和新闻影响
        3. 计算风险收益比
        4. 设定止损和止盈点
        5. 做出最终交易决策

        输出要求：
        - 必须包含风险评估
        - 必须设定止损点
        - 必须以'最终交易建议: **买入/持有/卖出**'结束
        
        历史经验：{past_memory_str}""",
    },
    context,
]
```

## 📝 注意事项

1. **备份重要**: 修改前务必备份原文件
2. **测试验证**: 在测试环境中验证修改效果
3. **版本控制**: 使用Git管理配置变更
4. **文档更新**: 及时更新相关文档
5. **团队协作**: 与团队成员同步配置变更

## 🔗 相关文件快速索引

| 功能 | 文件路径 | 说明 |
|------|----------|------|
| 主配置 | `tradingagents/default_config.py` | 系统默认配置 |
| 运行配置 | `main.py` | 运行时配置覆盖 |
| 动态配置 | `tradingagents/dataflows/config.py` | 配置管理接口 |
| 市场分析师 | `tradingagents/agents/analysts/market_analyst.py` | 技术分析提示词 |
| 基本面分析师 | `tradingagents/agents/analysts/fundamentals_analyst.py` | 基本面分析提示词 |
| 新闻分析师 | `tradingagents/agents/analysts/news_analyst.py` | 新闻分析提示词 |
| 社媒分析师 | `tradingagents/agents/analysts/social_media_analyst.py` | 情感分析提示词 |
| 多头研究员 | `tradingagents/agents/researchers/bull_researcher.py` | 多头分析提示词 |
| 空头研究员 | `tradingagents/agents/researchers/bear_researcher.py` | 空头分析提示词 |
| 交易员 | `tradingagents/agents/trader/trader.py` | 交易决策提示词 |
| 反思系统 | `tradingagents/graph/reflection.py` | 反思分析提示词 |
| 缓存配置 | `tradingagents/dataflows/cache_manager.py` | 缓存管理配置 |

## 🛠️ 高级配置技巧

### 1. 环境变量配置

您可以通过环境变量来覆盖某些配置，而无需修改代码：

```bash
# 设置结果目录
export TRADINGAGENTS_RESULTS_DIR="/path/to/custom/results"

# 设置API密钥
export OPENAI_API_KEY="your_openai_api_key"
export GOOGLE_API_KEY="your_google_api_key"
export FINNHUB_API_KEY="your_finnhub_api_key"
```

### 2. 配置文件模板

创建 `config_template.py` 用于不同环境的配置：

```python
# config_template.py
DEVELOPMENT_CONFIG = {
    "llm_provider": "openai",
    "max_debate_rounds": 1,
    "online_tools": False,  # 开发环境使用离线工具
    "debug": True
}

PRODUCTION_CONFIG = {
    "llm_provider": "google",
    "max_debate_rounds": 3,
    "online_tools": True,
    "debug": False
}

TESTING_CONFIG = {
    "llm_provider": "mock",  # 使用模拟LLM进行测试
    "max_debate_rounds": 1,
    "online_tools": False,
    "debug": True
}
```

### 3. 动态提示词加载

创建外部提示词文件，便于管理：

```python
# prompts/market_analyst_prompts.py
MARKET_ANALYST_PROMPTS = {
    "chinese": """您是一位专业的中文市场分析师...""",
    "english": """You are a professional market analyst...""",
    "conservative": """您是一位保守型市场分析师...""",
    "aggressive": """您是一位激进型市场分析师..."""
}

# 在market_analyst.py中使用
from prompts.market_analyst_prompts import MARKET_ANALYST_PROMPTS

def create_market_analyst(llm, toolkit, style="chinese"):
    system_message = MARKET_ANALYST_PROMPTS.get(style, MARKET_ANALYST_PROMPTS["english"])
    # ... 其余代码
```

## 🔍 调试与测试

### 1. 提示词测试

创建测试脚本验证提示词效果：

```python
# tests/test_prompts.py
def test_market_analyst_prompt():
    """测试市场分析师提示词"""
    from tradingagents.agents.analysts.market_analyst import create_market_analyst

    # 创建模拟状态
    test_state = {
        "trade_date": "2024-01-15",
        "company_of_interest": "AAPL",
        "messages": []
    }

    # 测试分析师响应
    analyst = create_market_analyst(mock_llm, mock_toolkit)
    result = analyst(test_state)

    # 验证输出格式
    assert "market_report" in result
    assert len(result["market_report"]) > 100
```

### 2. 配置验证

```python
# utils/config_validator.py
def validate_config(config):
    """验证配置的有效性"""
    required_keys = [
        "llm_provider", "deep_think_llm", "quick_think_llm",
        "backend_url", "max_debate_rounds"
    ]

    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")

    if config["max_debate_rounds"] < 1:
        raise ValueError("max_debate_rounds must be at least 1")

    valid_providers = ["openai", "google", "anthropic"]
    if config["llm_provider"] not in valid_providers:
        raise ValueError(f"Invalid llm_provider: {config['llm_provider']}")

    return True
```

## 📊 性能优化配置

### 1. 缓存优化

```python
# 在default_config.py中添加缓存优化配置
DEFAULT_CONFIG = {
    # ... 现有配置

    # 缓存优化配置
    "cache_settings": {
        "enable_cache": True,
        "cache_size_limit_mb": 1000,  # 缓存大小限制
        "cache_cleanup_interval": 3600,  # 清理间隔（秒）
        "cache_compression": True,  # 启用压缩
    },

    # 并发配置
    "concurrency": {
        "max_workers": 4,  # 最大工作线程数
        "api_rate_limit": 60,  # API调用频率限制（每分钟）
        "batch_size": 10,  # 批处理大小
    }
}
```

### 2. 内存管理

```python
# 在config.py中添加内存管理
def optimize_memory_usage():
    """优化内存使用"""
    import gc
    import psutil

    # 获取当前内存使用
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024

    # 如果内存使用超过阈值，触发垃圾回收
    if memory_mb > 500:  # 500MB阈值
        gc.collect()
        print(f"内存优化：从 {memory_mb:.1f}MB 优化到 {process.memory_info().rss / 1024 / 1024:.1f}MB")
```

## 🌐 国际化支持

### 1. 多语言提示词管理

```python
# i18n/prompts.py
PROMPTS = {
    "zh-CN": {
        "market_analyst": "您是一位专业的市场分析师...",
        "trader": "您是一位专业的交易员...",
        "bull_researcher": "您是一位看多的研究员..."
    },
    "en-US": {
        "market_analyst": "You are a professional market analyst...",
        "trader": "You are a professional trader...",
        "bull_researcher": "You are a bull researcher..."
    },
    "ja-JP": {
        "market_analyst": "あなたはプロの市場アナリストです...",
        "trader": "あなたはプロのトレーダーです...",
        "bull_researcher": "あなたは強気の研究者です..."
    }
}

def get_prompt(role, language="zh-CN"):
    """获取指定语言的提示词"""
    return PROMPTS.get(language, PROMPTS["en-US"]).get(role, "")
```

### 2. 区域化配置

```python
# 针对不同市场的配置
MARKET_CONFIGS = {
    "US": {
        "trading_hours": "09:30-16:00 EST",
        "currency": "USD",
        "major_indices": ["SPY", "QQQ", "DIA"],
        "data_sources": ["yahoo", "finnhub", "alpha_vantage"]
    },
    "CN": {
        "trading_hours": "09:30-15:00 CST",
        "currency": "CNY",
        "major_indices": ["000001", "399001", "399006"],
        "data_sources": ["tushare", "akshare", "eastmoney"]
    },
    "JP": {
        "trading_hours": "09:00-15:00 JST",
        "currency": "JPY",
        "major_indices": ["N225", "TOPX"],
        "data_sources": ["yahoo_jp", "sbi"]
    }
}
```

## 🚨 常见问题与解决方案

### 1. 配置问题

**问题**: 修改配置后不生效
**解决**:
```python
# 确保重新加载配置
from tradingagents.dataflows.config import reload_config
reload_config()
```

**问题**: API密钥配置错误
**解决**:
```python
# 验证API密钥
def validate_api_keys():
    config = get_config()
    if not config.get("openai_api_key"):
        raise ValueError("OpenAI API key not configured")

    # 测试API连接
    try:
        client = OpenAI(api_key=config["openai_api_key"])
        client.models.list()
        print("✅ OpenAI API连接成功")
    except Exception as e:
        print(f"❌ OpenAI API连接失败: {e}")
```

### 2. 提示词问题

**问题**: 提示词过长导致token超限
**解决**:
```python
def truncate_prompt(prompt, max_tokens=4000):
    """截断过长的提示词"""
    # 简单的token估算（1 token ≈ 4 characters）
    if len(prompt) > max_tokens * 4:
        return prompt[:max_tokens * 4] + "..."
    return prompt
```

**问题**: 中文提示词效果不佳
**解决**:
```python
# 优化中文提示词结构
def optimize_chinese_prompt(prompt):
    """优化中文提示词"""
    # 添加角色强化
    prompt = f"请严格按照以下角色要求执行：\n{prompt}"

    # 添加输出格式要求
    prompt += "\n\n请确保输出格式规范，使用中文回答。"

    return prompt
```

## 📚 扩展阅读

- [LangChain提示词工程指南](https://python.langchain.com/docs/modules/model_io/prompts/)
- [OpenAI API最佳实践](https://platform.openai.com/docs/guides/prompt-engineering)
- [Google AI提示词优化](https://ai.google.dev/docs/prompt_best_practices)

通过本指南，您应该能够轻松地修改TradingAgents项目的配置和提示词，以满足您的特定需求。如有问题，请参考测试目录中的示例代码或联系开发团队。
