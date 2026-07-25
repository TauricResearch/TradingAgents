# 竞品分析与改进路线（2026-07）

> 基于 8 个 GitHub 开源项目（ai-hedge-fund / dexter / Vibe-Trading / daily_stock_analysis / a-stock-data / PokieTicker / OpenStock / AI-Trader）的源码深挖，结合 TradingAgents 本地代码审查，提炼改进项与总体架构重构建议。
> 关注维度：Agent 编排 / 辩论机制 / 结构化输出 / 可观测性 / UI 可视化 / 工程架构 / 数据源获取。

> 实施状态以 2026-07-23 的代码、前端构建与测试为准，见
> [实施状态表](competitive-analysis-implementation-status-2026-07.md)。本文件保留为
> 优化路线和验收来源，不能据“均计划实现”推断所有项目已交付。

## 1. 七维度横向对比

| 维度 | ai-hedge-fund | dexter | Vibe-Trading | daily_stock_analysis | a-stock-data | PokieTicker | OpenStock | AI-Trader |
|---|---|---|---|---|---|---|---|---|
| Agent 编排 | 19 agent 并行扇出+PM 汇总（共享 dict） | 单 agent + 子 agent 委派；maxIter=10 | YAML DAG 拓扑分层+依赖门控+手写 ReAct | 15 YAML 策略+SkillRouter 状态路由+多技能共识 | N/A | N/A | N/A | 3 信号类型+SAVEPOINT 跟单 |
| 辩论机制 | 无（DCF 情景非对抗） | 无（自反思 compact） | bull/bear->PM（同构） | 多策略加权+冲突分级 | N/A | N/A | N/A | 社区投票 |
| 结构化输出 | Pydantic Signal；PM `compute_allowed_actions` 确定性预算 | Zod schema；元工具两段式 | Research Goal ledger（claim/evidence/criterion+provenance） | 决策仪表盘 payload | 端点速查表+估值公式 | 三层 LLM pipeline（单字符压缩+Batch） | getSourceAlignment 对齐分类 | signals 表+正则抽预测 |
| 可观测性 | AgentProgress+SSE+Postgres；v2 CycleRecord | Scratchpad JSONL+全量 typed events | 崩溃安全 JSONL+sidecar；SSE Last-Event-ID | OutcomeStats+reassess 闭环 | N/A | events.jsonl+Layer2 缓存 | Inngest 事件/cron | mark-to-market+A/B sha256 分桶+协作网络 |
| UI 可视化 | React Flow 拖拽编辑拓扑 | Ink CLI | SwarmStatusCard+ToolProgressIndicator 进度环 | DecisionSignalsPage 反馈闭环 | N/A | K 线 Canvas 粒子+quadtree+框选归因 | TV widget+Cmd+K+oklch 暗色 | leaderboard/dashboard |
| 工程架构 | v2 Protocol+YAML 基金契约 | Bun/TS；工具注册表；per-turn 200k 预算 | FastAPI 薄组装+register 路由；MCP 双向 | GitHub Actions 零成本 cron；风险覆写状态机 | 单文件 127KB Skill；按需读取 | FastAPI+SQLite WAL | Next.js15；Server Actions cache() 分级 | FastAPI+worker 分离；SKILL.md 协议 |
| 数据源 | 单一 Financial Datasets+磁盘缓存 | Financial Datasets+Exa/Tavily | A 股 tushare/akshare/mootdx/eastmoney | 13 fetcher circuit breaker；7 新闻多 key 轮换 | **15 源 43 端点；em_get 限流；3 官方备胎** | Polygon（指数退避+429 Retry-After） | Finnhub round-robin | Alpha Vantage->yfinance；Provider 冷却状态机 |

---

## 2. 改进项清单

> 已合并重合点，按模块组织，不分优先级（均计划实现）。每项含：本地现状 / 优化方向 / 参考上游。

### A. A 股数据层重构

**本地现状**：`china_data.py`（431 行）仅 tushare/akshare SDK 封装，只覆盖 OHLCV+基本面+三表；`interface.py` 的 `route_to_vendor()` 线性 fallback，无 circuit breaker；`market_data_validator.py` 缺 A 股字段 ground truth。

**优化方向**：
1. 引入 `em_get()` 东财统一限流入口（串行+1s 抖动+Keep-Alive+Retry，429/5xx 退避、403 不重试）；fallback chain 增加"跨协议层"HTTP 直连备胎（龙虎榜/资金流/公告走沪深交易所官方+新浪，零鉴权）。
2. 新增 A 股特色数据层：资金面/筹码（融资融券/大宗/股东户数/龙虎榜/解禁）、打板层（炸板率/连板梯队/涨停题材）、互动易问答、iwencai NL 语义搜索（跨研报/公告/新闻）、财联社电报（本地签名零 key）。
3. `route_to_vendor()` 升级为带健康跟踪的 circuit breaker（按源按市场，429->60s/5xx->20s 冷却）+ 能力过滤 + 类型化错误（`RateLimitError`/`DataSourceUnavailableError`）+ 跨源字段补全；新闻 provider 多 key 轮换 + 每 key 健康跟踪。
4. 腾讯 88 字段实测索引（PE_TTM=39/PB=46/涨停价=47）给 `market_data_validator` 做 ground truth，止 LLM 编造价格。
5. LLM 路由元工具：market/fundamentals/news 数据获取包成单入口元工具，让 LLM 依自然语言自选子工具并发拉取，减少 analyst 节点硬编码。

**参考上游**：a-stock-data（端点/限流/备胎/降级速查）、daily_stock_analysis（`DataFetcherManager` circuit breaker `base.py:798-830`）、AI-Trader（provider 冷却 `price_fetcher.py:89-100`）、dexter（元工具 `get-financials.ts:143`）

### B. 声明式编排层（YAML preset + 角色注册表）

**本地现状**：`setup.py`（205 行）硬编码 13 角色（`analyst_factories` dict + 字符串 node 名 + `should_continue_{key}` 方法名），改阵容必须改代码；角色定义分散在 `agents/` 各子目录。

**优化方向**：
1. 把 Analyst->Steward->Bull/Bear->Trader->Risk->PM 抽成可声明/覆盖 YAML（tools/skills 白名单、`input_from` 上游摘要映射、max_iter/timeout/retries），用户不改代码自定义阵容；支持 `~/.tradingagents/presets/` 用户覆盖内置、跨升级存活。
2. 配套 `inspect_preset` 干跑校验（重复 ID/未知引用/未声明变量/DAG 层级合法性）。
3. `ANALYST_CONFIG` 单一注册表（display_name/description/investing_style/factory/order）同时驱动 graph 构建、CLI 选项、API agent 列表、前端 WorkflowMap。

**参考上游**：Vibe-Trading（`investment_committee.yaml` + `presets.py:286` + `inspect_preset` `presets.py:171`）、ai-hedge-fund（`ANALYST_CONFIG` `analysts.py:25-201`）

### C. Portfolio Manager 确定性约束 + 可解释审计

**本地现状**：`portfolio_manager.py` 直接让 LLM 出 `PortfolioDecision`（rating），无合法动作集预计算，LLM 做决策但不做算术校验，无 clamp 审计。

**优化方向**：
1. `compute_allowed_actions`：PM 前用持仓/cash/风控硬算每个 ticker 合法动作集+最大量，只把有交易空间的交 LLM，纯 hold 直接预填（LLM 不做算术），降 token + 防超仓幻觉。
2. Signal 归一为 [-1,+1] conviction + abstain 语义（"无观点"≠"看平"，abstain 排除分子分母），3-way 风险辩论用此语义聚合激进/保守/中性。
3. 风险 clamp 可解释审计：输出 `ClampEvent[]`（before/after/limit），"conviction requests, risk disposes"。
4. 实例级特征贡献 |z|×importance 输出 top drivers 佐证决策（哪条新闻/技术因子驱动本次判断）。

**参考上游**：ai-hedge-fund（`compute_allowed_actions` `portfolio_manager.py:96-157` + `blend_signals` `v2/portfolio/construction.py:29-89` + `apply_limits` `v2/risk/limits.py:49-82`）、PokieTicker（特征贡献 `inference.py:294-311`）

### D. 辩论与研究增强

**本地现状**：Bull/Bear 多轮辩论 + Research Manager 裁判是你的独有优势（保留），但缺多策略共识和并行研究能力。

**优化方向**：
1. 多策略加权共识：辩论之外并行跑多个策略各产 signal+confidence，`StrategyEngine` 分区/加权/冲突分级聚合（conflict_count/severity/consensus_level），`disagreement` 分类直接喂 PM。
2. 子 agent 并行委派：Research Manager 单 turn 发多个 spawn_subagent 并行跑独立子题（如"查 X 估值"+"查 Y 行业景气"），一层深防递归 + 只读工具白名单，缩短 wall-clock。

**参考上游**：daily_stock_analysis（`StrategyEngine` `skills/engine.py` + `disagreement.py`）、dexter（`spawn-subagent.ts`）

### E. 证据账本 + 三层 LLM 成本分层

**本地现状**：`evidence_steward.py` 仅 10 行 stub（真实逻辑在 `dataflows/evidence.py` 的 `evaluate_and_enrich_evidence`），只"评估+丰富"无持久 ledger；`news_advisor`/`evidence_steward` 统一 DeepSeek，无成本分层。

**优化方向**：
1. Research Goal 证据账本：claim<->evidence<->criterion 三元审计，每条 evidence 带 source_provider+uri+method+artifact_hash+data_as_of+verification_status+contradicts；Evidence Steward 从"够不够"判定升级为可溯源持久 ledger。
2. 三层 LLM pipeline：Layer0 免费规则过滤（拒 25-35% spam/列表文）-> Layer1 批量小模型情感（50 篇/调用 + 单字符 JSON 压缩 + Batch API，~$0.35/1000 篇）-> Layer2 按需深度模型（仅证据薄/争议时触发并缓存）。

**参考上游**：Vibe-Trading（Research Goal ledger `goal/models.py:40-162`）、PokieTicker（三层 pipeline `layer0.py`/`layer1.py:107`/`layer2.py` + 单字符压缩）

### F. 可观测性 + eval 框架

**本地现状**：`observability/` 有 events/observer/projections 框架但事件粒度粗；`tests/` 多 unit/smoke，缺端到端决策质量度量；`TradingMemoryLog` 无可回放的全量记录。

**优化方向**：
1. Scratchpad JSONL + 全量 typed events：补 tool_limit/thinking/microcompact/compaction/context_cleared 事件，按 query 落盘 jsonl（含 args+raw result+thinking），便于 web workbench 回放调试。
2. CycleRecord 全量序列化：一轮决策落成单一 Pydantic 记录（含 spec 快照），便于 replay/审计。
3. getSourceAlignment 分歧度投影：bullish% 极差+均值确定性分类（Bullish/Bearish/Tight/Wide divergence/Mixed），为 Bull/Bear + Evidence Steward 加"分歧度/对齐度"投影维度。
4. contradiction 一票否决 eval 框架：建 `tests/evals/` CSV（问题/参考决策/原子 rubric），judge-LLM 按信号一致性/仓位方向/风险披露打分，contradiction（如看多却建议卖出）直接 0 分；judge 与 target 模型必须不同。

**参考上游**：dexter（scratchpad `scratchpad.ts` + contradiction eval `evaluator.ts:80-123`）、ai-hedge-fund（CycleRecord `v2/pipeline/models.py:36-56`）、OpenStock（`getSourceAlignment` `adanos.helpers.ts:97-111`）

### G. 上下文压缩（防多轮辩论撑爆）

**本地现状**：多轮 Bull/Bear 辩论易撑爆上下文，`graph/` 无压缩机制，`TradingMemoryLog` 仅延迟反思不做轮间压缩。

**优化方向**：辩论轮间引入三级压缩：微压缩（裁旧 ToolMessage）-> 记忆 flush（已定论事实写 `TradingMemoryLog`）-> LLM 总结替换历史；溢出时保留近 3 轮重试。

**参考上游**：dexter（`compact.ts:36-59` microcompact/flush/compact）、Vibe-Trading（5 层上下文压缩）

### H. 前端可视化增强

**本地现状**：`frontend/` 已分层（state/hooks/api/domain/components），有 WorkflowMap/Timeline/Inspector/VendorProvenance，但缺价格-事件关联可视化和逐 worker 实时状态。

**优化方向**：
1. K 线新闻粒子标注 + 框选归因：K 线叠情绪粒子（Canvas，颜色=情绪/半径=|ret|/alpha=relevance）+ quadtree 命中测试 + d3.brushX 框选触发归因（点击触发 Layer2 深度分析缓存/框选触发 range-local 零 LLM 归因）。
2. SwarmStatusCard 逐 worker 状态表（状态/当前工具/耗时/迭代/输出+层进度）+ ToolProgressIndicator 实时 ETA 外推+SVG 进度环；useSSE 指数退避+LRU 去重+Last-Event-ID 续传。

**参考上游**：PokieTicker（`CandlestickChart.tsx` Canvas+quadtree+d3.brushX）、Vibe-Trading（`SwarmStatusCard.tsx` + `ToolProgressIndicator.tsx` + `useSSE.ts`）

### I. LLM 分析 Skill 引入机制（专家方法论框架 + 渐进式加载）

**本地现状**：4 个 analyst 用通用自然语言 system prompt，无专业方法论框架——`fundamentals_analyst.py:25-30`"写全面基本面报告"（无杜邦/Z值/M值/法证红旗）、`news_analyst.py:25-29`"分析新闻写报告"（无 news→需求→财务→验证链）、`market_analyst.py:24-53`选 8 个技术指标（无周期定位/板块轮动/健康度评分）、`sentiment_analyst.py`偏 Reddit/StockTwits（无北向/融资余额/公募持仓等 A 股情绪指标）。Bull/Bear 通用 prompt 辩论（`bull_researcher.py:27`）缺结构化增长假设锚；PM 的 PortfolioDecision（`portfolio_manager.py:42-53`）缺买方备忘录（三情景/反向论证/催化剂）。agent 输出是自由 str，无量化评分（Z值/M值/周期概率/偏差得分）。A 股特色维度完全缺失：董监高/北向/中国宏观/事件驱动/法证红旗/板块轮动。

**优化方向**：
1. Skill 注册表 + 渐进式加载：建 `tradingagents/skills/registry.py`（name/description/适用角色/触发条件/输出 schema）+ `library/`。frontmatter（name+description）常驻 agent 上下文做触发判断，SKILL.md 正文匹配后注入 system_message，references/（methodology+output-template）按需加载。剥离 serenity 的 `agents/openai.yaml`（OpenAI Agents SDK 专用，TradingAgents 用 LangGraph 不适用）；finskills 三层架构直接复用。
2. Skill 选择器：agent 节点执行前匹配，静态映射（角色→默认 skill，配在 ANALYST_CONFIG）为主，可选 LLM 轻量匹配（看 frontmatter 选 1-3 个）。参考 finskills 自然语言耦合——分析 skill 在 SKILL.md 按名称引用工具包，LLM 自动调用。
3. 精选核心 skill 子集（按角色，覆盖数据层+方法论+A 股特色）：
   - 数据底座：findata-toolkit-cn → 移植 `fetch_insider_trades`/`fetch_northbound_flow`/`macro_data.py` 为 `dataflows/china_capital_flow.py`+`china_macro.py`，补 china_data.py 缺失的董监高/北向/中国宏观/经济周期（与 A 项协同）。
   - Fundamentals Analyst ← financial-statement-analyzer（杜邦5因子/Z值/F值/M值/营运资本/12项财务红旗+9项治理红旗，CAS 特有）+ juglar-cycle-stock-stage（朱格拉周期八维评分+五阶段概率，唯一显式 A 股支持）。
   - News Analyst ← serenity-alpha（news→已发生需求→财务翻译→小市值弹性→验证链）+ event-driven-detector（资产注入/国企改革/回购/解禁/分拆/指数调整）+ sector-rotation-detector（五支柱宏观+申万31行业轮动，补中国宏观）。
   - Social Analyst ← sentiment-reality-gap（50+50偏差评分+暂时/结构性决策树，北向资金作情绪指标）。
   - Bull/Bear Researcher ← bayesian-intrinsic-growth-valuation（H0-H5增长假设+贝叶斯更新+内在vs隐含增长）+ tam-adj-peg（TAM Runway+Quality Factor修正PEG）。
   - Portfolio Manager ← buy-side-equity-research-memo（论点先行+三情景+反向论证+催化剂+监控仪表盘）。
   - 可选二阶段：insider-trading-analyzer（董监高职务权重）、high-dividend-strategy（分红可持续性）、tech-hype-vs-fundamentals（科技估值）、portfolio-health-check（组合诊断）、suitability-report-generator（适当性文档）、gf-dma-health-index（Market 健康度评分）。
4. 输出结构化：skill 的 output-template 转成 Pydantic schema，agent 输出解析入 state（与 C 项协同）——fundamentals_report 含杜邦/Z值/M值/周期概率，news_report 含 alpha 假设+验证链+事件信号，market_report 含健康度+轮动信号。
5. 工具包整合（与 A 项协同）：findata-toolkit-cn 脚本与 china_data.py 整合（同源 AKShare 的个股基本面/行情只保留一份），skill 引用 route_to_vendor tool methods 而非自带脚本；注意数据源优先级对齐（TradingAgents tushare 主+akshare 备 vs skill akshare 主+tushare 备）。
6. 声明式配置（与 B 项协同）：ANALYST_CONFIG 声明每角色可用 skill 池，preset YAML 可覆盖。skill 主观阈值（PE中位数/散户占比）参数化进 default_config.py（单配置源）。

**参考上游**：serenity-skill（SKILL.md 格式 + 6 个研究框架：juglar/serenity-alpha/bayesian/tam-adj-peg/buy-side-memo/gf-dma + 渐进式加载 + Mermaid 规范 + 可证伪设计）、finskills（三层架构 + 自然语言耦合工具包 + China-market A 股重写 + findata-toolkit-cn AKShare 无 key + 渐进式加载）

**必要性判断**：有必要，需控制范围。①当前 analyst 是"通用 LLM + 工具调用"缺专业方法论，skill 补齐 7 大类完全缺失能力（资金面/中国宏观/事件驱动/法证财务/量化因子/组合层/ESG），直接提升分析深度与可解释性。②渐进式加载省 token，契合多 agent 长流程。③与 B/C/E 项天然协同（skill 挂 ANALYST_CONFIG，输出转 Pydantic 入 state，评分喂 PM）。④纯 prompt + 可选脚本，不破坏 LangGraph，可插拔；AKShare 无 key 契合 A 股优先 + fail-open。风险：①不全量引入，精选核心 6 类 + 二阶段可选；②findata 与 china_data.py 重叠部分必须整合（A 项），只移植缺失 4 类；③serenity 数据偏 US（SEC/edgartools），A 股需替换源（juglar 除外），一致预期/TAM 需另接 wind/choice；④output-template 需转 Pydantic（C 项）；⑤主观阈值参数化进 default_config。

---

## 3. 架构师视角：总体重构建议

> 结合上游优秀功能落地，从总体架构看 TradingAgents 的模块边界、分层、前后端契约与可扩展性。当前已加入 frontend，需让每部分设计合理、便于后续修改。

### 3.1 模块边界清理

**问题**：当前存在边界模糊与文件臃肿：
- `agents/evidence_steward.py`（10 行 stub）真实逻辑在 `dataflows/evidence.py` -- agent 节点与业务逻辑边界不清。
- `dataflows/interface.py`（1211 行）把 routing + news cache + progress + yfinance incompleteness + supplemental vendor 混在一起。
- `web/manager.py`（1242 行）把 run 生命周期 + worker + roles 初始化 + terminalization 耦合。
- `execution/runner.py`（1059 行）+ `observability/observer.py`（1125 行）同样偏重。

**建议**：
- `dataflows/` 拆分为 `routing.py`（`VENDOR_METHODS`+`route_to_vendor`）/ `health.py`（circuit breaker+provider 冷却）/ `news.py`（news 路由+dedupe+cache）/ `progress.py`（进度事件），对应 A 项重构时一并完成。
- `agents/` 只保留 agent 节点包装（prompt + structured output 绑定），业务逻辑归 `dataflows/` 或独立 `evidence/` 模块；`evidence_steward.py` 要么内联真实逻辑要么显式 re-export 并文档化。
- `web/manager.py` 拆为 `lifecycle.py`（start/cancel/retry/resume）+ `worker.py`（_worker/_launch）+ `roles.py`（_initialize_roles）。
- 拆分原则：单文件 < 500 行，单一职责。

### 3.2 分层架构明确化

确立五层边界，每层只依赖下层接口：

```
┌─ frontend/ (展示层) ─ 消费 SSE 事件，不反查后端内部状态
├─ web/ (API 层) ─ REST + SSE，薄包装，无业务逻辑
├─ observability/ (可观测层) ─ 事件 schema + scratchpad + projections（F 项）
├─ graph/ (编排层) ─ YAML preset 驱动（B 项），不含业务逻辑
├─ agents/ (决策层) ─ agent 节点 + Pydantic schemas + 确定性约束（C/D 项）
└─ dataflows/ (数据层) ─ 纯数据获取 + vendor 注册表 + circuit breaker（A 项）
```

- 编排层与决策层解耦：`graph/setup.py` 只读 preset 构建 LangGraph，agent 实现由 `ANALYST_CONFIG` 注册表提供（B 项）。
- 数据层与决策层解耦：agent 通过 `route_to_vendor` 或 LLM 路由元工具（A 项）拿数据，不直接 import 具体 vendor。
- 可观测层横切：所有层通过 observability 事件上报，前端订阅统一事件流。

### 3.3 前后端契约统一

**问题**：当前前端通过 `api/eventSource.ts` 消费 SSE，但事件 taxonomy 与 `observability/events.py` 的对齐不够显式；前端 `domain/roles.ts` 与后端 `observability/roles.py` 各自维护。

**建议**：
- 统一事件 taxonomy：参考 dexter 的全量 typed events（tool_limit/thinking/microcompact/compaction/context_cleared）+ Vibe-Trading 的 SSE taxonomy（reasoning_delta/tool_heartbeat/swarm.event），在 `observability/events.py` 定义单一事件 schema，前端 `api/contracts.ts` 从同一 schema 生成（或共享类型定义）。
- 前端通过事件驱动渲染：`state/runReducer.ts` 消费事件流更新状态，`components/` 纯展示；新增 projections reducer 消费分歧度/特征贡献等投影（F 项）。
- `domain/` 层强化：`domain/roles.ts` 扩展为 `domain/{roles,projections,decisions}.ts`，承载领域模型，让 components 无业务逻辑。

### 3.4 可扩展性设计

让"加一个数据源 / 加一个角色 / 加一个策略"都无需改核心代码：
- **数据源可插拔**：vendor 注册表（A 项），新源注册到 `VENDOR_METHODS` + 健康跟踪即接入。
- **角色可扩展**：`ANALYST_CONFIG` 注册表（B 项），新角色注册 factory + YAML preset 引用即接入。
- **策略可扩展**：策略技能包 YAML（D 项），新策略丢 YAML 即接入，`SkillRouter` 按市场状态路由。
- **事件可扩展**：observability 事件 schema 化（F 项），新事件类型注册 payload schema，前端按类型渲染。
- **Skill 可插拔**：skill 注册表（I 项），新分析方法论丢 `skills/library/` + 注册 frontmatter 即被 agent 按角色/状态匹配加载，不改核心代码。

### 3.5 前端架构演进（针对已加入 frontend）

- 当前 `frontend/` 分层（state/hooks/api/domain/components）已合理，保持。
- 强化 `domain/` 为领域模型层（roles/projections/decisions），`components/` 纯展示，`state/` 用 reducer 模式（已有 `runReducer`，扩展 projections reducer）。
- 新增 K 线可视化组件（H 项）接入 observability 的 news-aligned 事件，作为 Inspector/Timeline 的补充视图。
- `api/eventSource.ts` 增强：指数退避+LRU 去重+Last-Event-ID 续传（参考 Vibe-Trading `useSSE.ts`），提升不稳定连接鲁棒性。
- 前端不直接耦合后端内部状态，只通过 SSE 事件 + REST API 契约交互，便于后端重构时前端不受影响。

### 3.6 落地顺序建议

1. **底座重构**：A（数据层）+ 3.1 模块边界清理 -- 先把数据层和文件臃肿解决，为后续铺路。
2. **编排与决策**：B（YAML preset）+ C（PM 确定性约束）-- 架构灵活性与决策质量。
3. **可观测与成本**：F（observability+eval）+ E（证据账本+成本分层）-- 可度量与降本。
4. **增强与前端**：D（辩论增强）+ G（上下文压缩）+ H（前端可视化）—— 体验与能力扩展。
5. **Skill 引入**：I（分析 Skill 机制）—— 在 A/B/C 就绪后接入，skill 挂 ANALYST_CONFIG，数据底座依赖 A 项 findata 移植，输出结构化依赖 C 项 Pydantic，方法论评分喂 PM。

---

## 4. 上游参考速查

| 改进项 | 最佳上游参考 | 核心文件/概念 |
|---|---|---|
| A 数据层 | a-stock-data + daily_stock_analysis + AI-Trader + dexter | em_get/备胎/降级速查 + circuit breaker + provider 冷却 + 元工具 |
| B 编排 | Vibe-Trading + ai-hedge-fund | investment_committee.yaml + inspect_preset + ANALYST_CONFIG |
| C PM 约束 | ai-hedge-fund + PokieTicker | compute_allowed_actions + blend_signals + apply_limits + 特征贡献 |
| D 辩论增强 | daily_stock_analysis + dexter | StrategyEngine + disagreement + spawn-subagent |
| E 证据+成本 | Vibe-Trading + PokieTicker | Research Goal ledger + 三层 pipeline + 单字符压缩 |
| F 可观测+eval | dexter + ai-hedge-fund + OpenStock | scratchpad + contradiction eval + CycleRecord + getSourceAlignment |
| G 上下文压缩 | dexter + Vibe-Trading | compact.ts 三级压缩 + 5 层压缩 |
| H 前端可视化 | PokieTicker + Vibe-Trading | CandlestickChart Canvas+quadtree + SwarmStatusCard + useSSE |
| I Skill 引入 | serenity-skill + finskills | SKILL.md 渐进式加载 + 三层架构 + findata-toolkit-cn + 6 研究框架（juglar/alpha/bayesian 等） |
| 架构重构 | Vibe-Trading + ai-hedge-fund v2 | YAML 契约 + Protocol 抽象 + 分层 + 注册表 |

## 附录：深挖卡片位置

8 个 subagent 产出的完整深挖卡片（含全部 file:line 引用）存放 `/tmp/deep/*.card.md`，竞品 clone 在 `/tmp/deep/*/`，供后续深挖时查阅。

2 个 skill 仓库的深挖卡片存放 `/tmp/skills/serenity.card.md` + `/tmp/skills/finskills.card.md`，clone 在 `/tmp/skills/serenity-skill/` + `/tmp/skills/finskills/`，含每个 skill 的方法论步骤、输出模板、A 股特色点、角色匹配度评估与完整 file:line 引用。
