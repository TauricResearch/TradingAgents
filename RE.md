# 新功能需求文档 (RE)

> 本文件是 **需求工程** 课程的需求规格说明。基于对 TradingAgents 框架现有实现的深入分析（图编排、辩论循环、数据工具、决策日志、报告树等），识别出当前版本的真实痛点，并运用需求工程方法（奥斯本方法 Osborn's method、目标-问题-度量 GQM、MoSCoW 优先级）产出以下增量需求。
>
> 需求均允许对现有功能做必要的清理/修改/删减，但强调模块化、纯函数、向后兼容与可独立测试。

## 0. 现状痛点分析（需求来源）

通过通读代码确认了以下真实问题：

| 痛点编号 | 描述 | 涉及代码 |
|---------|------|---------|
| P1 | **单标的分析速度慢、Token 消耗巨大**。流水线包含 4 个分析师 + 多空/风险多轮辩论 + 交易员 + 组合经理，每轮都把完整 `history` 全文注入 prompt（`bull_researcher.py:44`、`research_manager.py:43`），历史无上限增长，重复的 `instrument_context` 被每个 agent 重复拼接。 | `bull/bear_researcher.py`、`research_manager.py`、`agent_utils.py` |
| P2 | **子智能体对话过于松散随意**。辩论 prompt 仅用"对你的观点进行批判性分析、动态辩论"等开放措辞，缺少明确的论证结构、粒度、证据引用格式，模型易跑题、重复、堆砌数据而非真正交锋。 | `bull/bear_researcher.py` 的 prompt |
| P3 | **信号到仓位的映射缺失**。最终输出只有 5 档评级字符串，没有可执行的仓位/风险评估，`process_signal` 只是文本解析。 | `signal_processing.py`、`rating.py` |
| P4 | **历史反思逻辑依赖持有期常量**（5 天），且收益计算忽略交易成本，回测失真。 | `trading_graph.py:273` 的 `_fetch_returns` |
| P5 | **无成本/Token 追踪**，用户对一次 run 的 LLM 花费无感知。 | `llm_clients/`、`trading_graph.py` |

---

## 1. 需求列表（5 项，MoSCoW：M+）

> 以下 5 项需求均具备**实际工程意义**，且每一项都可独立开发、独立验收、独立测试。

---

### 需求 1：辩论超长历史压缩 —— 上下文窗口预算化（性能 / Token 优化，对应 P1）

**类型**：非功能需求（性能）；对既有功能的改进
**优先级**：Must

**问题**
`investment_debate_state["history"]` 是全文拼接的，随辩论轮数线性增长，并在每一轮被完整注入 prompt（bull/bear 每轮、research_manager 最终），导致：
- Token 消耗随轮数爆炸式增长（`max_debate_rounds` 默认 1，但 Deep 档为 5，每轮两个 agent 各带完整历史）。
- 长历史稀释注意力，模型在辩论末尾"遗忘"早期关键论据。

**方案要点（改造）**
- 新增 `tradingagents/graph/context_budget.py`，实现**历史压缩器**：将 `history` 转换为**有界上下文**，例如：
  - 只保留每方最近 N 条论点 + 每方首条核心立场（"首尾夹心"策略）。
  - 对超长段落做摘要（可选，`history_compress="summarize"`）或截断（`history_compress="truncate"`，默认，零 LLM 成本）。
- 由 config 控制：`debate_history_compact=True`、`history_max_chars`、`history_max_turns`、`history_compress`（枚举：`none|truncate|summarize`）。
- 修改 `bull_researcher.py` / `bear_researcher.py` / `research_manager.py`，用压缩后的 `context_budget` 替换注入的完整 `history`。
- 产生 `token_estimate` 指标（字符/4 估算），随 report 输出，量化压缩前后节省。

**可裁剪/改动**
- 删除 `max_recur_limit` 依赖的历史无界拼接逻辑；若设置 `history_compress="none"` 则保留旧行为，保证向后兼容。

**验收标准**
- 设置为 `truncate` 时，注入 prompt 的历史长度 ≤ `history_max_chars`。
- 单标的在深档（`max_debate_rounds=5`）下，估算 token 消耗相较现状显著下降（提供压缩前后对比日志）。
- 压缩不破坏 `history` 状态结构，下游 `InvestmentDebateState` 字段不变。
- 单测：`tests/test_context_budget.py` 覆盖压缩/摘要/关闭三态。

---

### 需求 2：辩论结构化 —— 基于奥斯本方法（Osborn's method）的论证增强（对应 P2）

**类型**：功能需求；对既有智能体对话机制的改进
**优先级**：Must

**问题**
当前 bull/bear 辩论 prompt 用"批判性地分析、动态地辩论"等开放措辞，无强制结构。模型会：重复引用同一批数据、变成竞品对比列表、不直接回应对方核心论点，导致"看似激烈、实则松散"的高成本对话。

**方案要点（奥斯本方法 SCAMPER + 论证规范）**
运用 Osborne 技术中的 **Substitute（替代）**、**Combine（合并）**、**Modify（调整）**、**Eliminate（消除——消除冗余论点）**、**Reverse（反向质疑自己）** 来约束论证结构，为每轮辩论加入一个**结构化论证框架**（`agents/utils/debate_skel.py`）：

1. **Substitute**：强制用"证据→推理→对对方论点的直接回应"三段式替换当前自由散文。
2. **Combine**：要求每方必须 Combine 至少一类分析师数据（技术/基本面/新闻/情绪）+ 量化引用。
3. **Eliminate**：每轮末尾要求删除/标注自己上一轮已被对方驳斥、不再成立的观点（"论点废止声明"），防止重复。
4. **Modify**：引入**立场强度自评** `stance_score ∈ [-1,1]`，随轮次可修正，供后续分歧度量化。
5. **Reverse**：每方末轮必须做一次"如果我是反面，我会如何攻击我本轮的论证"，强制反向审视。

- 实现为**约束 schema**（结构化输出），让 bull/bear 每轮输出：`key_claims[]`、`evidence_refs[]`、`refuted_points[]`、`stance_score`、`reverse_check`，而非自由长文。
- 在 `schemas.py` 增加 `DebateTurn`，在 `bull/bear_researcher.py` 用 `bind_structured` 替换现自由 invoke。

**可裁剪/改动**
- 可删除旧的"列出数据"式自由散文 prompt 段，替换为结构化约束；保留 `opponent_argument_or_opening`。

**验收标准**
- 每轮输出符合 `DebateTurn` 结构（含 stance_score、refuted_points、reverse_check）。
- prompt 文本未再出现"conversational style / dynamic debate"等开放措辞，或已由结构化约束替代。
- 单测：`tests/test_debate_skel.py` 验证 schema 字段、stance_score 边界、refuted_points 生成。

---

### 需求 3：评级 → 可执行仓位/风险映射（对应 P3）

**类型**：功能需求；新增能力
**优先级**：Should

**问题**
最终 `process_signal` 只产出字符串评级，`rating.py` 是纯文本解析。下游（真实下单、组合回放）拿不到"该买多少、止损在哪、仓位上限多少"的可执行建议，评级与仓位脱节。

**方案要点**
- 新增 `agents/utils/position.py`：静态映射表 `rating → (target_weight, risk_notes, stop_policy)`：
  - Buy → 高权重 / Overweight → 偏增 / Hold → 维持 / Underweight → 减 / Sell → 清仓。
  - 每档附带风险声明（最大单票权重、建议止损逻辑、波动阈值得出的仓位上限）。
- 扩展 `signal_processing.py`：`process_signal` 返回结构化 `PositionSignal(rating, weight, stop_loss_pct, confidence) => dataclass`，而非仅字符串。
- `trading_graph.py` 的 `propagate` 返回带仓位建议的 signal；`report_tree` 输出仓位建议区块。
- `default_config.py` 增加 `max_position_weight`、`volatility_scaling`（用已取到的历史波动计算最大仓位）。

**可裁剪/改动**
- `process_signal` 保留字符串返回值以满足兼容，同时新增 `process_position` 方法，默认用 `process_position` 的评级字段。

**验收标准**
- 每个评级能映射出明确的目标仓位权重与止损策略。
- 波动缩放生效：高波动标的自动降低建议仓位。
- 单测：`tests/test_position.py` 验证映射表与波动缩放。

---

### 需求 4：成本感知收益与可变持有期（对应 P4）

**类型**：非功能需求（正确性）；对既有功能修正
**优先级**：Should

**问题**
`_fetch_returns()` 用 `start + holding_days(固定5天)` 计算收益，且直接用 Close 相减，忽略交易成本与不同期限策略的差异，导致回测 alpha 与真实可成交结果偏差，污染 memory log 的反思学习。

**方案要点**
- `default_config.py` 增加 `holding_days_default`、`trading_cost_bps`（单边基点）、`min_commission`、`use_cost_adjusted_returns`。
- `trading_graph.py:_fetch_returns` 在收益中扣除往返成本：`net = (1+raw)*(1-cost_fee)*(1-cost_fee) - 1`，并提供 `gross_/net_` 双返回值。
- 持有期改为可配置，替代硬编码 `holding_days=5`；`TRADINGAGENTS_HOLDING_DAYS` 可从 env 覆盖。
- 反思 prompt 中同时给 gross 与 net alpha，让模型学习更接近真实的教训。

**可裁剪/改动**
- 设 `use_cost_adjusted_returns=False` 时行为与现状一致（默认保留旧逻辑避免测试破坏），或作为新开关。默认开启以体现改进。

**验收标准**
- 开启成本后，返回的 `net_return/net_alpha` 已扣除成本，且 ≤ gross。
- `holding_days` 可配置，默认值与旧值一致。
- 单测：`tests/test_cost_adjusted_returns.py` 覆盖成本扣除与关闭开关。

---

### 需求 5：LLM 消耗 / 成本仪表 + 预算熔断（对应 P5）

**类型**：非功能需求（可观测性）；新增能力
**优先级**：Should

**问题**
多 agent 流水线默认使用推理模型（`gpt-5.6`），一次分析 token 消耗大，但用户对单次 run 的用量、成本与"何时应停止"完全无感知。

**方案要点**
- 新增 `llm_clients/usage_tracker.py`：实现 `BaseCallbackHandler` 聚合每轮 LLM 调用的 `prompt/completion token`。
- `model_catalog.py` 扩展价格表（provider+model → 每百万 token 单价），估算 USD。
- 每次 run 结束写 `results_dir/costs/<ticker>_<date>.json`，并在 `complete_report.md` 顶部插入成本汇总行。
- `default_config.py` 增加 `max_run_budget_usd`（默认 None）与 `TRADINGAGENTS_RUN_BUDGET_USD` env；超限熔断：记录 `BUDGET_STOPPED` 并停止后续 agent 调用。
- 与既有 `callbacks` 参数合并，避免重复计数。

**可裁剪/改动**
- 无密钥的本地 provider（ollama）按 `0` 成本处理，不阻断。
- 若 model 无价格表项，标注 `unknown` 并跳过估算而非崩溃。

**验收标准**
- 每次 run 生成成本 JSON 与报告汇总。
- 设置预算上限后，超限触发标记 `BUDGET_STOPPED`，不再发新 LLM 请求。
- 单测：`tests/test_usage_tracker.py` 覆盖计数、估算、熔断阈值。

---

## 2. 各需求与课程方法对应

| 需求 | 需求工程方法 | 非功能性 | 可清洗/删减 |
|------|------------|:---:|:---:|
| R1 上下文预算化 | 目标-问题-度量 (GQM)、性能需求 | ✅ | 删历史无界拼接 |
| R2 辩论结构化 (Osborn) | 奥斯本方法 SCAMPER | — | 删开放措辞 prompt |
| R3 仓位映射 | 数据/接口设计、领域建模 | — | 扩展 rating 解析 |
| R4 成本感知收益 | 正确性需求、参数化 | ✅ | 修正硬编码持有期 |
| R5 成本仪表 | 可观测性需求、容量规划 | ✅ | 合并 callbacks |

## 3. 验收与实现建议

- 各需求以**独立 feature 分支**开发：`feature/context-budget`、`feature/debate-structure`、`feature/position-mapping`、`feature/cost-aware`、`feature/cost-meter`。
- 每个需求配套独立测试文件（见各需求验收标准），并跑通现有 CLI 冒烟（`tradingagents analyze --checkpoint`）。
- 涉及 token 优化与成本的需求，用 `TradingAgentsGraph` 在 `BABA` 上实测，产出前后对比日志作为度量证据（呼应 GQM）。

> 注：以上需求是增量、模块化设计，尽量复用既有组件（checkpoint、memory log、report_tree、model_catalog、binding_structured），新增部分以纯函数 / 独立模块为主，便于独立单测并保持向后兼容。