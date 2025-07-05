# TradingAgents 快速开始指南

## 🚀 概述

本指南将帮助您快速开始使用TradingAgents，包括新的中国市场功能、数据库集成和多LLM支持。

## ⚡ 快速设置 (5分钟)

### 1. 前置条件
```bash
# 需要Python 3.8+
python --version

# 克隆仓库
git clone https://github.com/your-repo/TradingAgents.git
cd TradingAgents

# 安装依赖
pip install -r requirements.txt
pip install pytdx beautifulsoup4  # 中国市场支持
```

### 2. 环境配置
```bash
# 复制环境模板
cp .env.example .env

# 编辑.env文件，填入您的API密钥
nano .env  # 或使用您喜欢的编辑器
```

**最小必需配置**:

**仅分析美股时**:
```env
# OpenAI或Google AI (选择一个)
OPENAI_API_KEY=your_openai_api_key_here
# 或者
GOOGLE_API_KEY=your_google_api_key_here

# FinnHub (金融数据必需)
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**分析中国A股或使用百炼LLM时**:
```env
# 百炼 (中国股票或通义千问模型必需)
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# FinnHub (金融数据必需)
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**注意**: 
- **百炼API密钥仅在以下情况需要**:
  - 分析中国A股股票 (使用通达信数据 + 百炼embeddings)
  - 选择百炼作为LLM提供商 (通义千问模型)
- **分析美股使用OpenAI/Google模型时**: 不需要百炼

### 3. 首次运行
```bash
# 启动应用程序
python -m cli.main

# 按照交互式提示操作:
# 1. 选择市场: 美股或中国A股
# 2. 输入股票代码 (如 AAPL 或 000001)
# 3. 选择分析日期
# 4. 选择分析师团队
# 5. 选择LLM提供商 (推荐百炼)
# 6. 运行分析
```

## 🌟 功能概览

### 🇺🇸 美股分析
- **支持代码**: AAPL, SPY, TSLA, NVDA, MSFT 等
- **数据源**: Yahoo Finance
- **格式**: 1-5位字母代码
- **示例**: `AAPL` (苹果公司)

### 🇨🇳 中国A股分析
- **支持交易所**: 
  - 上交所 (60xxxx): `600036` (招商银行)
  - 深交所 (00xxxx): `000001` (平安银行)
  - 创业板 (30xxxx): `300001` (科技股)
  - 科创板 (68xxxx): `688001` (创新公司)
- **数据源**: 通达信API
- **格式**: 6位数字代码

### 🤖 多LLM支持
- **百炼(DashScope)**: 通义千问模型，中文优化
- **OpenAI**: GPT-4o, GPT-4o-mini, o1, o3系列
- **Google AI**: Gemini 2.0/2.5 Flash系列
- **Anthropic**: Claude 3.5/4系列

## 📋 分步操作演示

### 步骤1: 市场选择
```
? Select Stock Market:
  US Stock - Examples: SPY, AAPL, TSLA
❯ China A-Share - Examples: 000001, 600036, 000858
```

### 步骤2: 股票代码输入
```
格式要求: 6位数字代码 (如 600036, 000001)
示例: 000001, 600036, 300001, 688001
? Enter China A-Share ticker symbol: 000001
✅ Valid A-share code: 000001 (will use TongDaXin data source)
```

### 步骤3: 分析配置
```
? Select your research depth:
❯ Light (1 round) - 快速分析
  Medium (2 rounds) - 平衡分析  
  Deep (3 rounds) - 深度分析

? Select your LLM Provider:
❯ DashScope (Alibaba Cloud)
  OpenAI
  Google AI
  Anthropic
```

### 步骤4: 模型选择
```
? Select Your [Quick-Thinking LLM Engine]:
❯ Qwen-Turbo - 快速响应，适合快速任务
  Qwen-Plus - 平衡性能和成本
  Qwen-Max - 复杂分析的最佳性能

? Select Your [Deep-Thinking LLM Engine]:
❯ Qwen-Plus - 平衡性能和成本 (推荐)
  Qwen-Max - 复杂分析的最佳性能
  Qwen-Max-LongContext - 超长上下文支持
```

## 🗄️ 数据库设置 (可选)

### 启用高性能缓存

**1. 启动数据库服务**:
```bash
# MongoDB用于持久化存储
docker run -d -p 27017:27017 --name mongodb mongo

# Redis用于高性能缓存
docker run -d -p 6379:6379 --name redis redis
```

**2. 在.env中启用**:
```env
# 启用数据库缓存
MONGODB_ENABLED=true
REDIS_ENABLED=true

# MongoDB配置
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DATABASE=tradingagents

# Redis配置  
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

**3. 重启应用程序**:
```bash
python -m cli.main
# 系统现在将使用数据库缓存以提高性能
```

## 🔧 配置示例

### 示例1: 使用OpenAI分析美股
```env
OPENAI_API_KEY=your_openai_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI选择**:
- 市场: 美股
- 股票代码: AAPL
- LLM提供商: OpenAI
- 模型: GPT-4o-mini (快速), o1 (深度)

**注意**: 使用OpenAI分析美股时不需要百炼

### 示例2: 使用Google AI分析美股
```env
GOOGLE_API_KEY=your_google_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI选择**:
- 市场: 美股
- 股票代码: TSLA
- LLM提供商: Google AI
- 模型: Gemini 2.0 Flash (快速), Gemini 2.5 Flash (深度)

**注意**: 使用Google AI分析美股时不需要百炼

### 示例3: 中国A股分析 (需要百炼)
```env
DASHSCOPE_API_KEY=your_dashscope_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI选择**:
- 市场: 中国A股
- 股票代码: 000001
- LLM提供商: 百炼
- 模型: qwen-turbo (快速), qwen-plus (深度)

**注意**: 中国股票分析需要百炼API密钥 (通达信数据 + embeddings)

### 示例4: 使用百炼LLM分析美股 (需要百炼)
```env
DASHSCOPE_API_KEY=your_dashscope_key
FINNHUB_API_KEY=your_finnhub_key
```

**CLI选择**:
- 市场: 美股
- 股票代码: SPY
- LLM提供商: 百炼(阿里云)
- 模型: qwen-turbo (快速), qwen-plus (深度)

**注意**: 选择百炼作为LLM提供商时需要百炼API密钥

## 🛠️ 故障排除

### 常见问题

**1. API密钥错误**:
```
错误: Invalid API key
解决方案: 检查.env文件并确保API密钥格式正确
```

**2. 通达信连接问题**:
```
错误: TongDaXin API unavailable
解决方案: 系统自动回退到缓存数据
```

**3. 数据库连接问题**:
```
错误: MongoDB/Redis connection failed
解决方案: 系统自动回退到文件缓存
```

**4. 股票代码格式错误**:
```
错误: Invalid ticker format
解决方案: 
- 美股: 使用1-5位字母代码 (AAPL)
- A股: 使用6位数字代码 (000001)
```

### 调试模式
```bash
# 启用调试日志
export TRADINGAGENTS_LOG_LEVEL=DEBUG
python -m cli.main
```

## 📊 示例分析输出

### 美股分析 (AAPL)
```
📈 AAPL (苹果公司) 分析结果
市场: 美国证券交易所
数据源: Yahoo Finance

🔍 技术分析:
- 当前价格: $150.25 (+2.3%)
- RSI: 65.2 (中性偏多)
- 移动平均线: 高于20日和50日均线

💰 基本面分析:
- 市盈率: 28.5
- 营收增长: 8.2% 同比
- 市值: $2.4万亿

📰 新闻情绪: 积极 (0.72/1.0)
🎯 建议: 买入，目标价 $165
```

### 中国A股分析 (000001)
```
📈 000001 (平安银行) 分析结果
市场: 深圳证券交易所
数据源: 通达信API

🔍 技术分析:
- 当前价格: ¥12.85 (+1.8%)
- RSI: 58.3 (中性)
- 成交量: 高于平均水平

💰 基本面分析:
- 市盈率: 5.2
- ROE: 12.8%
- 账面价值: ¥15.20

📰 新闻情绪: 中性 (0.55/1.0)
🎯 建议: 持有，目标价 ¥14.50
```

## 🎯 下一步

### 探索高级功能
1. **自定义提示词**: 修改智能体提示词以适应特定策略
2. **数据库分析**: 分析历史性能
3. **多市场比较**: 比较美股和中国股票
4. **风险管理**: 配置风险参数

### 了解更多
- [配置指南](configuration_guide.md) - 详细配置选项
- [架构指南](architecture_guide.md) - 系统架构概览
- [API文档](api_documentation.md) - API参考

### 获取支持
- GitHub Issues: 报告错误和功能请求
- 文档: 全面的指南和示例
- 社区: 加入讨论和分享策略

---

🎉 **恭喜！** 您现在已经准备好使用TradingAgents分析美股和中国市场了。系统提供智能回退、多LLM支持和企业级缓存，以获得最佳性能。
