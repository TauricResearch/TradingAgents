# TradingAgents 中文使用指南

> 基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 定制，添加中文输出支持。

## 项目简介

TradingAgents 是一个多 Agent LLM 交易分析框架，模拟真实交易公司的工作流程：多个专业 AI Agent 协同分析、辩论，最终给出交易建议。

**⚠️ 声明：本项目仅供研究和学习使用，不构成任何投资建议。**

---

## Agent 架构

```
📊 分析师团队
├── 市场分析师     → 技术指标（MACD/RSI/均线等）
├── 情绪分析师     → 社交媒体舆情
├── 新闻分析师     → 宏观新闻 & 行业动态
└── 基本面分析师   → 财报、估值、公司健康度

🔬 研究员团队
├── 多头研究员     → 寻找买入理由
└── 空头研究员     → 寻找做空理由（结构化辩论）

💼 决策层
├── 研究主管       → 综合多空辩论，得出投资建议
├── 交易员         → 制定具体交易计划
├── 激进风控       → 支持高风险高收益策略
├── 保守风控       → 强调风险控制
├── 中性风控       → 中立评估
└── 风控主管       → 最终审批，输出 BUY / SELL / HOLD
```

---

## 快速开始

### 1. 环境准备

```bash
cd ~/.openclaw/workspace/TradingAgents
source .venv/bin/activate
```

### 2. 运行分析（命令行脚本）

```bash
# 分析 NVDA（今日日期）
GOOGLE_API_KEY=你的Key python run_analysis.py NVDA

# 分析 VOO
GOOGLE_API_KEY=你的Key python run_analysis.py VOO

# 指定日期
GOOGLE_API_KEY=你的Key python run_analysis.py NVDA 2026-03-20
```

结果自动保存到 `results/NVDA_日期.txt`，包含完整的多 Agent 分析报告。

### 3. 运行交互式 TUI 界面（推荐）

```bash
GOOGLE_API_KEY=你的Key python -m cli.main
```

会启动漂亮的终端界面，可以选择：
- 分析标的（任意股票代码）
- 使用哪些分析师
- 使用哪个 LLM 模型

---

## 配置说明

修改 `run_analysis.py` 顶部的 `config` 可调整行为：

```python
config["llm_provider"] = "google"          # 模型提供商：google / anthropic / openai
config["deep_think_llm"] = "gemini-2.5-flash"  # 深度推理用（研究员辩论/风控）
config["quick_think_llm"] = "gemini-2.5-flash" # 快速任务用（情绪/新闻分析）
config["max_debate_rounds"] = 1            # 多空辩论轮数（越多越慢越贵）
config["max_risk_discuss_rounds"] = 1      # 风控讨论轮数
```

### 支持的模型提供商

| 提供商 | `llm_provider` | 环境变量 | 推荐模型 |
|--------|---------------|---------|---------|
| Google Gemini | `google` | `GOOGLE_API_KEY` | `gemini-2.5-flash` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-5.4` |

---

## 支持的标的

| 标的 | 类型 | 支持情况 |
|------|------|---------|
| NVDA | 美股个股 | ✅ 完整支持（4 个分析师全部可用） |
| VOO | 美股 ETF | ✅ 支持（基本面分析师意义较小） |
| 其他美股 | - | ✅ 理论上支持 |
| Au99.99（黄金） | 国内 SGE | ⚠️ 需要自定义数据适配层 |

---

## 已知问题

1. **Gemini 偶发断连**：Google API 对长 prompt 偶尔返回 `Server disconnected`，脚本已内置 3 次自动重试。
2. **Python 3.14 兼容警告**：`Pydantic V1 not compatible` 是警告非错误，不影响运行。
3. **回测数据不可信**：框架在回测时可能存在前视偏差，历史回测结果仅供参考。

---

## 目录结构

```
TradingAgents/
├── run_analysis.py          # 中文分析入口脚本（定制）
├── .env                     # API Key 配置（已 gitignore）
├── results/                 # 分析结果输出目录
├── cli/                     # TUI 交互界面
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/        # 4 个分析师（已汉化）
│   │   ├── researchers/     # 多空研究员（已汉化）
│   │   ├── managers/        # 研究主管 + 风控主管（已汉化）
│   │   ├── trader/          # 交易员（已汉化）
│   │   └── risk_mgmt/       # 风控辩手团队（已汉化）
│   ├── dataflows/           # 数据获取层（yfinance）
│   └── default_config.py    # 默认配置
└── README_CN.md             # 本文件
```

---

## Gitea 仓库

`http://192.168.1.94:4000/flyingjoe2010/TradingAgents`

---

## 参考

- 原项目：https://github.com/TauricResearch/TradingAgents
- 论文：https://arxiv.org/abs/2412.20138
