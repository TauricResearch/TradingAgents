# TradingAgents 项目定制记录

本文件记录项目中的定制脚本、配置约定和集成逻辑，供后续 agent 快速理解上下文。

---

## 1. 持仓上下文注入功能

### 功能概述

在原有的多智能体股票分析流程基础上，新增了用户持仓管理能力。系统在分析时会自动将用户的实际持仓信息（成本、仓位、交易历史）注入到 Trader 和 Portfolio Manager 的 Prompt 中，使决策考虑用户的真实持仓状况。

### 核心模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 数据模型 | `tradingagents/portfolio/models.py` | PositionRecord, Transaction, Portfolio (Pydantic v2) |
| 存储层 | `tradingagents/portfolio/store.py` | PortfolioStore - JSON 文件持久化 CRUD |
| 上下文生成 | `tradingagents/portfolio/context.py` | build_portfolio_context() - 生成 Markdown 格式的持仓上下文 |
| 状态集成 | `tradingagents/agents/utils/agent_states.py` | AgentState 中的 `portfolio_context` 字段 |
| Prompt 注入 | `tradingagents/agents/trader/trader.py` | 交易员 Prompt 末尾追加持仓上下文 |
| Prompt 注入 | `tradingagents/agents/managers/portfolio_manager.py` | 组合经理 Prompt 末尾追加持仓上下文 |
| 配置项 | `tradingagents/default_config.py` | `portfolio_enabled`, `portfolio_path` |
| CLI 命令 | `cli/portfolio_cmd.py` | portfolio add/remove/list/clear, portfolio tx add/list |
| CLI 集成 | `cli/main.py` | 分析前自动检测持仓并提示 |

### 数据存储

- 默认路径: `~/.tradingagents/portfolio/portfolio.json`
- 环境变量覆盖: `TRADINGAGENTS_PORTFOLIO_PATH`
- 格式: JSON，包含 positions 数组和 transactions 数组

### 配置项

```python
# default_config.py 中的相关配置
"portfolio_enabled": True,   # 是否启用持仓上下文注入
"portfolio_path": "",        # 自定义持仓文件路径（空=使用默认）
```

对应环境变量:
- `TRADINGAGENTS_PORTFOLIO_ENABLED` → portfolio_enabled
- `TRADINGAGENTS_PORTFOLIO_PATH` → portfolio_path

---

## 2. 持仓同步脚本

### 脚本路径

`scripts/import_portfolio.py`

### 功能

从平级的 `financial-management` 项目一键同步持仓和交易记录到 TradingAgents 的 Portfolio 系统。

### 目录结构约定

两个项目**始终保持平级目录**：
```
parent_dir/
├── TradingAgents/           ← 本项目
└── financial-management/    ← 持仓数据源
```

脚本使用相对路径定位 financial-management：
```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINANCIAL_MGMT_ROOT = _PROJECT_ROOT.parent / "financial-management"
```

### 数据源文件

| 文件 | 路径（相对 financial-management） | 用途 |
|------|------|------|
| 持仓快照 | `data/parsed/{YYYY-MM}/holdings.json` | 当月持仓明细 |
| 交易记录 | `data/parsed/{YYYY-MM}/transactions.json` | 当月交易流水 |
| 组合状态 | `state/portfolio.json` | 精确均价（avg_cost） |

### 同步逻辑

1. 自动扫描 `data/parsed/` 下所有月份目录，选最新月份读取 holdings
2. 聚合**所有月份**的 transactions（不只是最新月份）
3. 只导入 `type=="trade"` 的真实买卖记录，过滤逆回购/银证转账等
4. 优先从 `state/portfolio.json` 获取精确 avg_cost
5. 根据 market 字段或 symbol 编码规则自动推断 .SH/.SZ 后缀
6. 全量同步（清空旧数据后重新导入）

### 使用方式

```bash
cd TradingAgents
python scripts/import_portfolio.py
```

---

## 3. 开发分支约定

- 新功能开发使用独立 feature 分支
- 本功能开发分支: `feature/portfolio-context`

---

## 4. 关键环境变量

| 变量 | 用途 | 示例 |
|------|------|------|
| `TRADINGAGENTS_OUTPUT_LANGUAGE` | 控制分析报告输出语言 | `Chinese` |
| `TRADINGAGENTS_PORTFOLIO_ENABLED` | 启用/禁用持仓注入 | `true` |
| `TRADINGAGENTS_PORTFOLIO_PATH` | 自定义持仓文件路径 | `/path/to/portfolio.json` |
| `TRADINGAGENTS_LLM_PROVIDER` | LLM 服务商 | `openai` |
| `TRADINGAGENTS_DEEP_THINK_LLM` | 深度思考模型 | `gpt-5.4` |
| `TRADINGAGENTS_QUICK_THINK_LLM` | 快速思考模型 | `gpt-5.4-mini` |

---

## 5. 数据流概览

```
financial-management (持仓源)
    │
    │  python scripts/import_portfolio.py
    ▼
~/.tradingagents/portfolio/portfolio.json
    │
    │  TradingAgentsGraph.propagate(ticker, date)
    ▼
AgentState.portfolio_context (Markdown 文本)
    │
    ├──→ Trader Prompt (考虑持仓做交易建议)
    └──→ Portfolio Manager Prompt (考虑持仓做最终评级)
```
