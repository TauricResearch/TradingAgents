# 🚀 TradingAgents 快速开始指南

## ✅ 部署已完成！

恭喜！TradingAgents 已成功配置为使用 DeepSeek API。

---

## 📝 快速运行

### 1. 激活环境
```bash
conda activate tradingagents
```

### 2. 运行测试（推荐新手）
```bash
python test_simple.py
```

这将分析 NVDA（英伟达）股票并给出交易建议。

### 3. 运行完整版本
```bash
python main.py
```

### 4. 使用 CLI 界面
```bash
python -m cli.main
```

---

## 🎯 自定义分析

### 修改股票和日期

编辑 `test_simple.py`，找到这一行：
```python
_, decision = ta.propagate("NVDA", "2024-05-10")
```

改为：
```python
_, decision = ta.propagate("AAPL", "2024-06-15")  # 分析苹果股票
```

### 启用更多分析师

在 `test_simple.py` 中找到：
```python
selected_analysts = ["market"]  # 只有市场分析师
```

改为：
```python
selected_analysts = ["market", "fundamentals"]  # 添加基本面分析
# 或
selected_analysts = ["market", "social", "fundamentals"]  # 添加社交媒体分析
```

**注意**: 更多分析师 = 更多 API 调用 = 更高成本

---

## 💰 成本控制

### 使用更便宜的模型

编辑 `main.py` 或 `test_simple.py`：
```python
config["deep_think_llm"] = "deepseek-chat"  # 改用非思考模式
config["quick_think_llm"] = "deepseek-chat"
```

### 减少辩论轮次
```python
config["max_debate_rounds"] = 1  # 默认值，可以保持
```

---

## 📊 理解输出

### 交易决策类型
- **BUY**: 买入建议
- **SELL**: 卖出建议  
- **HOLD**: 持有建议

### 分析流程
1. 📈 **数据收集**: 获取股票价格、技术指标
2. 🤖 **分析师分析**: 各专业分析师独立分析
3. 💬 **多方辩论**: 看涨/看跌研究员辩论
4. 📝 **交易员决策**: 基于辩论结果制定计划
5. ⚖️ **风险评估**: 风险管理团队评估
6. ✅ **最终决策**: 投资组合经理批准

---

## 🔧 配置文件说明

### 当前配置（DeepSeek）

**LLM 设置**:
- Provider: DeepSeek API
- Deep Think: `deepseek-reasoner` (思考模式)
- Quick Think: `deepseek-chat` (快速模式)

**数据源**:
- 股票数据: YFinance
- 技术指标: YFinance
- 基本面: YFinance
- 新闻: YFinance

### 切换回 OpenAI

如果想使用 OpenAI，修改配置：
```python
config["backend_url"] = "https://api.openai.com/v1"
config["deep_think_llm"] = "o1-mini"
config["quick_think_llm"] = "gpt-4o-mini"
```

并在 `.env` 中使用 OpenAI API 密钥。

### 使用 OpenRouter

如果想使用 OpenRouter，修改配置：
```python
config["backend_url"] = "https://openrouter.ai/api/v1"
config["deep_think_llm"] = "openai/gpt-4o-mini"  # 或其他 OpenRouter 模型
config["quick_think_llm"] = "openai/gpt-4o-mini"
```

并在 `.env` 中设置 `OPENAI_API_KEY` 为您的 OpenRouter 密钥。
**注意**: 系统会自动检测 OpenRouter 并禁用 embeddings 功能（避免 `AttributeError`）。

---

## ⚠️ 重要提示

### 1. 记忆功能已禁用
- DeepSeek 不支持 embeddings API
- 系统使用虚拟 embeddings
- 不影响核心分析功能

### 2. 仅供研究使用
- **不构成投资建议**
- 请勿直接用于实际交易
- 建议进行充分回测

### 3. API 配额管理
- 监控 DeepSeek API 使用量
- Alpha Vantage 免费版: 60次/分钟
- 避免短时间内大量请求

---

## 📚 进阶功能

### 批量分析多个股票

创建新脚本 `batch_analysis.py`:
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

load_dotenv()

# 配置
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["backend_url"] = "https://api.deepseek.com"
config["deep_think_llm"] = "deepseek-chat"
config["quick_think_llm"] = "deepseek-chat"

ta = TradingAgentsGraph(debug=False, config=config, selected_analysts=["market"])

# 批量分析
stocks = ["NVDA", "AAPL", "MSFT", "GOOGL"]
date = "2024-05-10"

for stock in stocks:
    print(f"\n分析 {stock}...")
    _, decision = ta.propagate(stock, date)
    print(f"{stock}: {decision}")
```

### 回测功能

查看 `main.py` 中的反思功能：
```python
# 在交易后反思和学习
ta.reflect_and_remember(returns_losses=1000)  # 传入收益/损失
```

---

## 🐛 常见问题

### Q: 运行很慢怎么办？
A: 
- 使用 `deepseek-chat` 替代 `deepseek-reasoner`
- 减少分析师数量
- 检查网络连接

### Q: 出现 API 错误？
A: 
- 检查 API 密钥是否正确
- 确认 API 配额未用完
- 查看错误信息详情

### Q: 如何保存分析结果？
A: 
结果自动保存在 `eval_results/{股票代码}/` 目录下

---

## 📞 获取帮助

- **配置指南**: 查看 `DEEPSEEK_CONFIG.md`
- **部署报告**: 查看 `DEPLOYMENT_SUCCESS.md`
- **GitHub Issues**: https://github.com/TauricResearch/TradingAgents/issues
- **Discord**: https://discord.com/invite/hk9PGKShPK

---

## 🎉 开始使用！

现在您可以开始使用 TradingAgents 进行股票分析了！

```bash
conda activate tradingagents
python test_simple.py
```

祝您分析愉快！📈

---

*最后更新: 2025-11-20*
