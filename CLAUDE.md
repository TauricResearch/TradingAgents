# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言规则
- **用中文回答用户的问题**

## 项目概述

TradingAgents 是一个基于 LangGraph 的多智能体 LLM 金融交易框架，模拟真实交易公司的运作模式。通过部署专业化的 LLM 智能体（基本面分析师、情绪分析师、技术分析师、交易员、风险管理团队）协作评估市场状况并做出交易决策。

## 常用命令

```bash
# 激活环境
source env312/bin/activate

# CLI 交互模式（推荐）
python -m cli.main

# 单股分析（编程方式）
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; ta = TradingAgentsGraph(debug=True); _, decision = ta.propagate('NVDA', '2026-01-15'); print(decision)"

# 运行测试
python -m pytest orchestrator/tests/

# Orchestrator 回测模式
QUANT_BACKTEST_PATH=/path/to/quant_backtest python orchestrator/examples/run_backtest.py

# Orchestrator 实时模式
QUANT_BACKTEST_PATH=/path/to/quant_backtest python orchestrator/examples/run_live.py
```

## 核心架构

### 工作流程
```
分析师团队 → 研究员辩论 → 交易员 → 风险管理辩论 → 组合经理
```

### 关键组件

**tradingagents/** - 核心多智能体框架
- `agents/` - LLM智能体实现 (分析师、研究员、交易员、风控)
- `dataflows/` - 数据源集成，通过 `interface.py` 路由到 yfinance/alpha_vantage/china_data
- `graph/` - LangGraph 工作流编排，`trading_graph.py` 是主协调器
- `llm_clients/` - 多Provider LLM支持 (OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama)
- `default_config.py` - 默认配置（LLM provider、模型选择、数据源路由、辩论轮数）

**orchestrator/** - 量化+LLM信号融合层
- `orchestrator.py` - 主协调器，融合 quant 和 LLM 信号
- `quant_runner.py` - 量化信号获取
- `llm_runner.py` - LLM 信号获取（调用 TradingAgentsGraph）
- `signals.py` - 信号合并逻辑
- `backtest_mode.py` / `live_mode.py` - 回测/实时运行模式
- `contracts/` - 配置和结果契约定义

**cli/** - 交互式命令行界面
- `main.py` - Typer CLI 入口，实时显示智能体状态和报告

## 配置系统

### TradingAgents 配置 (`tradingagents/default_config.py`)

运行时可覆盖的关键配置：
- `llm_provider`: "openai" | "google" | "anthropic" | "xai" | "openrouter" | "ollama"
- `deep_think_llm`: 复杂推理模型（本地默认 `MiniMax-M2.7-highspeed`）
- `quick_think_llm`: 快速任务模型（本地默认 `MiniMax-M2.7-highspeed`）
- `backend_url`: LLM API endpoint
- `data_vendors`: 按类别配置数据源 (core_stock_apis, technical_indicators, fundamental_data, news_data)
- `tool_vendors`: 按工具覆盖数据源（优先级高于 data_vendors）
- `max_debate_rounds`: 研究员辩论轮数
- `max_risk_discuss_rounds`: 风险管理辩论轮数
- `output_language`: 输出语言（"English" | "中文"）

### Orchestrator 配置 (`orchestrator/config.py`)

- `quant_backtest_path`: 量化回测输出目录（必须设置才能使用 quant 信号）
- `trading_agents_config`: 传递给 TradingAgentsGraph 的配置
- `quant_weight_cap` / `llm_weight_cap`: 信号置信度上限
- `llm_batch_days`: LLM 运行间隔天数
- `cache_dir`: LLM 信号缓存目录
- `llm_solo_penalty` / `quant_solo_penalty`: 单轨运行时的置信度折扣

### A股特定配置

- **数据源**: yfinance (akshare 财务 API 已损坏)
- **股票代码格式**: `300750.SZ` (深圳), `603259.SS` (上海), `688256.SS` (科创板)
- **MiniMax API**: Anthropic 兼容，Base URL: `https://api.minimaxi.com/anthropic`
- **本地默认模型**: `MiniMax-M2.7-highspeed`

## 数据流向

```
1. 工具调用 (agents/utils/*_tools.py)
   ↓
2. 路由层 (dataflows/interface.py)
   - 根据 config["data_vendors"] 和 config["tool_vendors"] 路由
   ↓
3. 数据供应商实现
   - yfinance: y_finance.py, yfinance_news.py
   - alpha_vantage: alpha_vantage*.py
   - china_data: china_data.py (需要 akshare，当前不可用)
   ↓
4. 返回数据给智能体
```

## 重要实现细节

### LLM 客户端
- `llm_clients/base_client.py` - 统一接口
- `llm_clients/model_catalog.py` - 模型目录和验证
- 支持 provider-specific thinking 配置 (google_thinking_level, openai_reasoning_effort, anthropic_effort)

### 信号融合 (Orchestrator)
- 双轨制：quant 信号 + LLM 信号
- 降级策略：单轨失败时使用另一轨，应用 solo_penalty
- 缓存机制：LLM 信号缓存到 `cache_dir`，避免重复 API 调用
- 契约化：使用 `contracts/` 定义的结构化输出

### 测试
- `orchestrator/tests/` - Orchestrator 单元测试
- `tests/` - TradingAgents 核心测试
- 使用 pytest 运行：`python -m pytest orchestrator/tests/`

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
