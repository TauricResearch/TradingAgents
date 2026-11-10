# 优化进度（Issue 驱动）

Issue 在 [kissman911/tradingagents-crypto-trader](https://github.com/kissman911/tradingagents-crypto-trader/issues)。审计报告：[audit-2026-11.md](audit-2026-11.md)。
流程：每个 Issue 一个分支（`cursor/issue-<n>-<slug>-6e50`）→ 改动 + 测试 → ruff / pytest / tsc / oxlint / build → 自审 → 合入 `crypto-trader` → 推 `backup` → 验收通过才关 Issue。
mini 上的部署（`git pull`、`launchctl kickstart`）由用户执行，按 roadmap 的更新流程。

状态：triage 待定方案 · ready 可做 · in-progress 进行中 · blocked 阻塞 · review 待验收 · done 已关闭。

| # | 标题 | 优先级 | 状态 | 依赖 | 方案要点 | 测试/验收 | 阻塞或备注 |
|---|---|---|---|---|---|---|---|
| 1 | 日内信号连续失败（529）处置 | P1 | review | — | 用户选方案 A：瞬时错误同小时内最多再试 2 次、间隔 60 s；连续 2 整点全失败告警 + 恢复通知；ADR 0006 补条 | 4 个新测试 + 分类参数化；等 CI | 不改提示词/模型/指纹 |
| 2 | web 在 OKX 不可达时降级 | P1 | done | — | Market 失败短缓存 + 旧值；overview/equity 行情字段可为 null + `market` 状态；其他路径 503；UI 横幅 | 3 个新测试；CI 42763806494 绿 | 基线：3 天 1,040 次 500；改后比例待 mini 部署后观察 |
| 3 | mini 关闭睡眠 | P1 | blocked | 用户 | `sudo pmset -a sleep 0` | 用户执行后 `pmset -g` 核对 | 需用户在 mini 执行 |
| 4 | 11-11 结算后核对 | P1 | blocked | 时间 | 核对准确度卡与净值曲线 | — | 11-11 后 |
| 5 | CI 覆盖 crypto-trader | P1 | done | — | ci.yml 加 crypto-trader 与 cursor/**；test 装 `.[dev,web]` | CI 42762814727 绿（py3.11–3.14、NY 时区、smoke、ruff） | — |
| 6 | ADR 0001 例外回退 | P2 | ready | — | 回退 news.py，等上游 4429078 或 trader 侧兜底 | 研判在 Yahoo 不可用时仍完成 | 改动 tradingagents 指纹会变（代码指纹，不重置验证期） |
| 7 | 定价表过期提示 | P3 | ready | — | UI 高亮 + 维护说明 | — | — |
| 8 | 扩池前置：指纹 + KeyError | P2 | done | — | `Paper.instruments`（持仓 ∪ 自选池）；两个账户指纹含 watchlist，旧指纹首次只记录；基线跳过无参考价的币 | 5 个新测试；CI 42766298688 绿 | 未改自选池 |
| 9 | 验证期末分流决策 | P2 | blocked | #4 | 决策模板 | — | 12-05 前 |
| 10 | 清理 worktree/分支，同步文档提交 | P3 | ready | — | 删已合并分支；推 backup | — | 删分支前需用户确认 |
| 11 | 日报 OKX 不可达时降级 | P2 | done | 措辞同 #2 | `okx.REQUEST_ERRORS`；meta `marks`；`Paper.equity_now()` 回退标记价；日报/小时报带 ⚠ 行 | 5 个新测试；CI 42764932128 绿 | 首次运行后 marks 才有值 |
| 12 | ledger 索引/WAL/反向依赖 | P3 | ready | — | 索引 + WAL + 类型内聚 | 单元测试 | WAL 只读连接权限需验证 |
| 13 | events/attempts 分页、research_index 缓存 | P3 | ready | — | limit + mtime 缓存 | 单元测试 | — |
| 14 | 写端点认证 | P2 | done | — | `Settings.web_token`；`_write_auth` 依赖；`/api/models.write_protected`；UI 令牌框（sessionStorage） | 2 个新测试 + 真服务器 curl；CI 42767234724 绿 | 部署：.env 加 TRADER_WEB_TOKEN + kickstart web（不用改 plist） |

## 执行记录

| 日期 (UTC) | Issue | 分支/提交 | 结果 |
|---|---|---|---|
| 2026-11-10 | — | 审计报告与本文档 | 基线：ruff 通过、oxlint 0、tsc 通过、441 测试通过 |
| 2026-11-10 | #5 | `cursor/issue-5-ci-crypto-trader-6e50` → 68bbaa3（ff） | 验收通过（CI 42762814727）；“Closes” 让 push 提前关了 Issue，之后提交信息改用 “Refs” |
| 2026-11-10 | #2 | `cursor/issue-2-web-okx-degrade-6e50` → 030855b，合并 2a314be | 验收通过（CI 42763806494）；全量 1833 通过、tsc/oxlint/build 通过 |
| 2026-11-10 | #11 | `cursor/issue-11-daily-report-degrade-6e50` → 合并 4f126c5 | 验收通过（CI 42764932128）；全量 1838 通过 |
| 2026-11-10 | #8 | `cursor/issue-8-watchlist-fingerprint-6e50` → 1313a9a（ff） | 验收通过（CI 42766298688）；全量 1843 通过；曾试按币数生成“三币等权”措辞，因超出范围回退，记入 roadmap |
| 2026-11-10 | #14 | `cursor/issue-14-write-token-6e50` → f04a466（ff） | 验收通过（CI 42767234724）；全量 1845 通过；手工对真 uvicorn：401/401/200，预检含 Authorization |
| 2026-11-10 | #1 | 用户选方案 A；`cursor/issue-1-intraday-signal-retry-6e50` → 4c9fd64（ff） | 全量 1858 通过；等 CI 后关闭 |
