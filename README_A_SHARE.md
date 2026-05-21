# TradingAgents A股分支说明

这个分支在原始 `TradingAgents` 的基础上补齐了 A 股研究与交易语境，目标不是简单把美股 ticker 换成 A 股代码，而是把 A 股真正影响决策的几类信息一起接进来：

- A 股行情、财务、公告、新闻数据源
- A 股 ticker / benchmark / 交易制度
- A 股公告事件化与公司行为压力
- A 股资金面、北向、融资融券、龙虎榜
- A 股板块轮动、板块强弱、同行对比、相对强弱
- A 股政策 / 监管语境、涨跌停情绪

这份 README 只描述当前 A 股分支的新增能力与使用方式。

## 适用范围

当前分支主要面向：

- 沪市 A 股：如 `600519.SH`
- 深市 A 股：如 `000001.SZ`、`002624.SZ`
- 北交所：如 `430047.BJ`

CLI 里也支持直接输入 6 位代码，程序会尽量自动规范化为带交易所后缀的 A 股 ticker。

## 主要新增能力

### 1. A 股数据链路

新增 `akshare` 作为 A 股主数据源，覆盖：

- 日线行情
- 技术指标
- 公司基本面
- 资产负债表 / 现金流量表 / 利润表
- 个股新闻与市场快讯
- 公司公告

核心实现位于：

- [tradingagents/dataflows/a_share.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/dataflows/a_share.py)
- [tradingagents/dataflows/a_share_common.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/dataflows/a_share_common.py)
- [tradingagents/dataflows/interface.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/dataflows/interface.py)

### 2. A 股 ticker 与 benchmark 适配

已经补齐：

- `600519 -> 600519.SH`
- `000001 -> 000001.SZ`
- `430047 -> 430047.BJ`

并且为 A 股加入了基准映射，默认会优先走沪深 300 相关 benchmark，而不是继续沿用美股 `SPY` 语境。

### 3. A 股新闻与公告分析

相对原始仓库，这个分支把 A 股更重要的信息源接进来了：

- `get_company_announcements`
- `get_company_event_signals`
- `get_corporate_action_pressure_context`
- `get_policy_signal_context`
- `get_caixin_news`

其中 `get_company_event_signals` 会把公告结构化成常见事件标签，例如：

- `shareholder_change`
- `buyback`
- `lockup`
- `earnings_preview`
- `financing`
- `risk_warning`
- `contract_order`
- `suspension`

并给出粗粒度倾向：

- `positive`
- `negative`
- `mixed`
- `neutral`

### 4. A 股资金面与市场活动

已经补齐的 A 股资金面工具包括：

- `get_market_activity`
- `get_capital_flow_regime_context`
- `get_limit_move_sentiment_context`

这几类信号会尽量整合：

- 个股主力资金
- 北向持股变化
- 融资融券
- 涨停 / 跌停情绪

区别于原始项目只给原始表格，这个分支还会尽量生成趋势判断，例如：

- 资金流是在强化还是减弱
- 北向是在持续累积还是持续流出
- 当前市场是偏热、偏冷还是分化

### 5. 板块轮动与相对强弱

已经补齐的 A 股相对强弱与板块语境包括：

- `get_sector_rotation_context`
- `get_sector_strength_snapshot`
- `get_relative_strength_context`
- `get_peer_comparison_context`

这些工具回答的是：

- 这只票属于什么行业 / 概念
- 当前板块是不是主线
- 这只票相对沪深 300 是强还是弱
- 这只票相对同行样本是强还是弱

### 6. 龙虎榜与席位画像

新增两层龙虎榜语境：

- `get_unusual_trading_activity`
- `get_lhb_seat_profile_context`

前者更偏“有没有上榜、净买额、上榜原因、最近统计”，后者更偏“谁在买、谁在卖、机构席位多不多、席位集中不集中”。

这对区分下面几类情况很有帮助：

- 基本面驱动
- 短线游资推动
- 机构参与确认
- 少数席位主导的拥挤交易

### 7. A 股交易制度与风险语境

当前分支已经把以下 A 股规则接进分析与决策链路：

- T+1
- 主板 / 创业板 / 科创板 / 北交所差异
- ST / *ST 风险
- 涨跌幅限制
- 停牌 / 风险提示 / 供给压力

相关能力包括：

- `get_trading_constraint_context`
- agent prompt 中的 A 股规则约束

## 已接入的 A 股专用工具

当前分支新增或强化的 A 股工具主要有：

- `get_company_announcements`
- `get_company_event_signals`
- `get_market_activity`
- `get_sector_rotation_context`
- `get_sector_strength_snapshot`
- `get_relative_strength_context`
- `get_trading_constraint_context`
- `get_limit_move_sentiment_context`
- `get_policy_signal_context`
- `get_peer_comparison_context`
- `get_corporate_action_pressure_context`
- `get_unusual_trading_activity`
- `get_lhb_seat_profile_context`
- `get_capital_flow_regime_context`
- `get_decision_signal_summary`
- `get_xueqiu_sentiment`
- `get_caixin_news`

## 已适配的 agent

当前分支已经把 A 股能力接到了这些 agent：

- Market Analyst
- Sentiment Analyst
- News Analyst
- Fundamentals Analyst
- Trader
- Researcher / Risk / Portfolio Manager 的 A 股制度语境

其中：

- `Market Analyst` 更关注技术面、板块、相对强弱、资金面、交易约束
- `Sentiment Analyst` 更关注新闻、雪球、财新、龙虎榜、席位画像
- `News Analyst` 更关注公告、政策、监管、市场快讯、异动语境
- `Fundamentals Analyst` 更关注财务、公告、公司行为压力、事件摘要

## 使用方式

### 1. 安装依赖

建议在虚拟环境中安装：

```bash
uv sync
```

如果你已经有 `.venv`，也可以：

```bash
source .venv/bin/activate
uv pip install -e .
```

如果本地使用了 SOCKS 代理，注意确保 `httpx[socks]` 可用。

### 2. 启动 CLI

```bash
tradingagents
```

或者：

```bash
python -m cli.main
```

### 3. 选择 A 股 ticker

推荐直接输入：

- `002624.SZ`
- `600519.SH`
- `430047.BJ`

也可以输入 6 位代码，程序会尽量自动识别。

### 4. 确认 market region

当前分支会尽量自动识别并切换到 `cn_a`，但如果你在代码里手动构造配置，建议显式设置：

```python
config["market_region"] = "cn_a"
```

## Python 用法

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["market_region"] = "cn_a"

ta = TradingAgentsGraph(debug=True, config=config)
state, decision = ta.propagate("002624.SZ", "2026-05-19")
print(decision)
```

## 推荐配置

对于 A 股分析，建议至少关注这些配置：

```python
config["market_region"] = "cn_a"
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-5.4"
config["quick_think_llm"] = "gpt-5.4-mini"
```

如果你想更稳定地恢复中断任务，可以继续打开 checkpoint：

```python
config["checkpoint_enabled"] = True
```

## 当前已验证内容

A 股分支目前已经补了较完整的回归测试，覆盖：

- vendor 路由
- ticker / benchmark 适配
- A 股行情
- 基本面与报表
- 公告与事件回退
- 市场活动
- 板块轮动 / 板块强弱 / 相对强弱 / 同行对比
- 公司行为压力
- 龙虎榜 / 席位画像
- 交易约束
- 涨跌停情绪
- 政策语境
- 综合决策摘要

## 已知限制

当前分支虽然已经比较完整，但仍有一些限制：

- AkShare 上游接口偶尔会变动，某些字段名可能会漂移
- 不同公告接口返回结构不完全一致，所以个别日期可能会走回退链路
- A 股数据源的“当日日线是否已经落地”仍受上游数据更新时间影响
- 政策 / 监管语境目前主要来自市场快讯抽取，还不是正式政策数据库
- 龙虎榜席位画像目前更偏短线交易语境，不应替代基本面判断

## 建议的阅读顺序

如果你想理解这条 A 股分支，建议按这个顺序看代码：

1. [tradingagents/dataflows/interface.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/dataflows/interface.py)
2. [tradingagents/dataflows/a_share.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/dataflows/a_share.py)
3. [tradingagents/graph/trading_graph.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/graph/trading_graph.py)
4. [tradingagents/agents/analysts/market_analyst.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/agents/analysts/market_analyst.py)
5. [tradingagents/agents/analysts/news_analyst.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/agents/analysts/news_analyst.py)
6. [tradingagents/agents/analysts/sentiment_analyst.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/agents/analysts/sentiment_analyst.py)
7. [tradingagents/agents/analysts/fundamentals_analyst.py](/Users/madongyu/Documents/AgentCode/TradingAgents/tradingagents/agents/analysts/fundamentals_analyst.py)

## 这个分支和原始仓库的差异总结

一句话总结：

原始仓库更像“全球 / 美股默认框架”，这个分支已经把它扩成了“可直接做 A 股研究”的版本。

核心差异不只是数据源，而是下面这些一起补齐了：

- 数据源换成 A 股可用链路
- 分析语境切换到 A 股制度和事件驱动
- 资金面切换到北向 / 融资融券 / 龙虎榜
- 相对强弱切换到 A 股 benchmark / 板块 / 同行
- 新闻语境切换到公告 / 政策 / 财新 / 雪球

## 后续可继续增强的方向

如果还要继续做，优先级比较高的增强项有：

- 政策主题到行业映射
- 公告事件的细粒度打分
- 北向 / 融资融券更长窗口的 regime 记忆
- 更细的席位画像标签
- 行业基准和多基准 alpha 对比

