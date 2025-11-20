---
description: 如何部署 TradingAgents 项目
---

# TradingAgents 部署工作流

本工作流描述如何从零开始部署 TradingAgents 多智能体交易框架。

## 前置条件

- 已安装 Conda
- 已安装 Git
- 有 OpenAI API 密钥
- 有 Alpha Vantage API 密钥（免费获取：https://www.alphavantage.co/support/#api-key）

## 部署步骤

### 1. 克隆项目（如果还未克隆）

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

### 2. 创建 Conda 虚拟环境

// turbo
```bash
conda create -n tradingagents python=3.13 -y
```

### 3. 激活环境并安装依赖

```bash
conda activate tradingagents
pip install -r requirements.txt
```

### 4. 配置 API 密钥

复制示例环境文件：
python -m cli.main
```

这将启动一个交互式界面，你可以选择：
- 股票代码（ticker）
- 日期
- LLM 模型
- 研究深度等参数

#### 方式 2: 使用 Python 代码

创建测试脚本或运行 `main.py`：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

### 6. 自定义配置（可选）

你可以修改默认配置来使用不同的 LLM 模型或数据源：

```python
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"  # 节省成本
config["quick_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 1

# 配置数据供应商
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage",
}

ta = TradingAgentsGraph(debug=True, config=config)
```

## 重要提示

⚠️ **成本控制**: 该框架会进行大量 API 调用。测试时建议使用 `gpt-4o-mini` 等较便宜的模型。

⚠️ **免责声明**: TradingAgents 仅用于研究目的，不构成财务、投资或交易建议。

⚠️ **API 限制**: Alpha Vantage 免费版有速率限制。TradingAgents 用户可获得提升的限制（每分钟 60 次请求，无每日限制）。

## 验证部署

运行以下命令验证环境配置正确：

// turbo
```bash
python test.py
```

或者运行一个简单的测试：

```bash
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('部署成功！')"
```

## 故障排除

### 问题: 缺少 API 密钥
**解决方案**: 确保 `.env` 文件存在且包含有效的 API 密钥，或设置环境变量。

### 问题: 依赖安装失败
**解决方案**: 
- 确保使用 Python 3.13
- 尝试升级 pip: `pip install --upgrade pip`
- 逐个安装依赖以识别问题包

### 问题: Alpha Vantage 速率限制
**解决方案**: 
- 等待一分钟后重试
- 考虑升级到 Alpha Vantage Premium
- 或在配置中切换到其他数据源

## 下一步

- 查看 `tradingagents/default_config.py` 了解所有可配置选项
- 阅读项目文档了解多智能体架构
- 加入 Discord 社区: https://discord.com/invite/hk9PGKShPK
