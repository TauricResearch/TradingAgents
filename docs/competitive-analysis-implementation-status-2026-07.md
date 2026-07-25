# 竞品优化实施状态（2026-07-23）

本表是 [竞品分析与改进路线](competitive-analysis-2026-07.md) 的实施状态，代码和
测试是事实来源。它不替代原路线图，也不把尚未实现的建议写成现役能力。

## 已验证的完成切片

- **A 数据路由**：`VendorHealthRegistry` 已按 vendor、市场和能力记录冷却；429
  冷却 60 秒，网络/5xx 冷却 20 秒。`route_to_vendor()` 会跳过冷却源并继续 fallback，
  且将跳过写入 provenance。A 股标的**跳过 yfinance**（需 VPN、覆盖差）—`_should_skip_vendor_for_symbol`
  同时处理 A 股跳过 yfinance 和非 A 股跳过 tushare/akshare。冷却中 vendor 返回
  NO_DATA_AVAILABLE sentinel 而非 raise（`last_no_data` synthetic），防止 halt-on-missing 方法阻
  断分析。
- **B 分析师 preset**：`tradingagents/presets.py` 安全加载 YAML，支持内置 preset 与
  `~/.tradingagents/presets/` 覆盖；前端选择会真实改变分析师启停和顺序。除四个
  分析师外的九个角色固定执行，保证完整结论。
- **C 组合约束**：`PortfolioContext`、`compute_allowed_actions()` 与 `ClampEvent`
  在 PM 前限制下单方向和数量；Web API/快照/续跑指纹/前端输入使用同一契约。没有
  组合上下文时系统只允许 `hold`，不会假造可执行仓位。
- **A 股财务报表 Sina 回退**：`get_fundamentals_akshare` 改用 Sina `stock_financial_abstract`
  为主源（东财 `stock_individual_info_em`/`stock_zh_a_spot_em` 被反爬封锁—
  akfamily/akshare #7101/#7103/#6148）。新增 `get_balance_sheet_akshare`、
  `get_cashflow_akshare`、`get_income_statement_akshare`，均通过
  `stock_financial_report_sina` 获取新浪财报，注册到 `VENDOR_METHODS`。
- **G 上下文压缩**：`microcompact_tool_messages` 移除旧 ToolMessage 时同步移除拥有
  其 `tool_calls` 的 AIMessage，防止 DeepSeek/OpenAI 400（孤立的 tool_calls 无配对
  ToolMessage）。跨轮次不拆分—若 AIMessage 的工具调用跨保留剪切线，整个轮次一起移除。
- **H 的 SSE 基础**：前端有持久事件回放、序列去重、断开后带游标重连；已构建到
  `tradingagents/web/static/`。逐 worker 状态表渲染 13 个角色及实时状态/工具/耗时/轮次。
  K 线 Canvas 粒子半径编码最近 bar 的 |涨跌幅|。

## 路线图逐项状态

| 项 | 状态 | 已交付 | 仍待完成 |
|---|---|---|---|
| A A 股数据层 | partial | vendor 健康冷却、类型化不可用错误、A 股 yfinance 跳过、冷却 sentinel、A 股 Sina 财报回退（东财反爬） | `em_get` 统一限流、官方 HTTP 备胎、资金/筹码/互动易/iwencai/财联社层、腾讯字段、LLM 元工具、多 key 新闻健康 |
| B 声明式编排 | partial | YAML 分析师 preset、用户覆盖、`inspect_preset()`、固定下游 DAG、`ANALYST_CONFIG` 注册表 | 全图 YAML DAG、tools/skills/input 映射、timeout/retry |
| C PM 约束与审计 | partial | 合法动作集、资金/仓位/整手/费用限制、clamp 审计、前后端/恢复契约 | conviction/abstain 归一和风险聚合、实例级特征贡献 |
| D 辩论与研究 | pending | 保留 Bull/Bear+Research Manager 辩论 | 多策略共识/冲突分级、只读子 agent 并行委派 |
| E 证据账本与成本分层 | partial | Evidence Steward 评估+丰富+provenance；evidence ledger（claim/evidence/criterion+direction_score+artifact hash）；source_alignment 投影到 Bull/Bear 输入 | 三层 LLM 成本管线与缓存 |
| F 可观测与评估 | partial | 版本化持久事件、artifact/provenance、Web 回放、source_alignment_from_ledger、render_source_alignment_summary | scratchpad 事件、CycleRecord、contradiction eval |
| G 上下文压缩 | partial | microcompact 移除 ToolMessage 时同步移除所属 AIMessage（防 DeepSeek 400），跨轮次不拆分 | memory flush、摘要替换、近三轮重试 |
| H 前端可视化 | partial | 13 角色状态、时间线、Inspector、SSE 重连、逐 worker 状态表（5 列 13 行）、K 线 Canvas、粒子半径编码 | 事件粒子叠加、quadtree、框选归因、ToolProgressIndicator/ETA 进度环 |
| I Skill 引入 | partial | sentiment reality_gap 写入 methodology_reports+persist_role_report；build_role_skill_prompt/build_role_report_contract 注入基本面分析师 | skill registry、按需加载、方法论模板、A 股数据补充、结构化评分 |
| 架构重构 | pending | `health.py` 已从路由中抽出 | interface.py/web/manager.py/execution/runner.py 拆分，Protocol/分层收口 |

## 验证范围与非结论

- 2026-07-23：组合、preset、API/续跑、静态资源、vendor 路由、上下文压缩、skill 结构化
  输出相关 pytest 通过；前端 Vitest 通过；TypeScript、Ruff、生产构建和静态资源契约通过。
  Vitest **64 项通过**；TypeScript、Ruff、生产构建和静态资源契约通过。
- 这不是生产发布或实时市场数据验证：服务仍是 localhost-only，本次没有运行真实
  LLM/供应商的端到端交易分析，也没有浏览器手工验收新输入。
- 不持久化模型私有推理链。可审计内容仅为输入、输出、工具/数据 provenance、事件、
  合法动作与 clamp 结果。
