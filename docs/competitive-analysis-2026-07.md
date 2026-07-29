# 竞品分析与改进路线（2026-07）

> 对 8 个 GitHub 开源项目的分层深挖，提炼可落地补强 TradingAgents 的改进点。
> 关注维度：Agent 编排 / 辩论机制 / 结构化输出 / 可观测性 / UI 可视化 / 工程架构 / 数据源获取（回测与评估不在本次重点，因本系统定位为"产出观点"而非实时交易）。

## 1. 概述

### 1.1 方法
- **第一层浅读**：用 `gh api` 拉取 8 个仓库的 README + 元信息，建立全局定位认知。
- **第二层深挖**：派发 8 个 `Agent` subagent 并行 clone 各仓库源码，按统一模板（定位/架构/各维度发现/可借鉴点/独特创新点）产出深挖卡片（`/tmp/deep/*.card.md`）。
- **整合**：基于 8 张卡片 + TradingAgents 现状盘点，产出横向对比与落地 issue 清单。

### 1.2 TradingAgents 现状速览
| 层 | 现状 |
|---|---|
| graph/ | LangGraph 编排（setup/conditional_logic/signal_processing/propagation/reflection/checkpointer/analyst_execution） |
| agents/ | analysts/managers/researchers/risk_mgmt/trader + evidence_steward + schemas.py + utils/structured.py（Pydantic） |
| dataflows/ | china_data.py(431行) + interface.py(1211行) + alpha_vantage 系列 + fred + tavily_news + credibility + consistency + market_data_validator + news_advisor + symbol_utils |
| observability/ | events/observer/projections/roles/lifecycle/provenance/redaction/canonical/context/graph_tasks |
| web/ + execution/ | api/broker/manager/store + runner（loopback-only SPA + SSE） |
| frontend/ | React+TS+Vite，9 个组件目录（controls/history/inspector/layout/timeline/workflow/tools/shared/icons） |

**核心特点**：bull↔bear 多轮辩论 + Research Manager 裁判、A 股 3-tier 身份解析、Evidence Steward、Tavily 新闻、loopback web workbench。
**主要短板**：A 股数据层薄（仅 OHLCV+基本面+三表，SDK 封装，无 HTTP 直连防封/无限流）、13 角色硬编码、缺端到端决策质量 eval、缺成本分层、上下文管理粗。

### 1.3 8 个项目一句话定位
| 仓库 | ⭐ | 定位 | 与 TradingAgents 关系 |
|---|---|---|---|
| virattt/ai-hedge-fund | 6.2万 | 19 agent 并行投票->PM 汇总的教育性对冲基金模拟 | agent 编排 + 结构化输出最直接可比 |
| virattt/dexter | 2.7万 | "Claude Code for 金融研究"，单 agent + 子 agent 委派 | 架构互补，eval/可观测性/压缩可借鉴 |
| HKUDS/Vibe-Trading | 2.6万 | YAML DAG preset 的个人交易 agent（MCP） | 同范式（辩论->决策），preset 化最值得学 |
| ZhuLinsen/daily_stock_analysis | 5.8万 | 多市场每日分析 + 14 渠道推送 + 15 YAML 策略 | 数据源 fallback/策略模板/推送可借鉴 |
| simonlin1212/a-stock-data | 7607 | A 股 Skill 文件（10 层 43 端点 15 数据源） | **最直接补强 dataflows/china_data.py** |
| owengetinfo-design/PokieTicker | 784 | K 线新闻标注 + 三层 LLM pipeline + 事件归因 | 成本分层 + 可视化 + 反思链路可借鉴 |
| Open-Dev-Society/OpenStock | 1.4万 | Next.js 消费级行情应用（TradingView+Finnhub） | 前端工程模式参考（非业务模式） |
| HKUDS/AI-Trader | 2.1万 | Agent-native 社交/跟单/竞赛平台 | 正交，借鉴平台/协议层（SKILL.md/实验框架） |

---

## 2. 七维度横向对比

| 维度 | ai-hedge-fund | dexter | Vibe-Trading | daily_stock_analysis | a-stock-data | PokieTicker | OpenStock | AI-Trader |
|---|---|---|---|---|---|---|---|---|
| **Agent 编排** | 19 agent 并行扇出+PM 单点汇总（LangGraph 共享 dict，无并行原语） | 单 agent loop + 子 agent 委派；maxIter=10；Jaccard loop 检测 | YAML DAG 拓扑分层（层内并行/层间串行）+依赖门控+手写 ReAct | 15 YAML 策略包 + SkillRouter 市场状态路由 + StrategyEngine 多技能共识 | N/A（Skill 非 agent） | N/A（事件归因） | N/A（消费级行情） | 3 信号类型 + SAVEPOINT 隔离跟单 |
| **辩论机制** | **无**（DCF bear/base/bull 是情景非对抗） | 无（自反思 compact） | bull/bear->risk->PM（与 TradingAgents 同构） | 多策略加权 + disagreement 冲突分级 | N/A | N/A | N/A | 社区投票（accept/reject/revise） |
| **结构化输出** | Pydantic Signal(bullish/bearish/neutral+confidence)；PM `compute_allowed_actions` 确定性预算 | Zod schema；元工具两段式规划 | Research Goal ledger（claim/evidence/criterion + 完整 provenance） | 决策仪表盘 payload（risk_alerts/catalysts/key_levels/strategy_synthesis） | 端点路由速查表 + 估值公式集 | 三层 LLM pipeline（Layer0 规则/Layer1 Haiku Batch 单字符压缩/Layer2 Sonnet 按需） | getSourceAlignment 跨源对齐确定性分类 | signals 表 schema + 正则抽取预测（中文看多/看空） |
| **可观测性** | AgentProgress 回调 + SSE + Postgres；v2 CycleRecord 全序列化 | Scratchpad JSONL（init/tool_result/thinking）+ 全量 typed events | 崩溃安全 JSONL + sidecar；SSE Last-Event-ID + 僵尸 reconcile | OutcomeStats + reassess 反馈闭环 | N/A | events.jsonl + Layer2 缓存 | Inngest 事件/cron | 挑战赛 mark-to-market + A/B sha256 分桶 + 协作网络物化 |
| **UI 可视化** | React Flow 拖拽编辑拓扑 | Ink/React CLI | SwarmStatusCard 逐 worker 表 + ToolProgressIndicator 进度环 | DecisionSignalsPage（反馈闭环 + 结果跟踪） | N/A | K 线 Canvas 粒子层 + quadtree + d3.brushX 框选归因 | TV widget 注入 + Cmd+K + oklch 暗色 | React leaderboard/dashboard |
| **工程架构** | 13 provider 枚举 if-elif；v2 Protocol + YAML 基金契约 | Bun/TS；工具注册表 concurrencySafe；三级缓存；per-turn 200k 预算 | FastAPI 薄组装 + register 路由；providers 冻结 dataclass；MCP 双向 | GitHub Actions 零成本 cron；per-agent 超时预算；风险覆写状态机 | 单文件 127KB Skill；按需局部读取；零 akshare 直连 HTTP | FastAPI + SQLite WAL；预构建 DB | Next.js15 App Router；Better Auth 惰性单例；Server Actions cache() 分级；AI provider 主备降级 | FastAPI + worker 分离；SKILL.md 提示协议；PG/SQLite |
| **数据源** | 单一 Financial Datasets API + 磁盘缓存 | Financial Datasets + Exa/Tavily | A 股 tushare/akshare/mootdx/eastmoney 免 token | 13 fetcher circuit breaker；7 新闻 provider 多 key 轮换 | **15 源 10 层 43 端点；em_get 限流；3 官方备胎；降级速查表** | Polygon（8 次指数退避 + 429 Retry-After） | Finnhub（quote/profile/news round-robin） | Alpha Vantage->yfinance；Hyperliquid；Polymarket；Provider 冷却状态机 |

---

## 3. 单项目深挖卡片

### 3.1 ai-hedge-fund（virattt）
- **定位**：教育性 LLM 对冲基金模拟器。v1=19 投资人格局 agent 并行投票；v2（开发中）= FUND>STRATEGY>MODEL 层级，point-in-time 严格、LLM 只产 view 不碰交易。
- **架构**：`start ─┬─> [13 名人 + 6 分析师]（全并行，各写 analyst_signals dict） └─> risk_management ─> portfolio_manager ─> END`。用 LangGraph 但 analyst 间无边，靠共享 dict 扇出，非真辩论。
- **关键发现**：
  - `compute_allowed_actions`（`portfolio_manager.py:96-157`）先确定性算合法动作集+最大量，只把不可 hold 的交 LLM，纯 hold 预填--LLM 不做算术。
  - v2 `Signal.value`（`v2/models.py:14-27`）+ `blend_signals`（`v2/portfolio/construction.py:29-89`）abstain 排除分子分母（"无观点"≠"看平"）。
  - v2 `apply_limits`（`v2/risk/limits.py:49-82`）返回 `ClampEvent[]`（before/after/limit）可解释审计。
  - v2 point-in-time by construction（`v2/pipeline/run_cycle.py:134-165` 按 filing date 过滤，held 无价则 raise）。
- **独特创新**：YAML 即基金契约（新策略=丢 YAML）；Persona 即系统提示 + PromptCache（跨策略复用只付一次 LLM 费）；React Flow 可视编辑拓扑动态编译 LangGraph。

### 3.2 dexter（virattt）
- **定位**：单 agent CLI 金融研究助手（"Claude Code for finance"），TS/Bun，~26.6k LOC。非多 agent 辩论框架。
- **架构**：agent loop（`agent.ts:128-289`）+ 三级上下文压缩（microcompact->memory flush->compaction）+ SOUL/RULES/SKILL 三层文档。
- **关键发现**：
  - **contradiction 一票否决 eval**（`evaluator.ts:80-123`）：50 题 9 类带原子 rubric，任一 contradiction 命中 score=0；judge 与 target 模型必须不同（`options.ts:97`）。
  - **LLM 路由元工具**（`get-financials.ts:143`）：单入口让 LLM 依自然语言自选子工具并发拉取。
  - **三级上下文压缩**（`compact.ts:36-59`）：微压缩->记忆 flush->LLM 总结，含 Pending Data Needs/Next Steps 段驱动规划。
  - **Scratchpad JSONL**（`scratchpad.ts`）：init/tool_result/thinking 三类 entry，全量 typed events（tool_limit/microcompact/compaction/context_cleared 等）。
  - **子 agent 并行委派**（`spawn-subagent.ts`）：leader 单 turn 发多个 spawn，一层深防递归+只读白名单。
- **独特创新**：contradiction 一票否决（金融场景错向比漏答危险）；SOUL/RULES/SKILL 三层热加载（DCF skill 含 7 步校验如 EV 偏差<30%）；per-turn 200k 字符结果预算+落盘预览；seeded 分层可复现抽样。

### 3.3 Vibe-Trading（HKUDS）
- **定位**：个人交易智能体（FastAPI+React19+MCP），与 TradingAgents 同范式但用 YAML DAG 取代硬编码 LangGraph，自带 12 券商实盘 + Shadow Account + Alpha Zoo(462 因子) + 18 渠道消息总线。
- **关键发现**：
  - **YAML DAG preset 化**（`src/swarm/runtime.py:262` + `presets.py:286`）：`investment_committee.yaml` 即 bull/bear->risk->PM，用户覆盖内置跨升级存活；`inspect_preset`（`presets.py:171`）干跑校验。
  - **依赖门控**（`runtime.py:521`）：上游失败下游 blocked，PM 不在缺风险输入时出决策。
  - **输出契约 + 反伪造**（`worker.py:246` + `_classify_deliverable:883`）：Data Citation Discipline 每数字溯源；`incomplete`≠`failed`。
  - **Research Goal 证据账本**（`src/goal/models.py:40-162`）：claim<->evidence<->criterion 三元审计，每 evidence 带 source_provider+uri+method+artifact_hash+data_as_of+verification_status+contradicts。
  - **UI**：SwarmStatusCard 逐 worker 表 + ToolProgressIndicator 实时 ETA+SVG 进度环 + useSSE 指数退避+LRU 去重+Last-Event-ID 续传。
- **独特创新**：Shadow Account（CSV->隐式规则->回测闭环）；Alpha Zoo（462 因子+AST 纯度门+前视哨兵）；Live 安全栈（mandate+kill-switch+audit fail-closed）；5 层上下文压缩。

### 3.4 daily_stock_analysis（ZhuLinsen）
- **定位**：多市场(A/HK/美/日/韩/台+ETF)每日分析 + GitHub Actions 零成本定时 + 14 渠道推送决策仪表盘。Trendshift Python 日榜 #1。
- **关键发现**：
  - **DataFetcherManager**（`data_provider/base.py:600`）：远超线性 `route_to_vendor()`--按源按市场健康跟踪（circuit breaker `base.py:798-830`）+ 能力过滤 + 跨源字段补全 + 类型化错误（`RateLimitError`）+ 批量预取。新闻 7 provider 多 key 轮换 + 每 key 健康跟踪。
  - **15 YAML 策略包 + 状态路由**（`strategies/*.yaml` + `skills/router.py`）：零代码写策略，SkillRouter 三级选择（用户显式 > 市场状态检测 trending/volatile/sideways > fallback），StrategyEngine 多技能加权共识 + 冲突分级。
  - **决策仪表盘 payload**（`orchestrator.py:1527-1660`）：含 risk_alerts/positive_catalysts/key_levels/strategy_synthesis/disagreement_explanation；DecisionSignalsPage 带反馈闭环 + OutcomeStats + reassess。
  - **14 渠道推送**（`notification.py:256`）：ChannelDetector 自动探测 + send_to_context 上下文感知回复 + evaluate_noise_control 防刷。
  - **GitHub Actions**（`00-daily-analysis.yml`）：cron + 并发控制 + 随机抖动 + 按市场逐股交易日过滤 + artifact。
- **独特创新**：零代码 YAML 策略 + market_regimes 标签；风险覆写为一等公民状态机（转移校验）；上下文感知推送；按市场逐股交易日过滤。

### 3.5 a-stock-data（simonlin1212）⭐ 最直接补强数据层
- **定位**：A 股数据 Skill（V3.4.0），单文件 127KB Markdown+内嵌 Python，10 层 43 端点 15 数据源，全直连 HTTP（V3.0 移除 akshare）。
- **与 TradingAgents 对比**：`china_data.py` 仅 431 行，只覆盖 OHLCV+基本面+三表，源 tushare/akshare/yfinance（SDK 封装），降级靠同协议层 fallback，无 HTTP 直连备胎/无限流防封/无龙虎榜/资金流/打板/研报/公告/舆情。
- **关键发现**：
  - **`em_get()` 东财统一限流**：串行 + `EM_MIN_INTERVAL=1.0s` + 随机抖动 + Keep-Alive Session + HTTPAdapter Retry（429/5xx 退避，403 不重试）。
  - **`eastmoney_datacenter()` 统一查询**：龙虎榜/解禁/融资融券/大宗共用 base URL + reportName 参数。
  - **腾讯 88 字段实测索引**：PE_TTM=39、PB=46、总市值=44、涨停价=47、跌停价=48（网上误传 43=PB，实测 43=振幅%）。
  - **3 个官方备胎函数**：`dragon_tiger_backup()`（沪深交易所官方龙虎榜含营业部）、`fund_flow_backup()`（新浪日度资金流）、`announcements_backup()`（深市深交所+沪市东财公告+PDF），零鉴权一手权威。
  - **降级策略**：十类核心数据各一条独立备胎（不同域名/不同风控面），东财系被封时备胎不受牵连；死源黑名单（网易126/和讯/凤凰/腾讯ff_/雪球免登录）。
- **独特创新**：打板层（`limit_up_sentiment()` 炸板率/连板梯队 + `ths_limit_up_pool()` 涨停原因题材/封板成功率）；iwencai NL 语义搜索（跨研报/公告/新闻，X-Claw 鉴权）；互动易问答（投资者提问+公司回复，独家）；财联社本地签名零 key（`md5(sha1(排序query))`）；北向本地 CSV 自缓存应对 2024-08 断供；估值公式集（pe_digestion/peg）可喂 PM。

### 3.6 PokieTicker（owengetinfo-design）
- **定位**：单用户学习型工具，"K 线背后的故事"，事件归因 + 新闻驱动预测可视化（非交易代理）。
- **关键发现**：
  - **三层 LLM pipeline 成本优化**：Layer0 规则过滤免费拒 25-35%（`layer0.py:23-55`）-> Layer1 Haiku Batch 50 篇/调用 + 单字符 JSON 压缩（`layer1.py:107` r/s/e/u/d）+ 长文关键词抽取 + Batch API 再省 50%（约 $0.35/1000 篇）-> Layer2 Sonnet 仅点击触发并缓存（$0.003/篇）。
  - **新闻-交易日对齐**（`alignment.py:44-83`）：ret_t0/1/3/5/10 前向收益表。
  - **K 线新闻粒子标注**（`CandlestickChart.tsx`）：Canvas 粒子层（颜色=情绪/半径=|ret_t1|/alpha=relevance）+ quadtree 命中 + d3.brushX 框选触发归因。
  - **双路径归因**：`/range`（Sonnet）vs `/range-local`（零 LLM，`analysis.py:90-183`）。
  - **相似历史事件**（`inference.py:71-158`）：滑动窗口 cumsum 向量化余弦 + 前向收益统计；实例级特征贡献 |z|×importance（`:294-311`）。
- **独特创新**：单字符 JSON token 压缩；Canvas 粒子层+quadtree；cumsum 向量化余弦；零 LLM 双路径归因；跨 ticker 新闻 TF-IDF 相似。

### 3.7 OpenStock（Open-Dev-Society）
- **定位**：消费级行情追踪应用（AGPL-3.0），非 AI 决策代理；LLM 仅做邮件文案。取其前端工程模式。
- **关键发现**：
  - **TradingView widget 注入**（`hooks/useTradingViewWidget.tsx`）：`script.innerHTML=JSON.stringify(config)` + 通用组件 + `lib/constants.ts` 10 种 widget 工厂配置 + autosize + allowExpand。
  - **Cmd+K 面板**（`components/SearchCommand.tsx`）：cmdk + `useDebounce(300ms)` + Finnhub `/search` + 空闲热门/输入结果双态。
  - **暗色**：Tailwind v4 oklch token + `!important` 把 TV iframe 背景压成 #141414（`globals.css:391-457`）。
  - **邮件自动化**（Inngest）：注册发 `app/user.created` 携 onboarding 画像 -> AI 生成 `{{intro}}`（失败降级）+ 每周摘要 cron + 沉睡召回 + 价格提醒。
  - **跨源对齐打分**（`adanos.helpers.ts:97-111`）：`getSourceAlignment` 按 bullish% 极差+均值确定性分类（Bullish/Bearish/Tight/Wide divergence/Mixed）。
  - **工程**：Better Auth 惰性单例；Server Actions `cache()` 去重 + `fetch` revalidate 分级；AI provider 主备降级链。
- **注意**：onboarding 字段只随事件走未写入 user 模型（口径瑕疵，借鉴时需修正）；TV 免费档对 A 股等新兴市场有限，宜用于非 A 股次级场景。

### 3.8 AI-Trader（HKUDS）
- **定位**：Agent-native 社交/跟单/竞赛平台（agent 当交易员），非分析框架，与 TradingAgents 正交。借鉴平台/协议层。
- **关键发现**：
  - **SKILL.md 提示协议**（`skills/ai4trade/SKILL.md`）：稳定 URL 托管，外部 agent 拉 markdown -> selfRegister -> 拿 token（`secrets.token_urlsafe(32)`）-> 按任务路由表拉子 skill。Heartbeat 强制参与协议。
  - **3 信号类型 + SAVEPOINT 跟单**（`routes_signals.py:391-528`）：operation(realtime)/strategy/discussion；leader 发 operation 时每 follower 用 SAVEPOINT 隔离，单 follower 现金不足不阻塞。
  - **确定性信号质量分（无 LLM）**（`signal_quality.py:183-274`）：5 维正则启发式（verifiability 0.3/evidence 0.25/specificity 0.2/novelty 0.15/review 0.1）+ 从自由文本正则抽取预测（direction 含中文看多/看空）。
  - **A/B 实验框架**（`experiments.py`）：sha256 稳定分桶 + enrollment cap + **行为事件 primary / 读状态 diagnostic 因果分离**。
  - **Provider 冷却状态机**（`price_fetcher.py:89-100`）：429->60s，5xx->20s，指数退避+jitter。
- **独特创新**：agent 为一等交易用户；SAVEPOINT 隔离同步跟单；协作网络物化（8 类加权边）；确定性信号质量分（LLM-judge 透明替代）；信号市场托管（48h 自动完成+争议）。

---

## 4. 落地改进 issue 清单

> 每条含：来源 / 对位 TradingAgents 模块 / 做法 / 预期收益。按优先级 P0/P1/P2 分组。

### P0 — 高价值、直接补强核心短板（与 A 股场景强相关）

#### P0-1 A 股数据层补强：限流防封 + 跨协议备胎 + 资金面/打板/题材层
- **来源**：a-stock-data
- **对位**：`tradingagents/dataflows/china_data.py`(431行) + `interface.py`
- **做法**：
  1. 引入 `em_get()` 东财统一限流入口（串行+1s 抖动+Keep-Alive+Retry，429/5xx 退避、403 不重试）。
  2. fallback chain 增加"跨协议层"HTTP 直连备胎：`dragon_tiger_backup`（沪深交易所官方龙虎榜）、`fund_flow_backup`（新浪资金流）、`announcements_backup`（深交所+东财公告+PDF）。
  3. 用 `eastmoney_datacenter()` 统一查询新增资金面/筹码层 vendor（融资融券/大宗/股东户数/龙虎榜/解禁）。
  4. 新增打板层（`limit_up_sentiment` 炸板率/连板梯队）+ `ths_hot_reason` 题材归因，喂 Bull/Bear Researcher。
- **收益**：防 IP 封禁；fallback 从 SDK 层升级到跨协议层；补全 A 股特色数据（当前完全缺失）。

#### P0-2 YAML DAG preset 化编排（声明式阵容）
- **来源**：Vibe-Trading（`investment_committee.yaml` + `inspect_preset`）+ daily_stock_analysis（15 YAML 策略包）
- **对位**：`tradingagents/graph/setup.py`（13 角色硬编码）
- **做法**：把 Analyst->Steward->Bull/Bear->Trader->Risk->PM 抽成可声明/覆盖 YAML（tools/skills 白名单、input_from 上游摘要映射、max_iter/timeout/retries），用户不改代码自定义阵容；配套 `inspect_preset` 干跑校验（重复 ID/未知引用/未声明变量/DAG 层）。
- **收益**：策略即数据，降低迭代成本；阵容可热替换。

#### P0-3 确定性预算约束喂 Portfolio Manager
- **来源**：ai-hedge-fund（`portfolio_manager.py:96-157` `compute_allowed_actions`）
- **对位**：`tradingagents/agents/portfolio_manager.py`
- **做法**：PM 前用持仓/cash/风控硬算每个 ticker 合法动作集+最大量，只把有交易空间的交 LLM，纯 hold 直接预填--LLM 不做算术。
- **收益**：降 token、防 LLM 幻觉超仓；决策可解释。

#### P0-4 contradiction 一票否决的 eval 框架
- **来源**：dexter（`evaluator.ts:80-123`）
- **对位**：`tests/`（多为 unit/smoke，缺端到端决策质量度量）
- **做法**：建 `tests/evals/` CSV（问题/参考决策/原子 rubric），judge-LLM 按"信号一致性/仓位方向/风险披露"打分，contradiction（如看多却建议卖出）直接 0 分；judge 与 target 模型必须不同。
- **收益**：补端到端回归门；量化决策质量。

#### P0-5 Provider 冷却状态机 + 按源按市场 circuit breaker
- **来源**：AI-Trader（`price_fetcher.py:89-100`）+ daily_stock_analysis（`base.py:798-830`）
- **对位**：`tradingagents/dataflows/interface.py`（线性 `route_to_vendor()`）
- **做法**：升级为带健康跟踪（429->60s/5xx->20s 冷却）+ 能力过滤 + 类型化错误（`RateLimitError`/`DataSourceUnavailableError`）+ 跨源字段补全；新闻 provider 多 key 轮换 + 每 key 健康跟踪。
- **收益**：数据韧性大幅提升，减少宕机期冗余调用。

#### P0-6 三层 LLM 成本分层（news_advisor / evidence_steward）
- **来源**：PokieTicker（Layer0/1/2）
- **对位**：`tradingagents/dataflows/news_advisor.py` + `agents/evidence_steward.py`（当前统一 DeepSeek）
- **做法**：Layer0 免费规则过滤（拒 25-35% spam/列表文）-> Layer1 批量小模型情感（50 篇/调用 + 单字符 JSON 压缩 + Batch API）-> Layer2 按需深度模型（仅证据薄/争议时触发并缓存）。
- **收益**：新闻/证据处理成本大幅下降（参考 $0.35/1000 篇）。

### P1 — 重要、明确价值

#### P1-1 Research Goal 证据账本（provenance ledger）
- **来源**：Vibe-Trading（`goal/models.py:40-162`）
- **对位**：`tradingagents/agents/evidence_steward.py`
- **做法**：从"够不够"判定升级为 claim<->evidence<->criterion 三元审计，每条 evidence 带 source_provider+uri+method+artifact_hash+data_as_of+verification_status+contradicts。
- **收益**：可溯源、可审计、可回放。

#### P1-2 三级上下文压缩（防多轮辩论撑爆）
- **来源**：dexter（`compact.ts:36-59`）+ Vibe-Trading（5 层压缩）
- **对位**：`tradingagents/graph/`（多轮 Bull/Bear 辩论）+ `TradingMemoryLog`
- **做法**：辩论轮间引入微压缩（裁旧 ToolMessage）-> 记忆 flush（已定论事实写 MemoryLog）-> LLM 总结替换历史。
- **收益**：防上下文溢出，支持更多辩论轮次。

#### P1-3 K 线新闻粒子标注 + 框选归因（web workbench 可视化）
- **来源**：PokieTicker（`CandlestickChart.tsx` Canvas+quadtree+d3.brushX）
- **对位**：`frontend/` web workbench
- **做法**：K 线叠情绪粒子（颜色=情绪/半径=|ret|/alpha=relevance），点击触发深度分析缓存，框选触发 range-local 零 LLM 归因。
- **收益**：比纯文本 13 角色辩论更直观；价格-事件关联可视化。

#### P1-4 多技能加权共识 + 冲突检测
- **来源**：daily_stock_analysis（`StrategyEngine` + `disagreement.py`）
- **对位**：Bull/Bear debate
- **做法**：辩论之外并行跑多策略各产 signal+confidence，加权聚合 + 冲突分级（conflict_count/severity/consensus_level），disagreement 分类喂 PM。
- **收益**：决策维度更丰富，冲突显式化。

#### P1-5 实验框架（A/B 测 deep_vs_quick LLM、辩论轮数）
- **来源**：AI-Trader（`experiments.py` sha256 稳定分桶 + 行为指标 primary）
- **对位**：新增 `tests/evals/` 或 `observability/`
- **做法**：sha256 可复现分桶 + enrollment cap + **行为事件 primary / 读状态 diagnostic 因果分离**。
- **收益**：科学评估 config 变更，避免读状态混淆因果。

#### P1-6 news_aligned 表 + 相似历史事件检索
- **来源**：PokieTicker（`alignment.py:44-83` + `inference.py:71-158`）
- **对位**：`TradingMemoryLog`（有延迟反思但缺结构化对齐）
- **做法**：news_aligned 表（ret_t0/1/3/5/10 前向收益）+ 滑动窗口特征余弦找相似历史事件，给 Evidence Steward/Researcher"历史上类似情形后续走势"能力。
- **收益**：延迟反思链路确定化；相似检索增强决策。

#### P1-7 Scratchpad JSONL + 全量 typed events
- **来源**：dexter（`scratchpad.ts` + `types.ts:103-294`）
- **对位**：`tradingagents/observability/`
- **做法**：补 tool_limit/thinking/microcompact/compaction/context_cleared 事件 + 按 query 落盘 jsonl（含 args+raw result+thinking）。
- **收益**：web workbench 可回放调试；事件粒度更细。

#### P1-8 Cmd+K 命令面板 + TradingView widget 注入
- **来源**：OpenStock
- **对位**：`frontend/`
- **做法**：cmdk + 300ms debounce 做 ticker 切换/运行历史检索/快速动作；TV widget 注入（A 股 TV 免费档受限，用于非 A 股次级场景）。
- **收益**：交互效率 + 图表锚定辩论。

### P2 — 锦上添花、中长期

#### P2-1 腾讯 88 字段实测索引给 market_data_validator 做 ground truth
- **来源**：a-stock-data（PE_TTM=39/PB=46/涨停价=47）
- **对位**：`tradingagents/dataflows/market_data_validator.py`
- **做法**：用腾讯字段做 PE/PB/涨跌停确定性校验，止 LLM 编造价格/指标。

#### P2-2 iwencai NL 语义搜索 + 财联社本地签名零 key
- **来源**：a-stock-data
- **对位**：`tradingagents/dataflows/tavily_news.py`（A 股研报语境）
- **做法**：iwencai 跨研报/公告/新闻语义检索（比 Tavily 关键词更适合 A 股）；`cls_telegraph` 本地签名零 key 电报源与东财互备。

#### P2-3 SKILL.md bootstrap 协议（web workbench 被外部 agent 编程驱动）
- **来源**：AI-Trader
- **对位**：`tradingagents/web/`
- **做法**：暴露稳定 URL 的 SKILL.md，描述分析 API + SSE 流 + 任务路由表（intent->子 skill），让外部 agent（Claude Code/Cursor）编程驱动分析；补充 Heartbeat 任务拉取协议（对不稳定连接更鲁棒）。

#### P2-4 GitHub Actions 零成本定时 + 14 渠道推送
- **来源**：daily_stock_analysis
- **对位**：新增 `.github/workflows/`
- **做法**：cron + 并发控制 + 随机抖动 + 按市场逐股交易日过滤 + artifact；接入 NotificationService（ChannelDetector 自动探测 + 上下文感知回复 + 防刷）。

#### P2-5 子 agent 并行委派（Research Manager 并发派独立子题）
- **来源**：dexter（`spawn-subagent.ts`）
- **对位**：`tradingagents/graph/` Researcher 节点
- **做法**：leader 单 turn 发多个 spawn_subagent 并行跑独立子题，一层深防递归 + 只读白名单防副作用，缩短 wall-clock。

#### P2-6 ANALYST_CONFIG 单一注册表 + CycleRecord 全量序列化
- **来源**：ai-hedge-fund（`analysts.py:25-201` + `v2/pipeline/models.py:36-56`）
- **对位**：`tradingagents/graph/`（13 角色分散）+ `TradingMemoryLog`
- **做法**：抽 registry dict 同时驱动 graph/CLI/UI 降耦合；一轮决策落成单一 Pydantic 记录（含 spec 快照）便于 replay。

#### P2-7 getSourceAlignment 分歧度投影
- **来源**：OpenStock（`adanos.helpers.ts:97-111`）
- **对位**：`tradingagents/observability/projections.py`
- **做法**：bullish% 极差+均值确定性分类，为 Bull/Bear + Evidence Steward 加"分歧度/对齐度"投影维度。

#### P2-8 LLM 路由元工具 + SwarmStatusCard 进度环
- **来源**：dexter（元工具）+ Vibe-Trading（SwarmStatusCard + ToolProgressIndicator）
- **对位**：`tradingagents/dataflows/interface.py` + `frontend/` Timeline
- **做法**：market/fundamentals/news 数据获取包成单入口元工具让 LLM 自选子工具并发；Timeline 借鉴逐 worker 状态表 + 实时 ETA+SVG 进度环 + Last-Event-ID 续传。

#### P2-9 Signal abstain 语义 + 风险 clamp 审计
- **来源**：ai-hedge-fund v2（`blend_signals` + `apply_limits`）
- **对位**：3-way 风险辩论 + `risk_manager`
- **做法**：Signal 归一 [-1,+1] conviction，abstain 排除分子分母（无观点≠看平）；输出 `ClampEvent[]`（before/after/limit）可解释审计。

#### P2-10 实例级特征贡献做可解释性
- **来源**：PokieTicker（`inference.py:294-311` |z|×importance）
- **对位**：Trader/PM 结构化输出
- **做法**：输出 top drivers 佐证决策（哪条新闻/技术因子驱动本次判断）。

---

## 5. 优先落地建议（路线图）

**第一波（数据底座 + 决策质量，1-2 周）**：P0-1（A 股数据层）、P0-5（circuit breaker）、P0-3（确定性预算喂 PM）、P0-4（eval 框架）。这四条直接补强最薄弱的数据层与缺位的决策质量门。

**第二波（架构灵活性 + 成本，2-3 周）**：P0-2（YAML preset）、P0-6（三层 LLM 分层）、P1-1（证据账本）、P1-2（上下文压缩）。

**第三波（可视化 + 实验性，3-4 周）**：P1-3（K 线新闻归因）、P1-5（实验框架）、P1-6（news_aligned + 相似检索）、P1-8（Cmd+K + TV widget）。

**第四波（生态 + 锦上添花）**：P1-4、P1-7、P2 全部。

---

## 附录 A：subagent 派发记录

8 个 subagent 并行深挖，卡片存放 `/tmp/deep/*.card.md`：

| 仓库 | clone 路径 | 卡片 |
|---|---|---|
| ai-hedge-fund | /tmp/deep/ai-hedge-fund | /tmp/deep/ai-hedge-fund.card.md |
| dexter | /tmp/deep/dexter | /tmp/deep/dexter.card.md |
| Vibe-Trading | /tmp/deep/vibe-trading | /tmp/deep/vibe-trading.card.md |
| daily_stock_analysis | /tmp/deep/daily_stock_analysis | /tmp/deep/daily_stock_analysis.card.md |
| a-stock-data | /tmp/deep/a-stock-data | /tmp/deep/a-stock-data.card.md |
| PokieTicker | /tmp/deep/PokieTicker | /tmp/deep/PokieTicker.card.md |
| OpenStock | /tmp/deep/OpenStock | /tmp/deep/OpenStock.card.md |
| AI-Trader | /tmp/deep/AI-Trader | /tmp/deep/AI-Trader.card.md |

## 附录 B：维度归属速查（谁的哪点最值得学）

| 维度 | 最佳来源 | 核心点 |
|---|---|---|
| Agent 编排 | Vibe-Trading + daily_stock_analysis | YAML DAG preset + 市场状态路由 |
| 辩论机制 | TradingAgents 自身最强 | bull↔bear 多轮 + 裁判（保持，补多策略共识） |
| 结构化输出 | ai-hedge-fund + PokieTicker | 确定性预算喂 LLM + 三层成本分层 |
| 可观测性 | dexter + AI-Trader | Scratchpad JSONL + A/B 行为指标因果分离 |
| UI 可视化 | PokieTicker + OpenStock | K 线新闻粒子归因 + Cmd+K/TV widget |
| 工程架构 | Vibe-Trading + daily_stock_analysis | YAML 契约 + GitHub Actions 零成本定时 |
| 数据源获取 | a-stock-data | 15 源直连 HTTP + 限流防封 + 跨协议备胎 |
