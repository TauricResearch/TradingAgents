# TradingAgents 中文版

> 基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 定制，新增：
> - 🇨🇳 全部 Agent 输出改为简体中文
> - 💬 支持注入自定义分析视角
> - 🔄 Gemini API 自动重试（SSL 断连容错）
> - 📝 中文分析入口脚本 `run_analysis.py`
> - 🖥️ TUI 界面新增用户视角输入步骤

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

### 1. 克隆并安装

```bash
git clone https://github.com/dw1161/TradingAgents.git
cd TradingAgents

# 创建虚拟环境（推荐 Python 3.11-3.13）
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

创建 `.env` 文件（已被 gitignore，不会上传）：

```bash
# 三选一，用哪个填哪个
GOOGLE_API_KEY=你的Gemini_Key
ANTHROPIC_API_KEY=你的Claude_Key
OPENAI_API_KEY=你的OpenAI_Key
```

### 3. 运行分析

**TUI 交互界面（推荐，有实时进度展示）：**
```bash
python -m cli.main
```

**命令行脚本：**
```bash
# 基础用法
python run_analysis.py NVDA 2026-03-20

# 注入自定义分析视角（核心功能）
python run_analysis.py NVDA 2026-03-20 "中东地缘冲突升级是当前美股主要风险，请重点评估"

# 交互式输入视角
python run_analysis.py NVDA
```

结果保存至 `results/NVDA_日期.txt`。

---

## 自定义分析视角（新功能）

支持在分析开始前注入你的判断框架，**所有 Agent 都会优先考虑此视角**：

```bash
# 地缘政治视角
python run_analysis.py NVDA 2026-03-20 "中东伊朗局势升级正在推高油价并压制科技股估值"

# 宏观政策视角  
python run_analysis.py NVDA 2026-03-20 "美联储降息预期升温，流动性改善利好成长股"

# 产业趋势视角
python run_analysis.py NVDA 2026-03-20 "AI算力需求超预期，数据中心扩张带来订单增量"
```

TUI 界面（`cli.main`）在 Step 8 也支持输入视角。

---

## 配置说明

修改 `run_analysis.py` 顶部调整行为：

```python
config["llm_provider"] = "google"              # google / anthropic / openai
config["deep_think_llm"] = "gemini-2.5-flash"  # 深度推理（研究员辩论/风控）
config["quick_think_llm"] = "gemini-2.5-flash" # 快速任务（情绪/新闻分析）
config["max_debate_rounds"] = 1                # 辩论轮数（越多越慢越贵）
```

### 支持的模型提供商

| 提供商 | `llm_provider` | 环境变量 | 推荐模型 |
|--------|---------------|---------|---------|
| Google Gemini | `google` | `GOOGLE_API_KEY` | `gemini-2.5-flash` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-5.4` |

---

## 日期参数说明

传入日期为**截止日期**，Agent 用该日期及之前的数据分析：
- 推荐传**昨天或前天**（今天数据不完整）
- 可传历史日期做回测验证

---

## 支持的标的

| 标的 | 支持情况 |
|------|---------|
| 美股个股（NVDA/AAPL 等） | ✅ 完整支持 |
| 美股 ETF（VOO/SPY 等） | ✅ 支持（基本面分析意义较小） |
| 国内 A 股 / 商品 | ⚠️ 需自定义数据适配层 |

---

## 已知问题

1. **Gemini 偶发断连**：已在 LLM 客户端层加入指数退避自动重试（最多 5 次）
2. **Python 3.14 Pydantic 警告**：Warning 非 Error，不影响运行，忽略即可
3. **回测前视偏差**：Agent 联网获取信息可能导致回测数据失真，历史结果仅供参考

---

## 本版改动说明

| 文件 | 改动 |
|------|------|
| `tradingagents/agents/analysts/*.py` | 所有分析师 prompt 加中文输出指令 |
| `tradingagents/agents/researchers/*.py` | 多空研究员 prompt 加中文指令 |
| `tradingagents/agents/managers/*.py` | 研究主管/风控主管加中文指令 |
| `tradingagents/agents/trader/trader.py` | 交易员加中文指令 |
| `tradingagents/agents/risk_mgmt/*.py` | 风控辩手加中文指令 |
| `tradingagents/llm_clients/google_client.py` | 加入 SSL 断连自动重试 |
| `tradingagents/graph/propagation.py` | 支持 `user_context` 参数 |
| `tradingagents/graph/trading_graph.py` | `propagate()` 支持用户视角注入 |
| `cli/main.py` | TUI 新增 Step 8 用户视角输入 |
| `run_analysis.py` | 新增中文分析入口脚本 |

---

## 参考

- 原项目：https://github.com/TauricResearch/TradingAgents
- 论文：https://arxiv.org/abs/2412.20138
