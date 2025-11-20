# DeepSeek API 配置指南

## 📋 配置步骤

### 1. 获取 DeepSeek API 密钥

访问 DeepSeek 官网获取 API 密钥：
- 网址: https://platform.deepseek.com/
- 注册并登录账户
- 在 API Keys 页面创建新的 API 密钥

### 2. 配置环境变量

编辑项目根目录下的 `.env` 文件，填入您的 API 密钥：

```bash
# DeepSeek API 密钥（使用 OPENAI_API_KEY 变量名，因为 DeepSeek 兼容 OpenAI SDK）
OPENAI_API_KEY=your_deepseek_api_key_here

# Alpha Vantage API 密钥（用于获取股票数据）
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key_here
```

**重要提示**: 
- DeepSeek API 使用 `OPENAI_API_KEY` 作为环境变量名
- 这是因为 DeepSeek 使用 OpenAI 兼容的 API 格式
- 不要将其与 OpenAI 的 API 密钥混淆

### 3. 验证配置

运行测试脚本验证 DeepSeek API 是否配置正确：

```bash
conda activate tradingagents
python test_deepseek.py
```

如果看到 "✅ DeepSeek API 配置正确"，说明配置成功！

## 🚀 运行 TradingAgents

### 使用 Python 脚本

已经为您配置好了 `main.py`，直接运行：

```bash
conda activate tradingagents
python main.py
```

### 使用 CLI 界面

```bash
conda activate tradingagents
python -m cli.main
```

## 🔧 DeepSeek 模型说明

项目已配置使用以下 DeepSeek 模型：

- **deepseek-reasoner**: 深度思考模型（思考模式）
  - 用于复杂的分析和决策任务
  - 对应 `deep_think_llm` 配置
  
- **deepseek-chat**: 快速对话模型（非思考模式）
  - 用于快速响应和简单任务
  - 对应 `quick_think_llm` 配置

## 💰 成本优化建议

DeepSeek API 的定价比 OpenAI 更实惠，但仍建议：

1. **测试时使用较少的辩论轮次**
   - 当前配置: `max_debate_rounds = 1`
   - 可以根据需要调整

2. **监控 API 使用量**
   - 在 DeepSeek 控制台查看使用情况
   - 设置使用限额避免超支

3. **使用缓存**
   - 项目会缓存股票数据
   - 避免重复调用相同数据

## 📊 配置文件说明

主要配置在 `main.py` 中：

```python
config = DEFAULT_CONFIG.copy()

# DeepSeek API 配置
config["llm_provider"] = "openai"  # 使用 OpenAI 兼容接口
config["backend_url"] = "https://api.deepseek.com"  # DeepSeek API 端点
config["deep_think_llm"] = "deepseek-reasoner"  # 思考模式
config["quick_think_llm"] = "deepseek-chat"  # 非思考模式
config["max_debate_rounds"] = 1  # 辩论轮次

# 数据源配置
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage",
}
```

## ❓ 常见问题

### Q: 为什么使用 OPENAI_API_KEY 而不是 DEEPSEEK_API_KEY？

A: DeepSeek API 使用 OpenAI 兼容的格式，langchain-openai 库默认读取 `OPENAI_API_KEY` 环境变量。通过设置 `base_url="https://api.deepseek.com"`，我们将请求重定向到 DeepSeek 的服务器。

### Q: 可以同时使用 OpenAI 和 DeepSeek 吗？

A: 可以，但需要修改代码来支持不同的 API 密钥。当前配置只支持一个 LLM 提供商。

### Q: Alpha Vantage API 是必需的吗？

A: 是的，用于获取股票基本面数据和新闻。您可以免费获取 API 密钥: https://www.alphavantage.co/support/#api-key

### Q: 如何切换回 OpenAI？

A: 修改 `main.py` 中的配置：
```python
config["backend_url"] = "https://api.openai.com/v1"
config["deep_think_llm"] = "gpt-4o"
config["quick_think_llm"] = "gpt-4o-mini"
```
并在 `.env` 中使用 OpenAI 的 API 密钥。

## 🔗 相关链接

- DeepSeek 平台: https://platform.deepseek.com/
- DeepSeek API 文档: https://platform.deepseek.com/api-docs/
- Alpha Vantage: https://www.alphavantage.co/
- TradingAgents GitHub: https://github.com/TauricResearch/TradingAgents
