# 优化进度（Issue 驱动）

Issue 在 [kissman911/tradingagents-crypto-trader](https://github.com/kissman911/tradingagents-crypto-trader/issues)。审计报告：[audit-2026-11.md](audit-2026-11.md)。
流程：每个 Issue 一个分支（`cursor/issue-<n>-<slug>-6e50`）→ 改动 + 测试 → ruff / pytest / tsc / oxlint / build → 自审 → 合入 `crypto-trader` → 推 `backup` → 验收通过才关 Issue。
mini 上的部署（`git pull`、`launchctl kickstart`）按 roadmap 的更新流程，每次由用户授权后才做（2026-11-10 07:19 UTC 用户选“全部部署”，已部署 b228b3b）。

状态：triage 待定方案 · ready 可做 · in-progress 进行中 · blocked 阻塞 · review 待验收 · done 已关闭。

| # | 标题 | 优先级 | 状态 | 依赖 | 方案要点 | 测试/验收 | 阻塞或备注 |
|---|---|---|---|---|---|---|---|
| 1 | 日内信号连续失败（529）处置 | P1 | done | — | 用户选方案 A：瞬时错误同小时内最多再试 2 次、间隔 60 s；连续 2 整点全失败告警 + 恢复通知；ADR 0006 补条 | 4 个新测试 + 分类参数化；CI 42768473571 绿 | 不改提示词/模型/指纹；观察一周“整点最终无信号”比例 |
| 2 | web 在 OKX 不可达时降级 | P1 | done | — | Market 失败短缓存 + 旧值；overview/equity 行情字段可为 null + `market` 状态；其他路径 503；UI 横幅 | 3 个新测试；CI 42763806494 绿 | 基线：3 天 1,040 次 500；改后比例待 mini 部署后观察 |
| 3 | mini 关闭睡眠 | P1 | blocked | 用户 | `sudo pmset -a sleep 0` | 用户执行后 `pmset -g` 核对 | 需用户在 mini 执行；实盘的解锁条件之一（ADR 0010） |
| 4 | 11-11 结算后核对 | P1 | blocked | 时间 | 核对准确度卡与净值曲线 | — | 11-11 后 |
| 5 | CI 覆盖 crypto-trader | P1 | done | — | ci.yml 加 crypto-trader 与 cursor/**；test 装 `.[dev,web]` | CI 42762814727 绿（py3.11–3.14、NY 时区、smoke、ruff） | — |
| 6 | ADR 0001 例外登记 | P2 | done | — | 前提修正：上游 4429078 早已在分支里，本地 3 行补丁是其上的额外修正且有测试锁定；不改代码，ADR 0001 新增「例外（登记）」一节 | 文档改动；CI 42768891023 绿 | 是否向上游提 PR 由用户定 |
| 7 | 定价表到期维护 + 过期提示 | P3 | blocked | 时间 | 步骤 3 已做：`Price.until`、`/api/models.price_until`、模型选择器对“截止日已过 / as_of 超 90 天”标“待核对官网”；ADR 0007 改成具体规则 | 1 个新测试 + API 断言；CI 42770632478 绿 | 步骤 1–2 等 11-30 / 12-31 到期后改单价 |
| 8 | 扩池前置：指纹 + KeyError | P2 | done | — | `Paper.instruments`（持仓 ∪ 自选池）；两个账户指纹含 watchlist，旧指纹首次只记录；基线跳过无参考价的币 | 5 个新测试；CI 42766298688 绿 | 未改自选池 |
| 9 | 验证期末分流决策 | P2 | blocked | #4 | 决策模板 | — | 12-05 前 |
| 10 | 清理 worktree/分支，同步文档提交 | P3 | blocked | 用户 | 用户选 A：已删 t1/t2/t5/t7（已合入、干净）；t6 有 3 个文件未提交改动，保留 | backup 已同步 | t6 由用户处理后才能关闭 |
| 11 | 日报 OKX 不可达时降级 | P2 | done | 措辞同 #2 | `okx.REQUEST_ERRORS`；meta `marks`；`Paper.equity_now()` 回退标记价；日报/小时报带 ⚠ 行 | 5 个新测试；CI 42764932128 绿 | 首次运行后 marks 才有值 |
| 12 | ledger 索引/WAL/反向依赖 | P3 | done | — | SCHEMA 5 个索引；写端 `journal_mode=WAL`；`fills()` 按 (ts, id) 排序；`SignalLike` Protocol 替代 intraday 导入 | `tests/test_trader_layering.py` 9 个测试；CI 42769530175 绿 | 手工备份账本要用 `.backup`，不能只 cp 主文件 |
| 13 | events/attempts 分页、research_index 缓存 | P3 | done | — | `since`/`limit`（默认 500）；`final_rating` 按 (mtime, size) 缓存；History 页显式传 limit | 2 个新测试；CI 42770062493 绿 | 部署要重启 web |
| 14 | 写端点认证 | P2 | done | — | `Settings.web_token`；`_write_auth` 依赖；`/api/models.write_protected`；UI 令牌框（sessionStorage） | 2 个新测试 + 真服务器 curl；CI 42767234724 绿 | 部署：.env 加 TRADER_WEB_TOKEN + kickstart web（不用改 plist） |
| 15 | 账户目录备份命令（WAL 后 cp 不安全） | P2 | done | — | `trader/backup.py` + `python -m trader backup DEST [--with-logs]`：SQLite 备份 API 一致快照，副本单文件；roadmap 补备份/恢复说明 | `tests/test_trader_backup.py` 3 个测试；CI 42772492468 绿 | 复审第 2 批时发现；是否排定时备份由用户定 |
| 16 | 总览首屏改成资产卡（用户反馈看板可读性差） | P1 | done | — | overview 加 capital/today/totals、持仓加 unrealized_pct；首屏七格资产卡（总资产、今日盈亏 UTC 日注北京 08:00、未实现、已实现、现金、名义/杠杆、累计）；持仓面板第二排 + 敞口分布条 + 浮盈% + 合计行；验证期指标下移；悬停时间加北京钟；指南/帮助同步 | `tests/test_web_api.py` 补 4 处断言 + 1 个新测试（零点快照未写时的起点）；tsc/oxlint/build；本机预览 1280 宽首屏；CI 42780888213 绿 | 用户拍板：UTC 为主旁注北京时间；交易盈亏不含 LLM 费用；已部署 mini（db7a7d0，11-10 09:05Z） |
| 17 | 每日/每月收益（/daily、柱状图、历史页标签） | P1 | done | #16 | 新接口 `GET /api/accounts/{id}/daily?limit=400`（按 UTC 日：open/close/pnl/pct/fills/funding/llm_cost/partial + months，最后一天到实时净值，无报价为 null）；总览持仓下“每日盈亏 · 最近 30 天”红绿柱（今天浅色，悬停 UTC/北京跨度）+ 月度收益表；历史页“每日收益”标签（期初/期末/盈亏/%/成交/资金费/AI 费用）；指南/帮助同步 | `tests/test_web_api.py` 4 个新测试；全量 1878 通过；tsc/oxlint/build 通过；本机预览核对 | 已关闭（CI 42785452087）；已部署 mini（db7a7d0，11-10 09:05Z） |
| 18 | 成交的已实现盈亏（只读回算） | P2 | done | — | `fills` 每行加 realized/realized_net/position_after，每次请求用 `paper._move` 从首笔回算（不改账本）；历史页成交表加“已实现（扣费）”“成交后持仓”两列 + 所列合计；帮助/指南说明与总览已实现的差额是资金费 | 测试：减仓/反手/平仓与 `_move` 对照；真实 execute+replay 验证 Σ(realized−fee)+funding == cash−capital；全量 1880 通过；tsc/oxlint/build 通过 | 已关闭（CI 42787102174）；已部署 mini（db7a7d0，11-10 09:05Z） |
| 19 | ADR 0008 + OKX 私有接口客户端（模拟盘） | P1 | done | — | 用户决定验证期内并行建执行层、demo 跟日内账户；`trader/okx_private.py` 签名/模拟盘标头/账户配置/持仓模式/杠杆/余额/持仓/市价单/查单/成交历史分页/条件止损单/一键平仓/资金费账单，`simulated=False` 直接拒绝；`Settings.okx_demo`（TRADER_OKX_DEMO_*，repr 掩码）；`python -m trader demo check` 只读 | `tests/test_trader_okx_private.py` 28 个（录制应答、已知签名向量、密钥不出现在输出）；CI 42797907343 | 执行层第 1/4 张票 |
| 20 | Demo 执行器（对账优先、跟日内信号下单、交易所侧止损、熔断） | P1 | done | #19 | `trader/demo/{account,job,report,settings}.py`：sync 以交易所为准入账（余额/持仓/成交/资金费/条件单，成交按 clOrdId 前缀归因），日内 `decided_hour` 到位后按同一套仓位规则下市价单（clOrdId 幂等、51016 回读），止损为交易所侧 reduce-only 条件单只收紧，熔断 close-position + 撤单 + halted；CLI `demo init|run|sync|report|resume`；launchd :10 等日内 :03 最多 15 分钟；顺带 `ContractSpec.tick_size`、`close_position(client_id=)` | 新增 39 个测试（仿真交易所）：开/加/反手/平/缺信号/止损触发对账/资金费/跨零点/熔断+resume/重跑幂等/对不上账跳过并限频告警/等决策超时/日内熔断跟随/CLI；全量 1946 通过；CI 42801935532 | 2026-11-10 完成（2d9c258、d415851、6fc8bf2）；未部署 mini，等 #22 |
| 21 | 看板接入 demo 账户 | P2 | done | #20 | accounts 含 demo；`/api/accounts/demo/execution`（上次对账：权益/钱包/持仓含杠杆、强平价、止损/挂着的止损单/问题/熔断）和 `/mirror`（与日内并排：持仓方向、逐小时成交与滑点 bp、两边累计收益），非 demo 账户 404；UI：顶栏 Demo、总览「执行对账」面板替代 LLM 面板、策略系列标「策略（交易所权益）」、历史页「与日内对照」页签、成交原因「非程序」、帮助 execution/mirror、指南第 10 节 | `tests/test_web_api_demo.py` 9 个；全量 1955；tsc/eslint/vite build；本机合成账本预览三处页面 | 已关（CI 42805364239）；提交 3964584 + 9c35252；未部署 mini，等 #22 |
| 22 | Demo 并行验收（mini 部署、7 个交易日对照报告） | P2 | in-progress | #20 #21 | 2026-11-10 11:53Z 用户授权（选 A）后部署：mini → 2a7a8f9、web 重启；`demo check` 通过（跨币种保证金、net、read+trade）；`demo init` 本金 5,000 USDT；launchd demo 作业已加载（:10） | 每小时按时运行；跑满 7 个交易日出 `docs/reports/demo-parallel-run.md`，结论进 roadmap | 观察中；13:01Z 用户授权（选 A）后 mini 升到 03aa7b0（含 #23 权限探针和 #24 跟随信号页），只 pull + rsync dist + 重启 web；首次运行 12:10Z |
| 23 | demo check/init 用探针验证 API key 的交易权限（50123 到首次下单才暴露） | P2 | done | #20 | `OKXPrivate.check_trade_permission`：撤一张不存在的订单，50xxx 即权限不足，51400 即能下单；check 打印结论，init 先探再改设置；账户模式档位用 OKX 现名（合约模式）；下单预检接口不能用（只对跨币种/组合保证金开放） | +4 测试，全量 1959；mini 真 key 验过两种结果 | 已关（CI 42816890344）；提交 e7f8dbe；未部署 mini |
| 24 | Demo 账户显示它跟随的日内信号及每小时执行结果（切到 Demo 信号页为空） | P2 | done | #22 | `followed_signals`：读日内账本的信号，按小时对照 Demo 的成交/事件标 executed / no_change / skipped / blocked / failed / pending；前端 Demo 有「信号」页和总览「最近信号」，「Demo 执行」芯片代替 token 成本列 |
| 25 | 信号记录同时显示北京时间 | P3 | done | — | `Time` 组件 `beijing` 属性：信号页和总览「最近信号」在 UTC 后显示「北京 HH:MM」，跨日带日期；其他页面不变 |
| 26 | demo 对账切掉了交易所时间戳晚于本机“现在”的成交，迟到成交下一小时又重复计 | P1 | done | #22 | 13:10Z 首次真实下单暴露：mini 时钟比 OKX 慢 1～3 s。对账窗口向后放宽 CLOCK_SKEW_MS=60 s；“成交解释的仓位”= `Ledger.net_fills()` 累计和，迟到成交抵消而非叠加；近三天成交读 `/trade/fills` 实时接口，更早读历史；14:10Z 对账干净、迟到成交补齐、正常交易，已关 |
| 27 | 离线评估框架（一期）：行情缓存、日内规则层回放、信号质量报告 | P1 | done | — | 用户选“先建评估再按数据改”。`IntradayPaper` 常数收进 `Params`（默认=线上）；`trader/evaluation/`：HistoryStore（sqlite 行情缓存只补缺段）、HistoricalOKX（带时钟的历史市场）、replay（真引擎逐小时回放，参数网格，策略层开关默认全关）、signals（1/4/24h 方向收益、换向）、CLI `evaluate fetch|replay|signals`；ADR 0009 | +26 测，全量 1994；回放线上信号：16 笔成交一一对应、午夜净值差 1.5 bp | 报告 docs/reports/evaluation-intraday-2026-11-10.md：样本 3.4 天不足以改参数；不按信心加仓；盯止损倍数、ATR 周期；下一步 #28/#29 |
| 28 | 离线评估（二期）：LLM 在历史输入上重跑小时信号，样本扩到几个月 | P1 | blocked | #27、用户 | `trader/evaluation/rerun.py` + `evaluate rerun`：线上 `Signaler` 对着 `HistoricalOKX` 逐小时问、引擎同步交易；按小时和币缓存（断点续跑、不重复付费）、预算按缓存累计、零成本失败退避重试；只走评估专用渠道和密钥（`TRADER_EVAL_BACKEND_URL`/`TRADER_EVAL_API_KEY`），与环境里任何 `*_API_KEY` 相同就拒绝启动 | 10-10→10-24 重跑 339 小时 1014 条（13.98 美元，约 1 美元/天）；报告 docs/reports/evaluation-rerun-2026-11-11.md：重跑信号反向，默认 −12.12%，网格差异主要来自敞口，线上不动 | 11-10 重跑走线上密钥被中转渠道判为批量任务，连带 mini 日内信号 16:03–00:03 UTC 连续 9 个整点失败（01:03 恢复）；剩余 10-24→11-06 约 309 小时（≈13 美元，86 美元预算还剩 72）：11-11 用户选暂不重跑，先等线上信号积累（11-07 起，约 11-21 满 14 天）用一期工具对照；要补时先配评估专用渠道 |
| 29 | 离线评估（三期）：日频账户回放，Paper 收进 Params | P2 | triage | #27 | 评级从研究日志读；样本只有 4 个交易日，等 3–4 周 | — | — |
| 30 | 实盘（第 1 档）：客户端的正式环境开关、单独的密钥文件、`live check` | P1 | review | — | ADR 0010；`OKXPrivate` 能连正式环境，默认仍是演示环境；live 密钥放 mini 上单独的文件，只有 `live` 命令读；只读检查含实际费率；核实正式环境域名、子账户资金是否独立 | 121 个新用例，全量 2139 通过；独立审查后返工 1 次（口令不随报错外泄、不跟随重定向等 8 条）；mini 上用只读 key 跑 `live check` 还没做；Python 3.14 上 CI 红（密钥文件的检查、标准库拒发的请求头），修复合并 `03f9bb6`，CI 43348772314 绿 | 已合 `ad6e8c4`（第 1 轮，`cursor/issue-30-live-client-6e50`），3.14 修复 `03f9bb6`；等 #35 的 key 在 mini 上跑 `live check`（域名、子账户、实际费率、探针的拒绝码）后关票 |
| 31 | 实盘（第 1 档）：live 账户、生来暂停的影子运行、带账户名的告警、外部心跳 | P1 | review | #30（已合） | 执行器按账户参数化；`live init` 建好即暂停；暂停时只读交易所并记录本该下的单；`live resume` 在第 2 档合入前不开放；成功后请求外部心跳 | 仿真交易所测试：新增 51 个用例，全量 2255 通过（py3.12/3.14），ruff、tsc / oxlint / build 通过，CI 43352592411 绿；命令行和心跳的 7 处变异都被抓到；mini 上影子运行 24 小时没有订单发出（未部署） | 已合 `9c0ba2c`（`cursor/issue-31-live-account-6e50`）；部署要用户授权，还要 #35 的只读 key 和心跳地址；live 熔断的告警写着运行 `live resume`，但 resume 拒绝熔断中的账户，#33 一并改 |
| 32 | 实盘（第 2 档）：止损单更新期间不留空窗，成交后挂不上止损就平仓 | P1 | review | — | 先挂后撤或改单接口；成交后挂不上就重试，再不行市价平并告警；一个仓位失败不影响其余；触发价已被穿越时平仓 | 仿真交易所测试：61 个新用例，全量 2204 通过（py3.12/3.14），独立审查后返工 1 次；演示环境实测归 #42 | 已合 `68d68f2`（第 1 轮，分支 `cursor/issue-32-stop-no-gap-6e50`）；改的是共用执行器，demo 同时受益，部署要用户授权；#42 在演示环境上测过（反手时两张止损能否并存、拒单的错误码）后关票 |
| 33 | 实盘（第 2 档）：熔断做扎实、`halt`、余额读不到不当成净值 0 | P1 | ready | — | 先写状态再平仓、逐个仓位容错、平后核实、告警必发；`live halt` 和 `demo halt`；`balance()` 没有数据时按出错处理 | 仿真交易所测试 | — |
| 34 | 实盘（第 2 档）：暂停状态和触发条件，live 的指纹暂停和两个绝对上限 | P1 | blocked | #33（#31、#32 已合） | 非程序成交（含强平）、未解释的余额变化、对不上账时暂停，demo 同样生效；live 另在指纹变化、净值超过 2,000 USDT 时暂停，单笔超过 4,000 USDT 拒单；暂停期间不自动熔断、只告警；最后合入并打开解锁 | 仿真交易所测试，逐个触发条件 | 部署后 demo 的异常处理会变 |
| 35 | 实盘：用户侧事项 | P1 | blocked | 用户 | 子账户、500 USDT、只读 key 后换交易 key（绑 IP、不勾提币）、心跳服务；解锁条件：#3 和 `TRADER_WEB_TOKEN` | 清单逐项勾完 | 需用户执行 |
| 36 | 实盘（第 3 档）：告警改进 | P2 | ready | #34 之后 | 止损成交当小时通知；失败告警按错误类型限频；发送失败后补发 | 测试 | 解锁之后做 |
| 37 | 实盘（第 3 档）：对不上账的修复命令 | P2 | blocked | #34 | `live reconcile` 和 `demo reconcile`：重读更长的时间窗补齐，差额经人确认后记成调整 | 仿真交易所测试 | — |
| 38 | 实盘（第 3 档）：`trader backup` 包含 demo 和 live 的账本 | P2 | done | — | `backup.LEDGERS` 加 demo、live 两个账本，同样走 SQLite 快照；命令逐个说明缺的账本；备份只拷清单里的东西，密钥文件不进备份 | `tests/test_trader_backup.py` 新增 5 个用例；全量 2018 通过 | 已合 `4cf5e54`（第 1 轮，`cursor/issue-38-backup-ledgers-6e50`）；roadmap 的备份和恢复说明已同步 |
| 39 | 实盘（第 3 档）：下单前的输入检查、顶格反手 | P2 | ready | #34 之后 | 拒单检查不拦正常反手；下单前重取报价；报价和 ATR 必须是大于 0 的有限数 | 复现场景的测试 | 解锁之后做 |
| 40 | 实盘（第 3 档）：出入金记账 | P2 | blocked | #34 | 读划转账单记成流水；本金、峰值、收益率按出入金调整；收益率口径待用户确认 | 仿真交易所测试；演示环境实测划转 | 第二次入金之前必须完成 |
| 41 | 实盘（第 3 档）：看板显示 live 账户 | P2 | ready | #31（已合） | 账户列表加 live；真钱标识；显示暂停、影子运行、熔断；指南同步 | 测试；tsc / oxlint / build | 部署要用户授权 |
| 42 | 实盘：在演示环境上演练执行器 | P2 | blocked | #30–#34、#22 | 开仓、反手、止损触发、手动平仓、`halt`、对不上账、中途杀进程、重复运行、划转 | 报告入 `docs/reports/` | 不卡解锁；避开 #22 的观察期 |
| 43 | 实盘：到期报告和去留决定 | P2 | blocked | 时间 | live、demo、日内模拟盘三方逐笔对照；继续、改跟 Rating 或停，决定写成 ADR | 报告入库 | 2026-12-05 |

## 执行记录

| 日期 (UTC) | Issue | 分支/提交 | 结果 |
|---|---|---|---|
| 2026-11-10 | — | 审计报告与本文档 | 基线：ruff 通过、oxlint 0、tsc 通过、441 测试通过 |
| 2026-11-10 | #5 | `cursor/issue-5-ci-crypto-trader-6e50` → 68bbaa3（ff） | 验收通过（CI 42762814727）；“Closes” 让 push 提前关了 Issue，之后提交信息改用 “Refs” |
| 2026-11-10 | #2 | `cursor/issue-2-web-okx-degrade-6e50` → 030855b，合并 2a314be | 验收通过（CI 42763806494）；全量 1833 通过、tsc/oxlint/build 通过 |
| 2026-11-10 | #11 | `cursor/issue-11-daily-report-degrade-6e50` → 合并 4f126c5 | 验收通过（CI 42764932128）；全量 1838 通过 |
| 2026-11-10 | #8 | `cursor/issue-8-watchlist-fingerprint-6e50` → 1313a9a（ff） | 验收通过（CI 42766298688）；全量 1843 通过；曾试按币数生成“三币等权”措辞，因超出范围回退，记入 roadmap |
| 2026-11-10 | #14 | `cursor/issue-14-write-token-6e50` → f04a466（ff） | 验收通过（CI 42767234724）；全量 1845 通过；手工对真 uvicorn：401/401/200，预检含 Authorization |
| 2026-11-10 | #1 | 用户选方案 A；`cursor/issue-1-intraday-signal-retry-6e50` → 4c9fd64（ff） | 验收通过（CI 42768473571，4c9fd64 的 run 被紧随的文档推送取消，以 fb475e4 的 run 为准；教训：等 CI 绿再推文档）；全量 1858 通过 |
| 2026-11-10 | #6 | `cursor/issue-6-adr-0001-exception-6e50` → 0b5863a（ff） | 验收通过（CI 42768891023）；Issue 前提不成立，改为登记例外 |
| 2026-11-10 | #12 | `cursor/issue-12-ledger-indexes-wal-6e50` → 7b2c203（ff） | 验收通过（CI 42769530175）；全量 1867 通过 |
| 2026-11-10 | #13 | `cursor/issue-13-web-pagination-rating-cache-6e50` → 7aac9bb（ff） | 验收通过（CI 42770062493）；全量 1869 通过，tsc/oxlint/build 通过 |
| 2026-11-10 | #7 | `cursor/issue-7-price-expiry-hint-6e50` → acbfc05（ff） | 步骤 3 完成（CI 42770632478）；全量 1870 通过；步骤 1–2 等到期日，Issue 保持 blocked |
| 2026-11-10 | #10 | 无提交（仓库维护） | 用户选 A：删 t1/t2/t5/t7 worktree+分支；t6 有未提交改动保留，等用户；Issue blocked |
| 2026-11-10 | #15 | 新开（复审发现）；`cursor/issue-15-account-backup-6e50` → 044a8be（ff） | 验收通过（CI 42772492468）；全量 1873 通过 |
| 2026-11-10 | 部署 | mini ea0400e → b228b3b | 用户授权（选 A）；pull + uv 装依赖 + rsync dist + kickstart web；验证：/api/models write_protected=false（未设令牌）、attempts?limit=0 → 422、新 bundle 已服务；第一份备份 ~/Backups/trader/20261110T071951Z；账本在下个整点作业才切 WAL |
| 2026-11-10 | #16 | 用户反馈后 grill 需求，开 #16/#17/#18；`cursor/issue-16-asset-card-6e50` → 74d7a72 + aee6294（ff） | 验收通过（CI 42780888213）；全量 1874 通过，tsc/oxlint/build 通过；本机预览核对首屏；未部署 mini |
| 2026-11-10 | #17 | `cursor/issue-17-daily-returns-6e50` → 954f728（API）+ 0c95e3e（UI）（ff） | 验收通过（CI 42785452087）；全量 1878 通过，tsc/oxlint/build 通过；本机预览（临时账本补假快照）核对总览与历史页；未部署 mini |
| 2026-11-10 | #18 | `cursor/issue-18-fill-pnl-6e50` → 6d27baa（API）+ de98f2b（UI）（ff） | 验收通过（CI 42787102174）；全量 1880 通过，tsc/oxlint/build 通过；本机预览核对成交表；未部署 mini |
| 2026-11-10 | 部署 | mini a60bd57 → db7a7d0 | 用户授权（选 A）；pull + uv 装依赖 + rsync dist + kickstart web；验证：/api/accounts 200、/daily 有逐日行、/fills 有 realized 字段、overview 有 today/totals、新 bundle index-DETK1jZP 已服务；部署时 mini 与本机都连不上 OKX（intraday 09:03Z、mark 09:07Z 失败，08:03Z 还正常），看板显示行情横幅，属外部网络，未处理 |
| 2026-11-10 | #19 | `cursor/issue-19-okx-private-client-6e50` → cbb1dfb（ADR 0008 + roadmap）+ 2b75fc5（客户端 + demo check）（ff） | 验收通过（CI 42797907343）；全量 1907 通过；用户 11-10 决定：并行建执行层到 OKX Demo，demo 跟日内账户，其余按推荐（全仓/单向/3×/交易所止损/模拟余额为本金/mini）；开 #19–#22 |
| 2026-11-10 | #20 | `cursor/issue-20-demo-executor-6e50` → 2d9c258（okx tick/clOrdId）+ d415851（demo account/report）+ 6fc8bf2（job/CLI/plist/roadmap）（ff） | 验收通过（CI 42801935532）；全量 1946 通过；测试抓到并修了一个 bug（熔断后再次对账时丢失熔断告警）；未部署 mini |
| 2026-11-10 | #21 | `cursor/issue-21-dashboard-demo-6e50` → 3964584（web api）+ 9c35252（ui）（ff） | 验收通过（CI 42805364239）；全量 1955 通过；本机合成账本预览了总览/历史/指南；未部署 mini |
| 2026-11-10 | 部署 + #22 | mini db7a7d0 → 2a7a8f9 | 用户授权（选 A）；pull + uv + rsync dist + kickstart web；模拟盘账户模式原为现货，用户改成跨币种保证金后 `demo check`/`demo init`（本金 5,000）通过；装并加载 com.tradingagents.trader.demo；/api/accounts/demo/{overview,execution,mirror} 200；daily/intraday/mark 未动 |
| 2026-11-10 | #23 | 首次 demo 运行暴露（三笔单 50123）后新开；`cursor/issue-23-demo-precheck-6e50` → e7f8dbe（ff） | 验收通过（CI 42816890344）；全量 1959 通过；用户已把 key 权限补上、账户模式改为合约模式，模拟盘 13:10Z 起正常下单；未部署 mini |
| 2026-11-10 | #24 | 用户反馈「切到 demo 信号不见了」后新开；`cursor/issue-24-demo-followed-signals-6e50` → 65dc8e7 + 20400c2（ff） | 验收通过（CI 42819046917）；全量 1961 通过，tsc/eslint/build 干净；本地合成账本预览六种芯片正常；未部署 mini |
| 2026-11-10 | 部署 #23 + #24 | mini 2a7a8f9 → 03aa7b0 | 用户授权（选 A）；pull + uv + rsync dist + kickstart web；/、demo 和 intraday 的 /signals 均 200，demo 信号页显示 12:03Z 三条日内信号并标「下单失败」（即 12:10Z 的 50123）；未重启 daily/intraday/mark/demo |
| 2026-11-10 | #25 | 用户要求信号记录显示北京时间；`cursor/issue-25-signals-beijing-time-6e50` → 854008c（ff） | 验收通过（CI 42822807972）；tsc/eslint/build 干净；未部署 mini |
| 2026-11-10 | #26 | 13:10Z demo 首次下单后对账漏了 ETH/SOL 成交；`cursor/issue-26-demo-fills-latency-6e50` → a123dce（ff） | 全量 1968 通过，新增 7 测（两接口分段/合并、迟到成交抵消、持续不解释仍报、时钟偏差、net_fills）；ADR 0008 补记；等授权部署 |
| 2026-11-10 | 部署 #25 + #26 | mini 03aa7b0 → 15ad42f | 用户授权（选 A，13:46Z）；pull + uv + rsync dist + kickstart web；/、demo signals、execution 均 200；未重启 daily/intraday/mark/demo；等 14:10Z 对账验证 #26 |
| 2026-11-10 | #26 验收 | mini 15ad42f | 14:10Z 对账 problems=[]，13:10 的 20 笔迟到成交入账，ETH/SOL 按 14:00 信号减仓，止损重挂；关闭 |
| 2026-11-10 | #27 | 用户要求优化策略，选“先建评估”；`cursor/issue-27-evaluation-harness-6e50` → 7fd723e（Params）+ 2da12c8（框架）+ 文档（ff） | 全量 1994 通过；用 11-07〜11-10 的真实行情和线上信号验收：成交逐笔对应、净值差 1.5 bp；网格和信号质量报告已出；线上未动，不需部署；已关（CI 42837617005）；开 #28（LLM 历史重跑，ready）、#29（日频回放，triage） |
| 2026-11-10 | #28 | `cursor/issue-28-llm-rerun-6e50` → 80e504f（重跑）+ 2f23164（零成本失败退避重试）+ 4af66d5（预算按缓存累计、ADR 0009） | 按 86 美元预算从 10-10 起重跑，到 10-24 03:03 共 339 小时 1014 条、13.98 美元；重跑用的是线上密钥，被中转渠道判为批量任务，连带 mini 日内信号 16:03–00:03 连续 9 个整点失败，01:03 自行恢复；重跑停在 10-24 03:03（续跑循环 22:00 前后放弃），未动 mini |
| 2026-11-11 | #28 | 用户选 A（先用已缓存的 14 天出报告）；d1d0c82（重跑只走 `TRADER_EVAL_BACKEND_URL`/`TRADER_EVAL_API_KEY`，与环境里任一 `*_API_KEY` 相同就拒绝启动；ADR 0009 补记事故）；四个提交一并 ff 进 crypto-trader；324927e（`.gitignore` 加 `!docs/reports/`，一期、二期报告进库） | 全量 2013 通过，新增 5 测；CI 42950063782 绿；真实 .env 下执行重跑被拒（未配评估渠道）；报告 docs/reports/evaluation-rerun-2026-11-11.md：重跑信号反向，默认回放 −12.12%，所有配置都亏、差异主要来自敞口，线上参数不动；未调模型、未动 mini、不需部署；CI 42950843920 绿；#28 改 blocked，用户随后选剩余 10-24→11-06 暂不重跑、等线上信号积累 |
| 2026-11-12 | #30–#43 | 用户要求接入实盘，grill 后定方案；ADR 0010、`CONTEXT.md`、roadmap 和本文档（只改文档） | 用户决定不等 #22 的报告和验证期结论：live 账户跟日内 Signal，独立子账户先入 500 USDT、上限 2,000，跑到 12-05；账户生来暂停（影子运行），解锁条件是第 1、2 档的票加 #3 和 `TRADER_WEB_TOKEN`；开 #30–#43；没有代码改动，全量 2013 通过；未动 mini、不需部署 |
| 2026-11-12 | #30 #32 #38 | 第 1 轮派出，起点 034961d：`cursor/issue-30-live-client-6e50`、`cursor/issue-32-stop-no-gap-6e50`、`cursor/issue-38-backup-ledgers-6e50` | 执行会话是 Cursor 的 Task 子代理，worktree 在 `../TradingAgents.worktrees/` 下由指挥会话手工建（`agent` CLI 登录失效，`best-of-n-runner` 不建 worktree）；会话 id 和交接事项在 `~/.commander/TradingAgents/live-rounds.md`；未动 mini |
| 2026-11-12 | #38 | `cursor/issue-38-backup-ledgers-6e50` → 合并 4cf5e54 | 验收通过：分支和主干各跑一遍守门，全量 2018 通过、ruff 通过；改动只在 `trader/backup.py`、`backup` 命令和它的测试；roadmap 的备份和恢复说明同步；CI 43271606110 绿，已关票；不需部署（mini 下次更新代码时带上） |
| 2026-11-12 | #30 | `cursor/issue-30-live-client-6e50` → 合并 ad6e8c4 | 代码验收通过，票不关（mini 上的 `live check` 等 #35）。`OKXPrivate` 默认仍是演示环境，`simulated` 只能按名字传且只读，只有 `trader/live/` 构造正式环境的客户端；密钥文件 `~/.config/tradingagents/okx-live.env`（权限 600，值只收可见 ASCII）；`python -m trader live check` 只读。独立审查找出两条密钥外泄的路径（口令随 `InvalidHeader` 的文本打出、请求跟随重定向带走签名头），返工 1 次修掉，demo 的客户端同时受益；全量 2139 通过 |
| 2026-11-13 | #30 | `cursor/issue-30-live-client-6e50` → efb73b8、6ea91f5，合并 03f9bb6 | 主干 CI 在 Python 3.14 上红（run 43280556556）：3.14 的 `Path.is_file()` 遇到任何 `OSError` 都返回 False，标准库拒发的请求头报的是 `ValueError`。密钥文件改为只 `stat` 一次、按错误类型说明原因，标准库拒发的请求头和 `InvalidHeader` 一样不带值报错；py3.12/3.14 全量 2143 通过，CI 43348772314 绿 |
| 2026-11-13 | #32 | `cursor/issue-32-stop-no-gap-6e50` → 返工 e528e62、9cb279d、6fbad02，合并 68d68f2 | 独立审查退回 4 条后返工：受理了却读不到的新止损（假交易所加开关，两条用例）、止损价按成交价定（正常路径和 protect 各一条）、一条恒真断言、protect 读交易所不重试且整池告警不记事件；三处变异都被新用例抓到，三个提交逐个跑过。全量 2204 通过（py3.12/3.14），ruff 通过，CI 43349373742 绿。票不关：演示环境实测归 #42；ADR 0008/0010、帮助页和指南的说法同步；部署要用户授权（mini 上的 demo 还是旧的换单方式） |
| 2026-11-13 | #31 | `cursor/issue-31-live-account-6e50` → 738aa05、89e5c5d、47ad594、8139a57、19d3faf、11c79d1，合并 9c0ba2c | 执行器按账户的 `Profile` 参数化（demo、live），消息前面带【账户名】，原来的“demo · ”“demo 对账：”“demo 运行失败：”“demo 日报 · ”都改了；账户可暂停（元数据 `paused`，事件 pause / unpause）：暂停时交易所客户端只读，不设置、不挂改止损、不下单、不熔断，没止损的仓位和回撤到线都只告警；影子运行记 shadow_order / shadow_none 事件，日报计数，`live report` 按小时列；限频键 live 用 `live_alerted_at`（demo 仍是 `demo_alerted_at`）；命令 `live init / run / sync / report / resume`，解锁开关 `trader/live/account.py` 的 `UNLOCK_OPEN` 默认关；心跳 `TRADER_LIVE_HEARTBEAT_URL`；`deploy/com.tradingagents.trader.live.plist` 只建不装；指南和 ADR 0010 同步。全量 2255 通过（py3.12/3.14），CI 43352592411 绿；票不关（验收要 mini 上影子运行满 24 小时）；未动 mini，部署要用户授权 |
