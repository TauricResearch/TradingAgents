# 优化进度（Issue 驱动）

Issue 在 [kissman911/tradingagents-crypto-trader](https://github.com/kissman911/tradingagents-crypto-trader/issues)。审计报告：[audit-2026-11.md](audit-2026-11.md)。
流程：每个 Issue 一个分支（`cursor/issue-<n>-<slug>-6e50`）→ 改动 + 测试 → ruff / pytest / tsc / oxlint / build → 自审 → 合入 `crypto-trader` → 推 `backup` → 验收通过才关 Issue。
mini 上的部署（`git pull`、`launchctl kickstart`）由用户执行，按 roadmap 的更新流程。

状态：triage 待定方案 · ready 可做 · in-progress 进行中 · blocked 阻塞 · review 待验收 · done 已关闭。

| # | 标题 | 优先级 | 状态 | 依赖 | 方案要点 | 测试/验收 | 阻塞或备注 |
|---|---|---|---|---|---|---|---|
| 1 | 日内信号连续失败（529）处置 | P1 | triage | — | 小时内有界重试 + 连续失败告警 + 看板显示；不改提示词/模型/指纹 | — | 方案待用户确认重试次数/间隔或按推荐执行 |
| 2 | web 在 OKX 不可达时降级 | P1 | ready | — | Market 失败短缓存；overview/equity 行情字段可为 null + `market` 状态；UI 提示 | — | 基线：3 天 1,040 次 500 |
| 3 | mini 关闭睡眠 | P1 | blocked | 用户 | `sudo pmset -a sleep 0` | 用户执行后 `pmset -g` 核对 | 需用户在 mini 执行 |
| 4 | 11-11 结算后核对 | P1 | blocked | 时间 | 核对准确度卡与净值曲线 | — | 11-11 后 |
| 5 | CI 覆盖 crypto-trader | P1 | ready | — | ci.yml 加分支 | Actions 运行通过 | — |
| 6 | ADR 0001 例外回退 | P2 | ready | — | 回退 news.py，等上游 4429078 或 trader 侧兜底 | 研判在 Yahoo 不可用时仍完成 | 改动 tradingagents 指纹会变（代码指纹，不重置验证期） |
| 7 | 定价表过期提示 | P3 | ready | — | UI 高亮 + 维护说明 | — | — |
| 8 | 扩池前置：指纹 + KeyError | P2 | ready | — | 持仓 ∪ 自选池；自选池入指纹 | 单元测试 | 指纹新增字段需不触发重置 |
| 9 | 验证期末分流决策 | P2 | blocked | #4 | 决策模板 | — | 12-05 前 |
| 10 | 清理 worktree/分支，同步文档提交 | P3 | ready | — | 删已合并分支；推 backup | — | 删分支前需用户确认 |
| 11 | 日报 OKX 不可达时降级 | P2 | ready | 措辞同 #2 | meta `marks` + 回退标记价 | 单元测试 | — |
| 12 | ledger 索引/WAL/反向依赖 | P3 | ready | — | 索引 + WAL + 类型内聚 | 单元测试 | WAL 只读连接权限需验证 |
| 13 | events/attempts 分页、research_index 缓存 | P3 | ready | — | limit + mtime 缓存 | 单元测试 | — |
| 14 | 写端点认证 | P2 | ready | — | `TRADER_WEB_TOKEN` Bearer | 单元测试 + 手工 | 部署需用户改 plist |

## 执行记录

| 日期 (UTC) | Issue | 分支/提交 | 结果 |
|---|---|---|---|
| 2026-11-10 | — | 审计报告与本文档 | 基线：ruff 通过、oxlint 0、tsc 通过、441 测试通过 |
