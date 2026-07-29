# TradingAgents 网页研究工作台优化设计

> 日期：2026-07-22  
> 状态：设计已确认；P0、P1 与 P2 的首个可验证切片已实施，仍待真实浏览器和关闭 VPN 验收  
> 权威范围：网页端研究阅读、数据源降级、研究流程投影、最终报告与审计回溯  
> 相关基线：docs/web-workbench-test-plan.md

## 1. 文档目的

这份文档指导后续开发者把现有 TradingAgents Web 工作台从“技术执行监控台”优化为“可阅读、可回放、可审计的股票研究工作台”。

目标不是重新设计 TradingAgents 的分析逻辑，也不是简单美化 13 个角色卡片。目标是让用户输入一只股票后，能够连续完成以下任务：

1. 阅读每位已选分析师的分析结果。
2. 看懂多空研究员和风险角色的逐轮讨论。
3. 看见研究经理与组合经理如何作出阶段裁决和最终裁决。
4. 直接阅读完整最终报告。
5. 在需要时回溯 Prompt、LLM 实际输入、上游材料、数据来源、工具调用和运行配置。
6. 在某个数据源不可用时自动切换来源，或以清晰的降级状态继续。

本文档以当前仓库和一次真实 AAPL 运行作为证据基础，明确区分“已验证事实”“设计目标”和“待实现能力”。

### 1.1 2026-07-22 实施状态（后续开发从这里开始）

已实施且有代码验证的最小闭环：

- 新 completed run 以 `final_report_artifact_id`、`completed_at` 和
  `degraded_data_sources` 明确终态；Store 拒绝缺少 canonical
  `reports/complete_report.md` 或 ID 不匹配的完成事件。
- 中间栏改为阶段式 `ResearchDocument`，只展示已选择的分析师；多空与风险
  发言严格按 `turn_index` 分轮。未 applied 的 candidate 不会作为正式结论
  读取。
- 完整报告和各分节报告使用受限、安全的 Markdown renderer。它不使用
  `dangerouslySetInnerHTML`，只接受 `http/https` 链接。由于本次明确要求
  不下载新依赖，当前实现是仓库内的白名单 renderer，而非新增第三方包。
- 右侧审计栏删除没有真实事件来源的“数据字段/原始值”一级页签，只保留
  实际持久化的上游资料、Prompt 和条件出现的配置；Prompt 会关联实际
  provider 与 model。数据来源和工具仍在独立的“数据与工具”页签。
- 右侧选择状态以 `run_id` 隔离：新建或切换历史运行时自动选择最新可审计
  阶段；运行中优先当前发言角色；同一运行中一旦用户手动选择便不再抢焦点。
- Router 将 FRED、Yahoo 等数据源的 DNS、路由、socket 和超时错误视为
  可恢复运输故障，进入已有的有序 fallback chain；终态从 durable
  `data.*` 事件汇总 `degraded`（备用源成功）或 `unavailable`（全部失败）。
  摘要只含稳定错误 code，不携带密钥或底层异常文本。

尚未实施或尚未验收的内容不能被误报为完成：最低行情预检、被动健康 TTL、
完整报告中的确定性“数据可用性”附录、响应式审计抽屉、Playwright 真浏览器
闭环，以及用户手动关闭 VPN 的真实 AAPL 运行。

## 2. 第一性原理

### 2.1 用户真正购买的是研究结论，不是 Agent 数量

13 个角色是执行结构，不是默认的信息架构。页面的首要任务是帮助用户理解一条研究推理链：

    股票输入
      -> 独立分析
      -> 证据校验
      -> 多空辩论
      -> 研究裁决
      -> 交易计划
      -> 风险讨论
      -> 组合裁决
      -> 完整报告

角色只有在这条推理链中产生了可阅读结果时才应进入主页面。

### 2.2 研究阅读与技术审计是两个层级

默认页面服务研究阅读；Prompt、原始数据、工具调用和 artifact 属于按需审计。两者必须共享同一份运行事实，但不能以同等视觉权重混在一起。

### 2.3 数据源是能力实现，不是用户任务

用户需要的是“可用的美股行情”“可用的基本面”“可用的新闻”，而不是必须使用 Yahoo Finance 或 Alpha Vantage。Vendor 选择、失败分类和切换顺序属于系统责任。

### 2.4 可追溯不等于把底层对象全部暴露出来

事件、artifact、vendor call 和 tool execution 必须保留，但页面应把它们投影为“这条结论用了什么依据”。只有高级审计视图才展示完整技术轨迹。

### 2.5 失败必须分为阻断、降级和不适用

- 阻断：ticker 无法规范化、缺少最低行情快照或所选 LLM 不可调用，不能形成有依据的结论。
- 降级：技术指标、基本面、新闻、社交情绪、FRED 或其他补充数据不可用，但仍可完成有限分析。
- 不适用：某个角色或数据类型本次没有选择，不应显示为空白 Bug。

## 3. 范围与非目标

### 3.1 本次范围

- FRED 配置与错误表达。
- AAPL 等美股在 Yahoo Finance 不可达时的数据源切换。
- 分析师结果、辩论轮次、经理裁决和最终报告的页面投影。
- Markdown 安全渲染。
- 右侧审计栏的信息架构。
- 历史运行与实时运行的一致回放。
- 自动化测试、真实网络验收和文档入口。

### 3.2 非目标

- 不修改或自动开关用户的 VPN。
- 不把网页部署为公网服务。
- 不改变现有 13 角色的核心投资研究职责。
- 不在本轮重新设计 LLM Prompt 内容本身。
- 不为视觉效果引入来源混杂的 PNG 图标包。
- 不在缺少结构化证据时推断“经理采纳或否决了某条具体观点”。
- 不因 fredapi 存在而替换当前可用的 FRED HTTP 客户端。

## 4. 当前实现与已验证证据

### 4.1 2026-07-22 本地验证

| 验证项 | 结果 | 证据或命令 |
|---|---|---|
| FRED .env 存在且格式符合当前校验 | 已验证 | 只检查存在性和 32 位小写字母数字形状，未输出密钥 |
| .env 不会被 Git 跟踪 | 已验证 | git check-ignore -v .env 命中 .gitignore |
| FRED 真实请求 | 已验证 | unemployment 指标真实请求成功 |
| AAPL 当前网络行情路由 | 已验证 | route_to_vendor(get_stock_data, AAPL, ...) 成功 |
| 前端 Vitest | 已验证 | 从 frontend 配置运行，11 个文件、61 个测试全部通过 |
| 关闭系统 VPN 的 AAPL 流程 | 待验证 | 必须由用户手动关闭 VPN 后执行 |
| 后端 pytest | 本轮未执行 | 当前 Python 环境未安装 pytest |
| 浏览器完整真实流程 | 待重新验收 | 需要正式 Playwright 入口和真实运行分别验证 |

标准前端入口应保持为：

    npm --prefix frontend test -- --run

如果当前环境没有 npm，但 frontend/node_modules 已存在，可从 frontend 目录用 Node 直接执行 Vitest。必须确保工作目录为 frontend，否则 Vitest 会绕过 jsdom 配置并产生误导性的 document is not defined 失败。

### 4.2 真实 AAPL 运行证据

最近一次已检查运行：

- 股票：AAPL
- 日期：2026-07-21
- LLM：DeepSeek
- 状态：completed
- 最终信号：Hold
- 13 个 turn 已开始并完成
- 21 个 Prompt 快照
- 19 个状态快照
- 1 个配置快照
- 24 个成功数据调用
- 5 个失败数据调用
- 216 个 artifact.written 事件
- 0 个 input.data_snapshot 事件
- 完整报告 reports/complete_report.md 存在，约 65 KB

最终报告目录已经包含：

- 四位分析师报告
- 多方、空方和研究经理报告
- 交易计划
- 三类风险报告
- 组合经理决策
- complete_report.md

因此“没有最终结果”的主要根因不是后端没有生成报告，而是前端没有把完整报告识别为一级结果并正确渲染。

### 4.3 当前五项问题的根因摘要

| 用户现象 | 当前根因 |
|---|---|
| FRED_API_KEY 报错 | 原先没有项目级配置；当前 .env 已补齐并验证成功。UI 仍需把可选源失败表达为降级，而不是原始 vendor 错误 |
| 无 VPN 时 AAPL 失败 | 已有 fallback chain，但不同数据类别、异常形态和直接 Yahoo 调用没有统一的能力级保障 |
| 没有最终结果 | 后端生成完整报告，但 run.completed 没有明确 final_report_artifact_id，前端“产物”也不是主结果视图 |
| Markdown 不可读 | SafeMarkdown 只转义后放入 pre，不解析 Markdown；ReportBody 也使用 pre |
| 看不到辩论流程 | WorkflowMap 以 13 个角色为中心；Timeline 是平铺 turn 列表，没有阶段与轮次投影 |
| 右侧大量空白 | 初始没有自动选中 turn；数据字段依赖不存在的 input.data_snapshot；存储对象被直接暴露为标签 |

## 5. 目标产品体验

### 5.1 三栏职责

#### 左侧：运行入口与历史

- 股票、日期、分析师、研究深度、Provider、模型、语言和 checkpoint。
- 历史运行记录。
- 选中历史记录后恢复完整研究卷宗和当次配置。

#### 中间：阶段式研究卷宗

顺序固定为真实图执行顺序：

1. 独立分析
2. 证据校验
3. 多空辩论
4. 研究经理裁决
5. 交易计划
6. 风险讨论
7. 组合经理裁决
8. 完整最终报告

每位分析师直接显示摘要，并允许展开完整 Markdown。多空和风险讨论按轮次排列。经理裁决单独高亮。完整最终报告是一级内容，不藏在 artifact 或“产物”标签中。

#### 右侧：本轮依据

右侧只解释当前选中内容：

- 关键数据与来源
- 数据降级和来源切换
- LLM 实际输入
- Prompt
- 原始数据与工具
- 本次配置

高级内容默认折叠并延迟加载。

### 5.2 默认选择

- 运行中自动选中当前正在发言的角色。
- 某个 turn 完成后可保持用户手动选择，不强行抢焦点。
- 运行完成且用户没有手动选择时，自动打开最终完整报告。
- 打开历史 completed 运行时直接打开最终完整报告。
- 不出现“请先选择角色”作为首屏主要内容。

`userHasSelected` 必须按 `run_id` 隔离，而不是全局布尔值：

- 新建运行或切换到另一条历史运行时重置为 `false`。
- 同一运行断点恢复时，如果原选择仍存在则保留；目标不存在时重置并选择当前阶段。
- 同一运行从 running 进入 completed 时，只有 `userHasSelected=false` 才自动打开最终报告。
- 重新打开 completed 历史运行时，默认打开最终报告，不继承上一条运行的手动选择。

### 5.3 角色识别与颜色

用户已确认图标不是重点。角色名称必须始终可见；颜色用于表达立场与团队：

- 多方：低饱和绿色背景。
- 空方：低饱和红色背景。
- 研究经理：低饱和金色背景。
- 激进风险：低饱和珊瑚色背景。
- 中性风险：低饱和蓝色背景。
- 保守风险：低饱和青绿色背景。
- 组合经理：低饱和紫色背景。

所有正文使用稳定的深色文字。颜色不能是唯一语义载体，必须同时显示角色名称、轮次和阶段。

## 6. 真实执行流程

当前 tradingagents/graph/setup.py 定义的主流程是：

1. 按 selected_analysts 的执行计划依次运行分析师。
2. 每位分析师可能在“角色 -> 工具 -> 角色”之间循环。
3. 分析师完成后进入 Evidence Steward。
4. Bull Researcher 与 Bear Researcher 交替，达到轮数后进入 Research Manager。
5. Research Manager 输出阶段裁决。
6. Trader 形成交易计划。
7. Aggressive、Conservative、Neutral 三类风险角色循环。
8. Portfolio Manager 输出最终裁决并结束。

页面投影必须遵守这一顺序。未选择的分析师不进入主研究章节，只在配置中显示“本次未选择”。

## 7. 研究视图投影层

### 7.1 边界

底层 reducer 继续保存可审计事实：

- run meta
- roles
- turns
- model calls
- tool calls
- vendor calls
- artifacts
- reports
- graph tasks

新增纯函数 projection/selector 层，将事实转换为研究页面模型。React 组件不能各自扫描原始事件并猜测业务含义。

建议接口：

    buildResearchDocument(state: ReducerState): ResearchDocument
    buildAuditBundle(state: ReducerState, selection: ResearchSelection): AuditBundle

建议领域模型：

- AnalystReport
- EvidenceGateResult
- DebateRound
- ResearchVerdict
- TradingPlan
- RiskRound
- PortfolioVerdict
- FinalReport
- AuditBundle

### 7.2 分析师章节

每个已选分析师投影为：

- actor_id
- 中文角色名
- 状态
- 摘要
- 完整报告 artifact
- 数据来源摘要
- 降级状态
- turn_id

报告正文在章节进入视口时加载；摘要和状态立即显示。

### 7.3 确定性输出映射

投影层必须使用显式映射，不能按 Markdown 标题或角色显示名猜测输出：

| actor_id | 研究阶段 | 已提交业务字段 | 对应 canonical report_kind |
|---|---|---|---|
| analyst.market | 分析师 | market_report | market |
| analyst.sentiment | 分析师 | sentiment_report | sentiment |
| analyst.news | 分析师 | news_report | news |
| analyst.fundamentals | 分析师 | fundamentals_report | fundamentals |
| evidence.steward | 证据门 | evidence_report | 无；读取 committed business delta |
| researcher.bull | 多空辩论 | investment_debate_state.current_response | 无；读取 committed business delta |
| researcher.bear | 多空辩论 | investment_debate_state.current_response | 无；读取 committed business delta |
| manager.research | 研究裁决 | investment_debate_state.judge_decision | 无；读取 committed business delta |
| trader | 交易计划 | trader_investment_plan | trader |
| risk.aggressive | 风险讨论 | risk_debate_state.current_aggressive_response | 无；读取 committed business delta |
| risk.conservative | 风险讨论 | risk_debate_state.current_conservative_response | 无；读取 committed business delta |
| risk.neutral | 风险讨论 | risk_debate_state.current_neutral_response | 无；读取 committed business delta |
| manager.portfolio | 最终裁决 | final_trade_decision | portfolio |

冲突消解规则按以下优先级执行：

1. `turn.output_ready` 只是实时候选内容；只有对应 graph task 被 applied、并产生 `turn.completed` 后才能进入已提交研究卷宗。被放弃或失败的候选不得进入最终报告。
2. 对存在 `report.updated` 的角色，使用同一 `report_kind` 的最高 revision 作为 canonical 正文；较低 revision 仍留在审计记录中。
3. 同一 `report_kind + revision` 指向不同 artifact 时属于完整性错误，页面显示诊断并拒绝任意选一个。
4. 没有 `report.updated` 的角色从已提交 business delta artifact 按上表读取，不得回退到最后一条任意模型响应。
5. 实时、刷新、历史和 resume 都按持久化 `sequence` 与 `turn_index` 排序，并以 `run_id + turn_id + sequence` 去重。
6. 中断发生在一轮中间时，保留已提交发言，并把缺少的角色显示为“本轮未完成”；不得把相邻轮次重新配对。

### 7.4 多空辩论

DebateRound 以 turn_index 和 actor_id 配对：

- 第 1 轮：Bull -> Bear
- 第 2 轮：Bull -> Bear
- 依此类推
- 研究经理裁决位于所有轮次之后

候选 output_ready 与 committed 状态必须区分；候选可以在实时界面显示“生成中”，但不能当作已完成结论。

### 7.5 风险讨论

RiskRound 与多空辩论一样按 `turn_index` 分组；每一轮内部顺序固定为：

- Aggressive
- Conservative
- Neutral

第 1 轮三位角色的 `turn_index` 都为 1，第 N 轮都为 N。中断在 Aggressive 后发生时，本轮 Conservative 和 Neutral 显示“本轮未完成”；中断在 Conservative 后发生时只为 Neutral 留缺位。resume 后继续填充原 `turn_index`，不得把下一轮角色合并到半轮中。组合经理裁决位于所有风险轮次之后。

### 7.6 不推断不存在的语义

如果现有自然语言输出没有明确观点引用，页面只能展示“综合裁决”和关联辩论轮次，不能自行标注“采纳了多方第 2 条”。

若未来需要这种关系，必须让经理输出结构化字段：

- accepted_points
- rejected_points
- remaining_uncertainties
- decision_rationale

该结构化输出属于后续能力，不是第一阶段前端推断任务。

## 8. 最终报告契约

### 8.1 问题

当前 publish_final 已原子生成完整报告树，run.completed 只携带一组 report_artifact_ids。前端无法可靠识别哪个 artifact 是 complete_report.md，只能依赖 locator 或文件名猜测。

### 8.2 目标契约

RunSnapshot 和 `run.completed` 使用同一终态契约：

    final_report_artifact_id: string | null
    final_signal: string | null
    completed_at: ISO-8601 UTC string | null
    degraded_data_sources: DegradedSourceSummary[]

    DegradedSourceSummary = {
      capability: "price_history" | "technical_indicators" |
                  "fundamentals" | "company_news" | "global_news" |
                  "social_sentiment" | "macro",
      status: "degraded" | "unavailable",
      attempted_vendors: string[],
      selected_vendors: string[],
      reasons: Array<{ vendor: string, code: VendorErrorCode }>,
      affected_sections: AffectedSectionId[]
    }

    AffectedSectionId =
      "analyst.market" | "analyst.sentiment" | "analyst.news" |
      "analyst.fundamentals" | "evidence.steward" |
      "research.debate" | "research.verdict" | "trading.plan" |
      "risk.debate" | "portfolio.verdict" | "final.report"

字段不变量：

- 对新建运行，四个字段始终存在；非 completed 状态使用 `null`、`null`、`null` 和 `[]`。
- 新运行只有在完整报告成功原子发布后才能进入 completed；此时 `final_report_artifact_id`、`final_signal`、`completed_at` 必须非空。
- `completed_at` 取成功提交 `run.completed` 的事件时间，不取文件 mtime，也不在回放时重算。
- `degraded_data_sources` 在终态发布时从 provenance 聚合，并按 capability、vendor、error code 去重；浏览器只接收错误 code，不接收可能含密钥或底层堆栈的原始异常。
- 降级摘要同时显示在最终报告旁的状态条，并由后端以确定性“数据可用性”附录写入新运行的 `complete_report.md`；它不是 LLM 自由生成内容。

降级对象只记录本次实际需要的能力；未选择、未调用的能力不进入数组。状态判定如下：

| 状态 | usable 数据 | selected_vendors | 含义 |
|---|---|---|---|
| 不产生条目 | 预期数据完整，且没有 fallback 或异常 | 非契约内容 | 正常路径无需噪声 |
| degraded | 至少一个来源返回可用数据，但发生 fallback、补充源缺失或结果不完整 | 必须至少 1 个 | 可以分析，但证据质量或覆盖率低于预期 |
| unavailable | 所有候选源都未返回可用数据 | 必须为空数组 | 对必要行情阻断；对其他能力进入确定性不可用或降级路径 |

`attempted_vendors` 按路由评估顺序记录，包含因 `not_configured` 或 `invalid_credentials` 被跳过的候选；`selected_vendors` 记录最终被采用或合并的全部来源。`affected_sections` 只能使用上面的稳定领域 ID，不能写显示标题、文件名或任意 actor 文本。

能力到直接受影响章节的映射固定如下；一旦直接分析章节受影响，还要追加所有本次实际存在的下游章节：`evidence.steward`、`research.debate`、`research.verdict`、`trading.plan`、`risk.debate`、`portfolio.verdict`、`final.report`，但不能追加未选择的分析师章节：

| capability | 直接 affected_sections |
|---|---|
| price_history | analyst.market |
| technical_indicators | analyst.market |
| fundamentals | analyst.fundamentals |
| company_news | analyst.news、analyst.sentiment |
| global_news | analyst.news |
| social_sentiment | analyst.sentiment |
| macro | analyst.news |

如需要章节导航，可再提供 report_sections；第一阶段也可以从最终 Markdown 的标题生成目录，不要求后端复制正文。

现有 GET artifact 端点继续负责读取内容，不新增平行下载协议。

### 8.3 兼容性

- API schema 为兼容旧快照允许读到缺失字段，但序列化新运行时必须显式写出上述字段。
- 旧 completed 运行缺少显式 ID 时，只能用精确 locator `reports/complete_report.md` 回退：唯一匹配才可读取。
- 回退得到 0 个匹配时显示“完整报告不可用”，并继续展示已有分节报告；不得把任意 Markdown 冒充最终报告。
- 回退得到多个匹配时显示完整性错误并拒绝猜测。
- artifact 读取失败或 hash 校验失败时，最终报告区域显示可重试错误卡；其他研究章节仍可阅读。
- 新运行在完整报告发布失败时进入 failed，错误 code 为 `report_publication_failed`，不得发送 `run.completed`。
- 生产环境读到“新 completed 运行缺少 explicit ID”时按契约违例展示错误；开发和测试环境同时令断言失败。
- 前端不得长期依赖文件名猜测作为主契约。

## 9. Markdown 渲染与安全

### 9.1 目标

统一渲染：

- 分析师报告
- 辩论发言
- 经理裁决
- 交易计划
- 风险讨论
- 最终报告

至少支持：

- 标题
- 加粗和强调
- 有序与无序列表
- 表格
- 引用
- 行内代码和代码块
- 安全外部链接

### 9.2 推荐实现

- react-markdown
- remark-gfm
- rehype-sanitize

要求：

- 禁止任意原始 HTML 执行。
- 不使用未经清洗的 dangerouslySetInnerHTML。
- 外部链接使用新窗口并设置 noopener noreferrer。
- 长报告延迟加载并 memoize。
- Markdown 渲染样式与研究正文排版共用。

现有 SafeMarkdown 的“安全转义”测试需要保留，并扩展为真正 Markdown 渲染的安全测试。

## 10. 右侧审计栏

### 10.1 现有标签处理

| 现有标签 | 目标处理 |
|---|---|
| 角色输入 | 改为“本轮依据” |
| 数据字段 | 删除独立标签 |
| 上游资料 | 合并到“LLM 输入” |
| Prompt | 保留，默认折叠 |
| 原始值 | 合并到“来源与工具” |
| 配置 | 移到运行级“本次配置” |
| 数据与工具 | 保留为高级审计 |
| 产物 | 从一级标签删除 |
| 本次输入 | 改为“本次配置” |

### 10.2 AuditBundle 数据来源

| 审计内容 | 事实来源 |
|---|---|
| Prompt | input.prompt_snapshot |
| LLM 实际输入与上游状态 | prompt snapshot + input.state_snapshot |
| 运行配置 | input.config_snapshot + RunMeta |
| 关键数据与来源 | data.completed、data.failed、tool events、provenance artifacts |
| 原始值 | normalized/raw/vendor-output artifacts |

不能继续等待不存在的 input.data_snapshot。关键数据应从已存在的数据调用与 provenance 关系投影。

### 10.3 产物的定位

artifact 有真实价值：

- 持久化阶段结果
- 历史回放
- 完整性校验
- 原始 Markdown 下载
- 崩溃恢复和审计

但 artifact 是后端存储概念，不是普通用户的一级导航。报告应出现在对应研究章节；原始文件下载放在“更多 -> 下载运行文件”。

### 10.4 空状态

- 不适用：隐藏。
- 尚未到达：显示等待状态。
- 应存在但采集失败：显示采集失败和原因。
- 没有手动选择：按默认选择规则自动选择。
- 原始大文件：显示摘要，展开后加载。

## 11. 数据源路由与无 VPN 场景

### 11.1 能力矩阵

| 数据能力 | 首选 | 备用 | 全部失败后的确定行为 |
|---|---|---|---|
| 最小行情快照 | Yahoo Finance | Alpha Vantage；A 股按覆盖率使用 Tushare、AKShare、Yahoo Finance | 全局阻断，禁止调用 LLM |
| 技术指标 | Yahoo Finance | Alpha Vantage 或用已取得行情本地计算 | 市场分析只基于行情降级继续 |
| 基本面 | Yahoo Finance | Alpha Vantage；A 股使用已配置覆盖源 | 生成确定性的“基本面数据不可用”章节，后续继续但标记证据不完整 |
| 公司新闻 | Tavily | Yahoo Finance、Alpha Vantage | 与全球新闻和宏观共同决定新闻章节是否完全 unavailable |
| 全球新闻 | Tavily | Yahoo Finance、Alpha Vantage | 与公司新闻和宏观共同决定新闻章节是否完全 unavailable |
| 社交情绪 | StockTwits、Reddit 并行聚合 | 无同等备用；公司新闻属于独立输入 | 公司新闻与社交情绪都不可用时，生成确定性的“情绪数据不可用”章节 |
| 宏观 | FRED | 暂无同等备用 | 降级继续并写入数据可用性附录 |

全局阻断条件只有三项：

1. ticker 无法规范化为受支持资产；
2. 所有候选行情源都不能提供 `MinimumMarketSnapshot`；
3. 所选 LLM 未配置或不可调用。

`MinimumMarketSnapshot` 定义为：分析日或之前、最近 10 个自然日窗口内至少 2 个不同交易日的有效日线记录。逐条记录使用同一个 predicate：

- `trading_date` 必须能解析为日期、不得晚于分析日，并在窗口内；按日期分组后每个日期最多算 1 条。组内先丢弃无效行；剩余行若 close 一致则保留 1 条，若 close 冲突则整组丢弃并记录 `malformed_response`。
- `close` 必填，必须是有限数且大于 0；仅 volume 非空不能通过闸门。
- `open`、`high`、`low`、`volume` 可缺失，因为全局闸门只保证最低价格依据；但存在时必须为有限数，前三者大于 0、volume 大于等于 0。
- `high` 存在时必须大于等于 close 以及存在的 open；`low` 存在时必须小于等于 close 以及存在的 open；high 与 low 同时存在时还必须满足 `high >= low`。任一约束不满足则该记录无效。

闸门通过只代表有最低价格依据，不代表技术指标完整。预检取得的数据必须缓存并复用于后续分析，不能为了验证再消耗一次相同 vendor 配额。

所选分析师只决定要生成哪些章节，不改变上述全局阻断边界：市场分析师在技术指标缺失时降级；基本面能力耗尽时使用确定性不可用说明；新闻分析把 `company_news`、`global_news`、`macro` 视为三类输入，三类都 unavailable 才走确定性不可用路径；情绪分析把 `company_news` 与 `social_sentiment` 视为两类输入，两类都 unavailable 才走确定性不可用路径。复合输入有任一类可用时，在明确列出其他缺失输入的前提下调用 LLM。不能要求 LLM 猜测缺失事实。Evidence Steward、经理、Trader、风险角色和 Portfolio Manager 继续处理仍可用材料，同时收到缺失证据清单，最终结论标记为 degraded。

#### 确定性不可用章节的唯一生产路径

该章节由 graph runner 与 analyst node 之间的分析编排层生成，不由 React、LLM 或最终报告拼接器临时补字。对本次已选择但所需能力全部 unavailable 的 news、fundamentals 或 sentiment analyst：

1. 正常创建该角色的 graph task 和 turn，但不产生任何 `model.started` 或模型计费。
2. 写入一份脱敏的 `UnavailableEvidence` artifact，包含 capability、错误 code、已评估来源和受影响章节。
3. 生成与 7.3 映射一致的 business delta：分别填入 `news_report`、`fundamentals_report` 或 `sentiment_report`，正文使用版本化确定性模板。
4. 正常产生 `graph.task_output_ready` 和 `turn.output_ready` 候选；只有 graph task applied/checkpoint committed 后，才产生 `turn.completed(reason=data_unavailable_deterministic)`。
5. 提交后写入对应 canonical Markdown artifact，并产生 `report.updated`；revision 规则与普通分析师一致。
6. provenance 将 canonical report 关联到 `UnavailableEvidence`，投影层因此无需特殊猜测，仍按 7.3 读取正文。

这种 turn 在流程上是 completed、在数据质量上是 unavailable；页面用降级标签表达，不能把它伪装成 LLM 分析。未选择的 analyst 仍是 not applicable，不生成 turn 或不可用章节。宏观能力没有独立 analyst turn，因此只进入 provenance、`degraded_data_sources` 和确定性数据可用性附录。

### 11.2 错误分类

路由层必须把 vendor 失败规范化为：

- network_unreachable
- timeout
- rate_limited
- not_configured
- invalid_credentials
- no_data_for_symbol
- invalid_symbol
- malformed_response
- incomplete_data
- unknown_vendor_error

每个错误的行为必须固定：

| code | 是否继续 fallback | 缓存/重试 | 候选源耗尽后的行为 |
|---|---|---|---|
| invalid_symbol | 否 | 不重试 | 输入校验失败，阻断运行 |
| network_unreachable | 是 | vendor + capability + symbol 短 TTL | 按能力矩阵阻断或降级 |
| timeout | 是 | 同上 | 按能力矩阵阻断或降级 |
| rate_limited | 是 | 记录限流 TTL，不立即重试该源 | 按能力矩阵阻断或降级 |
| not_configured | 是，直接跳过 | 进程内记配置状态 | 按能力矩阵阻断或降级，并给配置指引 |
| invalid_credentials | 是，直接跳过 | 不做瞬时重试 | 按能力矩阵阻断或降级，并给配置指引 |
| no_data_for_symbol | 是 | 只对 vendor + capability + symbol 缓存 | 按能力矩阵阻断或降级；不能仅凭单源无数据判定 ticker 无效 |
| malformed_response | 是 | 将该 vendor/capability 标记短期不健康 | 按能力矩阵阻断或降级 |
| incomplete_data | 是，并允许补充/合并 | 保留各源 provenance | 必要行情仍不足则阻断；其他能力使用部分数据降级 |
| unknown_vendor_error | 是，每个剩余源至多尝试一次 | 保留安全诊断 | 仅 vendor 边界内未知错误可降级；编程错误和非 vendor 异常必须重新抛出并令运行 failed |

普通页面只显示安全的错误摘要、已尝试来源与下一步；原始异常和调用细节只进入高级审计，并在持久化前脱敏。

### 11.3 最低成本预检

在正式 LLM 调用前验证：

- 股票代码可解析。
- 至少一个必要行情源能返回上文定义的 `MinimumMarketSnapshot`。
- 所选 LLM 已配置。
- 可选新闻与宏观源的配置状态。

预检只验证本次必要能力，不主动遍历所有 vendor，不消耗不必要配额。

### 11.4 短期健康状态

在一次进程生命周期内维护被动健康状态：

- available
- temporarily_unavailable
- rate_limited
- not_configured
- no_data_for_symbol

健康状态的键至少包含 `vendor + capability + symbol`；配置类错误可以省略 symbol。只根据真实调用更新，不增加后台主动探测。网络失败或限流后设置短 TTL，避免同一次运行反复等待同一来源超时；TTL 到期后允许下一次真实请求重新验证。没有延迟证据时不实现复杂熔断器。

### 11.5 不修改 VPN

系统不得自动检测后修改 VPN，也不得把“是否开 VPN”作为业务分支。它只根据真实请求失败分类进行 fallback。

关闭 VPN 的正式验收必须由用户手动完成，至少覆盖：

- 股票身份解析
- 行情
- 技术指标
- 基本面
- 新闻

不能只验证 get_stock_data，因为部分旁路可能直接调用 yfinance。

## 12. FRED

### 12.1 当前结论

- .env 已配置。
- 启动链会加载 .env。
- 密钥未进入 Git。
- 真实 FRED 请求成功。
- 当前 requests 实现符合 FRED Version 1 的 series 和 series/observations 契约。

本次不引入 fredapi。fredapi 的主要增量价值是 ALFRED 历史修订和“某日当时已知数据”，可作为未来研究严谨性增强。

### 12.2 UI 表达

普通用户不应看到：

    vendor fred failed for get_macro_indicators: ...

目标表达：

    宏观数据暂不可用。本次分析已在不含 FRED 数据的降级模式下继续。

高级审计中仍保留 vendor、method、错误分类和时间。

### 12.3 测试

- 正确密钥成功。
- 缺失密钥降级。
- 无效密钥归类为 invalid_credentials。
- 超时归类为 timeout。
- 429 归类为 rate_limited。
- FRED 失败不终止整个股票分析。

## 13. 历史回放与实时一致性

同一套 reducer + projection 必须服务：

- SSE 实时事件。
- 页面刷新。
- 打开历史运行。
- interrupted 后 resume。

关键不变量：

- snapshot 更新不能清空已重放 turns、artifacts、tool calls 和 vendor calls。
- terminal run 不进入重连风暴。
- 新事件按 sequence 去重。
- 旧运行缺少新字段时可以回退。
- completed 历史运行默认打开最终报告。

当前范围必须提供一个确定性 resume fixture，而不是只验证普通历史回放：

1. 构造 snapshot 与事件直到某轮中断，并包含尚未 applied 的 `output_ready` 候选。
2. 追加 resume 事件、重复重放事件和最终 committed 事件。
3. 与不中断的等价事件流比较 `ResearchDocument`。
4. 断言无重复 turn、无重复 report revision、候选内容未冒充 committed 输出、未完成轮次位置稳定。
5. 断言同一 run 的有效手动选择被保留；选择目标不存在时按 5.2 重置。

真实 checkpoint 的浏览器端断点恢复 E2E 可以在基础 fixture 通过后单列慢测试，但不能用“后续再测”替代上述投影契约测试。

## 14. 组件与模块边界

建议边界如下：

### 14.1 数据层

- 现有 vendor 实现：只负责一次来源调用。
- 路由层：错误归一化、fallback、组合 provenance。
- 预检层：验证本次最小必要能力。
- 健康状态：被动记录短期可用性。

### 14.2 Web 后端

- RunManager：运行生命周期和最终发布。
- ReportArtifactWriter：原子报告树。
- API/SSE：显式 final_report_artifact_id 和降级摘要。
- Store：持久化事实，不包含页面展示逻辑。

### 14.3 前端状态

- reducer：折叠事件为规范化事实。
- projection/selectors：构造研究卷宗和 AuditBundle。
- hooks：读取 artifact 与维护流连接。
- components：只渲染投影模型和用户交互。

### 14.4 UI 组件

- ResearchDocument
- AnalystSection
- EvidenceGateSection
- DebateSection
- ResearchVerdictSection
- TradingPlanSection
- RiskSection
- PortfolioVerdictSection
- FinalReportSection
- AuditDrawer
- MarkdownDocument

每个组件必须可以用一个小型投影 fixture 独立测试，不要求加载完整 709 事件运行。

## 15. 实施顺序

依赖闸门：P0 可以先落 `final_report_artifact_id`、终态字段形状和最终报告阅读闭环，但在 P2 的错误分类、provenance 聚合和确定性不可用章节完成前，`degraded_data_sources` 与“数据可用性”附录只能算结构占位，不能宣称达到 17 节验收。实现计划应先抽出共享的 `VendorErrorCode` 与 provenance 聚合接口，再让 P0、P2 分别消费，避免前后端出现两套降级语义。

### P0：恢复完整用户闭环

1. 增加 final_report_artifact_id 契约及旧运行回退。
2. 一级展示最终完整报告。
3. 引入安全 Markdown 渲染。
4. 默认选择当前 turn 或最终报告。
5. 移除必然为空的一级标签。

### P1：研究视图

1. 新增 ResearchDocument projection。
2. 按阶段和轮次组织内容。
3. 让实时和历史共用投影。
4. 重构右侧 AuditBundle。

### P2：数据韧性

1. 统一错误分类。
2. 检查并收敛绕过 router 的 Yahoo 调用。
3. 增加最小预检。
4. 增加被动短期健康状态。
5. 完成关闭 VPN 的真实 AAPL 验收。

### P3：体验完善

1. 长报告目录、折叠和复制。
2. 响应式审计抽屉。
3. 下载 Markdown 与运行文件。
4. 可访问性和性能优化。
5. 图标只作为辅助，不阻塞核心能力。

## 16. 测试矩阵

### 16.1 分层

| 层级 | 目标 |
|---|---|
| 前端单元 | reducer、projection、Markdown、自动选择、审计条件显示 |
| 后端单元 | 错误分类、fallback、最终报告契约、FRED 降级 |
| API/SSE 集成 | run.completed、artifact 读取、重放和历史一致性 |
| Playwright | 用户从输入到最终报告的网页闭环 |
| 真实网络 | FRED 与关闭 VPN 的 AAPL fallback |

### 16.2 核心场景

#### 正常 AAPL + DeepSeek

- 四位分析师。
- 阶段顺序与图一致。
- 多空和风险按轮次显示。
- 最终报告 Markdown 可读。
- Prompt、LLM 输入和配置可回溯。
- 历史重开内容一致。

#### 关闭 VPN

- 用户手动关闭 VPN。
- Yahoo 失败后 Alpha Vantage 接管必要能力。
- 页面显示切换过程。
- 不显示 Python 堆栈。
- 来源轨迹可审计。

#### 可选数据失败

- FRED 或新闻超时。
- 运行继续。
- 页面显示降级。
- 最终报告注明受影响来源。

#### 所有必要行情源失败

- LLM 调用前停止。
- 展示已尝试来源。
- 提供重试和配置指引。
- 不生成无行情依据的投资结论。

#### Markdown 安全

- 标题、列表、表格、引用和代码正确渲染。
- script、事件属性和危险 URL 不执行。
- 外部链接带安全属性。

#### 审计

- 每个 turn 的 Prompt、状态和来源正确关联。
- 不适用部分隐藏。
- 采集失败部分显示原因。
- API Key 不进入 DOM、SSE、artifact 或日志摘要。

### 16.3 可访问性

- 每条发言显示角色名称，不只依赖颜色。
- 文字背景对比度可读。
- 键盘可展开报告和审计项。
- 当前选择和阶段状态有可访问文本。

## 17. 验收标准

只有同时满足以下条件才可标记完成：

1. 用户能在网页完成一次真实股票分析。
2. 每位已选分析师的结果直接可读。
3. 辩论与风险讨论按真实顺序和轮次显示。
4. 最终完整报告作为一级内容正确渲染。
5. 打开历史运行后内容不丢失。
6. Prompt、LLM 输入、数据来源与配置可回溯。
7. FRED 失败只产生可理解的降级。
8. Yahoo 不可达时能使用已配置备用源，或在所有必要源失败时提前阻断。
9. 页面没有依赖不存在数据类型的永久空标签。
10. 密钥与危险 Markdown 不泄漏或执行。
11. 自动化测试通过。
12. 用户手动关闭 VPN 的真实 AAPL 验收通过。

## 18. 风险与约束

### 18.1 工作树已有在途改动

当前工作树包含用户已有的前端、SSE、API、脚本和静态构建改动。实现时必须逐文件检查，不得重置、覆盖或把无关改动混入提交。

### 18.2 旧运行兼容

历史运行缺少新字段。任何契约变更都必须提供回退，不能要求删除历史数据。

### 18.3 数据源差异

Yahoo Finance 与 Alpha Vantage 的字段、频率和覆盖范围不同。Fallback 成功不等于数据完全等价，必须记录来源和完整性。

### 18.4 LLM 输出不是稳定 schema

自然语言格式可能变化。重要页面关系应来自明确的 actor、turn、artifact 和结构化字段，不依赖脆弱的 Markdown 文本正则。

### 18.5 长报告

约 65 KB 的完整报告会影响首屏渲染。正文应延迟加载、分段或 memoize，但不能牺牲历史一致性。

## 19. 实现前检查清单

- 阅读本设计文档。
- 阅读 docs/web-workbench-test-plan.md 的 v0.3 路由说明与新增矩阵。
- 检查 git status，识别用户在途改动。
- 运行前端基线测试。
- 准备可运行 pytest 的隔离环境。
- 用旧运行 fixture 验证兼容。
- 为每个新契约先写红测试。
- 不在日志或测试 fixture 中写入真实 API Key。
- 不自动改变系统 VPN。

## 20. 设计决策记录

已由用户确认：

1. 页面采用“阶段式研究卷宗”。
2. 研究阅读优先，审计按需展开。
3. 角色名称与低饱和背景色是主要辨识方式。
4. 图标不是重点，只作为辅助。
5. 最终完整报告必须是一级结果。
6. Prompt、LLM 实际输入、数据来源和配置必须可回溯。
7. 空的技术标签应合并或删除。
8. 数据源不可用时优先自动切换，并保留来源轨迹。

## 21. 下一步

本设计通过审查并经用户复核后，再编写独立实现计划。实现计划必须把 P0、P1、P2、P3 拆成可测试的小步骤，不在一个提交中同时重写数据路由、事件契约和整个 UI。
