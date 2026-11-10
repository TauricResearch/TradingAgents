# 优化进度（Issue 驱动）

Issue 在 [kissman911/tradingagents-crypto-trader](https://github.com/kissman911/tradingagents-crypto-trader/issues)。审计报告：[audit-2026-11.md](audit-2026-11.md)。
流程：每个 Issue 一个分支（`cursor/issue-<n>-<slug>-6e50`）→ 改动 + 测试 → ruff / pytest / tsc / oxlint / build → 自审 → 合入 `crypto-trader` → 推 `backup` → 验收通过才关 Issue。
mini 上的部署（`git pull`、`launchctl kickstart`）按 roadmap 的更新流程，每次由用户授权后才做（2026-11-10 07:19 UTC 用户选“全部部署”，已部署 b228b3b）。

状态：triage 待定方案 · ready 可做 · in-progress 进行中 · blocked 阻塞 · review 待验收 · done 已关闭。

| # | 标题 | 优先级 | 状态 | 依赖 | 方案要点 | 测试/验收 | 阻塞或备注 |
|---|---|---|---|---|---|---|---|
| 1 | 日内信号连续失败（529）处置 | P1 | done | — | 用户选方案 A：瞬时错误同小时内最多再试 2 次、间隔 60 s；连续 2 整点全失败告警 + 恢复通知；ADR 0006 补条 | 4 个新测试 + 分类参数化；CI 42768473571 绿 | 不改提示词/模型/指纹；观察一周“整点最终无信号”比例 |
| 2 | web 在 OKX 不可达时降级 | P1 | done | — | Market 失败短缓存 + 旧值；overview/equity 行情字段可为 null + `market` 状态；其他路径 503；UI 横幅 | 3 个新测试；CI 42763806494 绿 | 基线：3 天 1,040 次 500；改后比例待 mini 部署后观察 |
| 3 | mini 关闭睡眠 | P1 | blocked | 用户 | `sudo pmset -a sleep 0` | 用户执行后 `pmset -g` 核对 | 需用户在 mini 执行 |
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
