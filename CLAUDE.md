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

# SEPA筛选 + TradingAgents 完整流程
python sepa_v5.py

# 单股分析
python run_ningde.py   # 宁德时代 (300750.SZ)
python run_312.py      # 贵州茅台

# CLI 交互模式
python -m cli.main
```

## 核心架构

### 工作流程
```
SEPA筛选 (定量) → 分析师团队 → 研究员辩论 → 交易员 → 风险管理辩论 → 组合经理
```

### 关键组件 (`tradingagents/`)

| 目录 | 职责 |
|------|------|
| `agents/` | LLM智能体实现 (分析师、研究员、交易员、风控) |
| `dataflows/` | 数据源集成 (yfinance, alpha_vantage, china_data) |
| `graph/` | LangGraph 工作流编排 |
| `llm_clients/` | 多Provider LLM支持 (OpenAI, Anthropic, Google) |

### 数据流向
```
数据源 → dataflows/interface.py (路由) → 各智能体工具调用
```

## A股特定配置

- **数据源**: yfinance (akshare财务API已损坏)
- **股票代码格式**: `300750.SZ` (深圳), `603259.SS` (上海), `688256.SS` (科创板)
- **API**: MiniMax (Anthropic兼容), Base URL: `https://api.minimaxi.com/anthropic`

## 关键文件

| 文件 | 用途 |
|------|------|
| `tradingagents/graph/trading_graph.py` | 主协调器 TradingAgentsGraph |
| `tradingagents/graph/setup.py` | LangGraph 节点/边配置 |
| `dataflows/interface.py` | 数据供应商路由 |
| `sepa_v5.py` | SEPA筛选流程 |
| `default_config.py` | 默认配置 |

## 配置

默认配置在 `tradingagents/default_config.py`，运行时可覆盖：
- `llm_provider`: LLM提供商
- `deep_think_llm` / `quick_think_llm`: 模型选择
- `data_vendors`: 数据源路由
- `max_debate_rounds`: 辩论轮数

## 设计上下文 (Web Dashboard)

### 核心功能
- **股票筛选面板**: 输入股票代码，运行SEPA筛选，展示筛选结果表格
- **分析监控台**: 实时显示TradingAgents多智能体分析进度（分析师→研究员→交易员→风控）
- **历史报告查看**: 展示历史分析报告，支持搜索、筛选、导出
- **批量管理**: 批量提交股票分析任务，查看队列状态

### 界面风格
- **风格**: 数据可视化优先 - 图表驱动，实时更新
- **参考**: Grafana监控面板、彭博终端、币安交易界面
- **主题**: 深色主题为主，大量使用图表展示数据

### 设计原则
1. **实时性优先** - 所有状态变化即时反映，图表数据自动刷新
2. **数据可视化** - 数字指标用图表展示，不用纯文本堆砌
3. **清晰的状态层级** - 当前任务 > 队列任务 > 历史记录
4. **批量效率** - 支持多任务同时提交、统一管理
5. **专业金融感** - 深色主题、K线/折线图、数据表格

## 设计系统

Always read `DESIGN.md` before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
