# TradingAgents 网页研究工作台优化设计

> 日期：2026-07-22  
> 状态：已与用户逐节确认，等待实现计划  
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

- 阻断：缺少必要行情，不能形成有依据的结论。
- 降级：FRED、新闻或某些补充数据不可用，但仍可完成有限分析。
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

### 7.3 多空辩论

DebateRound 以 turn_index 和 actor_id 配对：

- 第 1 轮：Bull -> Bear
- 第 2 轮：Bull -> Bear
- 依此类推
- 研究经理裁决位于所有轮次之后

候选 output_ready 与 committed 状态必须保留，但作为次要状态标签。

### 7.4 风险讨论

RiskRound 按以下顺序组织：

- Aggressive
- Conservative
- Neutral

组合经理裁决位于风险轮次之后。

### 7.5 不推断不存在的语义

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

RunSnapshot 和 run.completed 增加：

- final_report_artifact_id
- final_signal
- completed_at
- degraded_data_sources

如需要章节导航，可再提供 report_sections；第一阶段也可以从最终 Markdown 的标题生成目录，不要求后端复制正文。

现有 GET artifact 端点继续负责读取内容，不新增平行下载协议。

### 8.3 兼容性

- 新字段必须是可选字段，旧运行仍可回放。
- 对旧运行可以用 locator 精确匹配 reports/complete_report.md 作为兼容回退。
- 新运行必须写入 explicit final_report_artifact_id。
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

| 数据能力 | 首选 | 备用 | 全部失败 |
|---|---|---|---|
| 美股行情 | Yahoo Finance | Alpha Vantage | 阻断，禁止无行情继续推理 |
| 技术指标 | Yahoo Finance | Alpha Vantage 或本地行情计算 | 关键指标缺失时阻断或明确降级 |
| 基本面 | Yahoo Finance | Alpha Vantage | 允许部分分析，但必须标记证据不完整 |
| 公司新闻 | Tavily | Yahoo Finance、Alpha Vantage | 降级继续 |
| 宏观 | FRED | 暂无同等备用 | 降级继续 |
| A 股 | Tushare | AKShare、Yahoo Finance | 按覆盖率选择或组合 |

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

行为：

- 网络、超时、限流：自动尝试下一个来源。
- 未配置：跳过并记录配置缺失。
- 当前来源无数据：继续尝试其他来源。
- 股票代码无效：停止并提示用户。
- 数据不完整：尝试补充源并保留组合 provenance。

### 11.3 最低成本预检

在正式 LLM 调用前验证：

- 股票代码可解析。
- 至少一个必要行情源能返回最小行情快照。
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

只根据真实调用更新，不增加后台主动探测。网络失败或限流后设置短 TTL，避免同一次运行反复等待同一来源超时。没有延迟证据时不实现复杂熔断器。

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
