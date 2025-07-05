# TradingAgents 中文文档

## 📖 概述

TradingAgents是一个基于多智能体的金融分析系统，现已全面支持中国A股市场和多LLM提供商。本系统通过智能体协作提供深度的股票分析和投资建议。

## 🌟 主要特性

### 🌍 多市场支持
- **美股市场**: 完整的美国股票市场分析
- **中国A股市场**: 通达信API集成，支持实时A股数据 ⭐ **新功能**
- **智能市场选择**: 交互式CLI市场选择界面

### 🤖 多智能体分析框架
- **市场分析师**: 技术分析和图表模式识别
- **基本面分析师**: 财务数据和公司基本面分析
- **新闻分析师**: 新闻情绪和市场情绪分析
- **多空研究员**: 多角度投资观点辩论
- **交易员智能体**: 综合决策和风险评估
- **反思智能体**: 分析质量控制和改进建议

### 🧠 多LLM提供商支持
- **百炼(DashScope)**: 阿里云通义千问模型系列 ⭐ **推荐中国用户**
  - **当前设置**: 百炼作为主要选项，智能回退机制
- **OpenAI**: GPT-4o, GPT-4o-mini, o1, o3系列
- **Google AI**: Gemini 2.0/2.5 Flash系列
- **Anthropic**: Claude 3.5/4系列

### 🗄️ 企业级数据库集成
- **MongoDB**: 持久化数据存储和分析 ⭐ **新功能**
- **Redis**: 高性能缓存系统 ⭐ **新功能**
- **智能缓存**: 自动回退机制和性能优化

### 📊 数据源集成
- **美股数据**: Yahoo Finance集成
- **A股数据**: 通达信API集成 ⭐ **新功能**
  - 上海证券交易所 (60xxxx)
  - 深圳证券交易所 (00xxxx)
  - 创业板 (30xxxx)
  - 科创板 (68xxxx)
- **财经新闻**: 多源新闻聚合和情绪分析

### ⚙️ 配置管理
- LLM提供商设置 (百炼、OpenAI、Google、Anthropic)
  - **百炼(DashScope)**: 完整支持通义千问模型系列 ⭐ **推荐中国用户**
  - **当前设置**: 百炼作为主要选项，智能回退机制
- 市场选择和数据源配置
  - **美股市场**: Yahoo Finance集成
  - **中国A股市场**: 通达信API集成 ⭐ **新功能**
- 数据库和缓存系统
  - **MongoDB**: 持久化数据存储
  - **Redis**: 高性能缓存
  - **智能缓存**: 自动回退机制
- 辩论和讨论参数配置
- API配置和限制设置

### 🔧 高级功能
- **多市场支持**: 美股和中国A股
- **数据库集成**: MongoDB和Redis企业部署
- **智能缓存**: 自适应缓存管理和回退
- **多LLM支持**: 百炼、OpenAI、Google、Anthropic
- **通达信集成**: 实时A股数据访问
- 风险管理模板
- 性能优化
- 自定义提示词创建
- 环境特定配置

## 🚀 快速开始

### 1. 安装和设置
```bash
# 克隆仓库
git clone https://github.com/your-repo/TradingAgents.git
cd TradingAgents

# 安装依赖
pip install -r requirements.txt
pip install pytdx beautifulsoup4  # 中国市场支持

# 配置环境变量
cp .env.example .env
# 编辑.env文件，填入您的API密钥
```

### 2. 基本配置

**分析美股 (使用OpenAI)**:
```env
OPENAI_API_KEY=your_openai_api_key
FINNHUB_API_KEY=your_finnhub_api_key
```

**分析中国A股 (需要百炼)**:
```env
DASHSCOPE_API_KEY=your_dashscope_api_key
FINNHUB_API_KEY=your_finnhub_api_key
```

### 3. 运行分析
```bash
python -m cli.main
```

按照交互式提示选择市场、输入股票代码并配置分析参数。

## 📚 文档导航

### 🎯 新手指南
- **[快速开始指南](quick_start_guide.md)** - 5分钟快速设置和首次运行
- **[配置指南](configuration_guide.md)** - 详细的配置选项和自定义设置

### 🏗️ 技术文档
- **[架构指南](architecture_guide.md)** - 系统架构和技术实现详解
- **[提示词模板](prompt_templates.md)** - 智能体提示词自定义

### 📋 参考资料
- **[快速参考](quick_reference.md)** - 常用配置和修改速查表

## 🔑 API密钥配置说明

### 必需的API密钥

**百炼API密钥仅在以下情况需要**:
1. 📈 **分析中国A股股票** (使用通达信数据 + 百炼embeddings)
2. 🤖 **选择百炼作为LLM提供商** (通义千问模型)

**分析美股使用OpenAI/Google模型时**: 不需要百炼API密钥

### API密钥获取
- **百炼(DashScope)**: https://dashscope.aliyun.com/
- **OpenAI**: https://platform.openai.com/
- **Google AI**: https://ai.google.dev/
- **Anthropic**: https://console.anthropic.com/
- **FinnHub**: https://finnhub.io/ (金融数据，必需)

## 🌍 支持的市场和交易所

### 美股市场
- **格式**: 1-5位字母代码 (如 AAPL, SPY, TSLA)
- **数据源**: Yahoo Finance
- **示例**: AAPL (苹果), SPY (标普500ETF), TSLA (特斯拉)

### 中国A股市场
- **格式**: 6位数字代码
- **数据源**: 通达信API
- **支持交易所**:
  - 上海证券交易所: 60xxxx (如 600036 招商银行)
  - 深圳证券交易所: 00xxxx (如 000001 平安银行)
  - 创业板: 30xxxx (如 300001 科技股)
  - 科创板: 68xxxx (如 688001 创新公司)

## 🗄️ 数据库功能 (可选)

### MongoDB集成
- **用途**: 持久化数据存储和历史分析
- **功能**: Token使用跟踪、分析结果存储、用户会话管理
- **设置**: `MONGODB_ENABLED=true` 在.env中

### Redis集成
- **用途**: 高性能缓存和会话管理
- **功能**: 快速数据访问、实时缓存、性能优化
- **设置**: `REDIS_ENABLED=true` 在.env中

### 智能回退
- **第一层**: Redis高性能缓存
- **第二层**: MongoDB持久化存储
- **第三层**: 文件缓存 (始终可用)

## 🎯 使用场景

### 场景1: 美股日常分析
- **配置**: OpenAI + FinnHub
- **市场**: 美股
- **特点**: 快速、稳定、国际化

### 场景2: 中国A股专业分析
- **配置**: 百炼 + FinnHub + 通达信
- **市场**: 中国A股
- **特点**: 本土化、实时数据、中文优化

### 场景3: 企业级部署
- **配置**: 多LLM + MongoDB + Redis
- **市场**: 美股 + A股
- **特点**: 高性能、可扩展、完整功能

## 🛠️ 故障排除

### 常见问题
1. **API密钥错误**: 检查.env文件中的密钥格式
2. **网络连接问题**: 系统自动回退到缓存数据
3. **数据库连接失败**: 自动回退到文件缓存
4. **股票代码格式错误**: 参考市场特定格式要求

### 调试模式
```bash
export TRADINGAGENTS_LOG_LEVEL=DEBUG
python -m cli.main
```

## 🤝 贡献和支持

### 获取帮助
- **GitHub Issues**: 报告错误和功能请求
- **文档**: 查阅详细的配置和使用指南
- **社区**: 参与讨论和分享使用经验

### 贡献代码
- Fork项目并创建功能分支
- 提交Pull Request
- 遵循代码规范和测试要求

---

## 📈 系统优势

### 技术优势
- **多智能体协作**: 多角度分析，提高决策质量
- **多LLM支持**: 降低单点故障风险，提高可靠性
- **智能缓存**: 三层缓存架构，确保高性能和高可用
- **模块化设计**: 易于扩展和维护

### 市场优势
- **全球市场覆盖**: 支持美股和中国A股两大主要市场
- **本土化优化**: 中国市场专用数据源和模型
- **实时数据**: 通达信API提供实时A股数据
- **智能回退**: 确保服务连续性和稳定性

🎉 **开始您的智能投资分析之旅！** TradingAgents为您提供专业级的多市场股票分析能力。
