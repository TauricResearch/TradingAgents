# 路线图

目标：一个根据新闻、行情、宏观数据等自动交易的程序。第一版是 `trader/`：按日研判固定的加密货币自选池，在 OKX 永续合约的模拟盘上做多做空。决策方式和边界见 ADR 0001～0004，术语见 `CONTEXT.md`。

## 阶段 0：让第一版跑起来

- [x] OKX 行情客户端：K 线、资金费率、合约规格、最新价，带重试和翻页保护
- [x] daily 第一次回放的告警立即发送；06:05 UTC 加第三个补跑时点
- [x] 模型单价没配置时告警
- [x] 在 `.env` 里填 `TRADER_CAPITAL`、`TRADER_PRICE_DEEP`、`TRADER_PRICE_QUICK`、`TRADER_TELEGRAM_TOKEN`、`TRADER_TELEGRAM_CHAT_ID`（模板见 `deploy/trader.env.example`）
- [x] `python -m trader init`，然后装 `deploy/` 下的两个 launchd agent（在仓库目录执行；systemd 单元留给 Linux 服务器）：

  ```sh
  mkdir -p ~/Library/Logs/trader ~/Library/LaunchAgents
  for job in daily mark; do
    sed -e "s|@REPO_DIR@|$PWD|g" -e "s|@HOME@|$HOME|g" \
      deploy/com.tradingagents.trader.$job.plist > ~/Library/LaunchAgents/com.tradingagents.trader.$job.plist
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tradingagents.trader.$job.plist
  done
  ```

  Mac 要保持开机并登录；睡眠时错过的触发会在唤醒后补跑一次。卸载用 `launchctl bootout gui/$(id -u)/com.tradingagents.trader.<job>`。plist 改了要先 bootout 那个代理，再按上面生成并 bootstrap。daily 每小时 :05 运行到 12:05 UTC：00:05 那次研判，之后各小时给研判时 Yahoo 还没给出研判日日线的币重跑，并补跑失败的运行；模拟盘等重跑完才执行、发日报（#53，ADR 0002）。
- [x] 把分支备份到私有仓库 `kissman911/tradingagents-crypto-trader`（远程名 `backup`；`origin` 仍指向上游，用来拉更新）

完成标准：连续 3 天收到日报，账本里有成交和每日净值快照。

### 运行位置：Mac mini（2026-11-07 迁入）

三个 launchd 代理跑在 `macmini`（`~/Projects/TradingAgents`，用户 `kissman`，自动登录），账户目录 `~/.tradingagents/trader/` 从笔记本完整复制，验证期连续。笔记本上的三个代理已 `launchctl disable`，账户目录保留为 11-07 03:07 UTC 的快照；两台机器不能同时跑同一个账户。

- 仓库用只读部署密钥拉取（`core.sshCommand` 已配）。更新流程：本地提交并推到 `backup`，然后 `ssh macmini 'cd ~/Projects/TradingAgents && git pull -q && uv pip install -q --python .venv/bin/python -e ".[dev,web]"'`；前端改了要在本地 `npm run build` 后 `rsync -a --delete web/ui/dist/ macmini:~/Projects/TradingAgents/web/ui/dist/`，再 `launchctl kickstart -k gui/$(id -u)/com.tradingagents.trader.web`。
- `.env` 单独用 scp 同步，不进 git。
- 备份：在仓库目录 `.venv/bin/python -m trader backup <目录>`，在 `<目录>/<UTC 时间>/` 下放各账本的一致快照（日频、日内、demo、live，有哪个备份哪个；SQLite 备份 API，不阻塞正在跑的作业）和 `settings.json`、`memory/`；`--with-logs` 连研究记录一起。账本是 WAL 模式（Issue #12），最近的提交在 `ledger.sqlite-wal` 里，只 `cp ledger.sqlite` 会丢数据。定时和异地存放自定；恢复时先停所有会写账本的 launchd 代理（daily、mark、intraday、demo，以后还有 live），再把快照目录的内容拷回 `~/.tradingagents/trader/`（Issue #15、#38）。备份只拷清单里的东西，live 的密钥文件不在里面，换机器或恢复后要单独放回去（ADR 0010）。
- 日志在 mini 的 `~/Library/Logs/trader/`。看板只绑 mini 本机回环，tailnet 里的设备够不到 8000 端口。手机和其他设备走 `tailscale serve`：已在 mini 上执行 `/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg 8000`（配置由 Tailscale 保存，只对 tailnet 可见，不是 funnel），访问 `https://kissmanmac-mini.tailffe2e0.ts.net`，不带端口；关掉用 `tailscale serve --https=443 off`。也可以 `ssh -L 8000:127.0.0.1:8000 macmini` 转发。看板没有登录；在 mini 的 `.env` 里设 `TRADER_WEB_TOKEN`（任意长随机串）并 kickstart web 后，`POST /api/settings/llm` 必须带 `Authorization: Bearer <令牌>`，设置页会要令牌（只存在浏览器标签页里）；不设则 tailnet 里 ACL 放行的设备都能调它（ADR 0007，Issue #14）。
- mini 已关闭睡眠：`pmset -g` 和 `pmset -g custom` 都是 `sleep 0`（Issue #3，2026-11-13 核对）。

## 阶段 1：验证期，4 到 8 周

`trader/settings.py` 里的策略常数和研判输入都不动。每周看一次 `python -m trader report`，关注四个数字：

- 各档评级的命中率和相对 USDC 的平均 alpha，即评级准确度
- 扣掉 LLM 费用后的 Sharpe 与年化/回撤，对照三币等权持有和 BTC 单持，即策略表现
- 每月 LLM 费用；预算上限在观察满 7 天后自动定下
- 研判失败的频率；连续两天有币失败会告警

期末按证据分流：

- Sell 之后确实下跌：把空头放开到与多头对称（ADR 0003 预留了这一步）
- 评级没有预测力：先换模型或停掉，不加数据
- 有预测力：进入阶段 2

## 看板（验证期内并行）

产品的终点是替用户在交易所实盘操作（见下）。验证期内先做不依赖验证结果的部分：FastAPI 只读 API + React 看板，对着现在这一个模拟盘账户，API 从第一天带 `account_id`（ADR 0005）。

- [x] `web/api`：只读 API（账户、总览、净值曲线、成交、资金费、研判记录、评级准确度）
- [x] `web/ui`：总览 / 研判 / 历史三个页面（`cd web/ui && npm install && npm run build`）
- [x] 常驻运行：`deploy/com.tradingagents.trader.web.plist`，安装方式同另外两个 agent，服务在 http://127.0.0.1:8000；手机经 Tailscale 访问，不暴露公网
- [ ] 评级结算后核对准确度卡和净值曲线（11-11 前后）

## 日内账户（第二个模拟盘，与日频并行）

设计见 ADR 0006。共享骨架已在起点分支：`trader/intraday/{__init__,settings,types}.py`。票按轮派给独立 worktree 的执行会话，由指挥会话验收合并。

| 票 | 内容 | 档 | 状态 |
|---|---|---|---|
| T1 | 日内引擎与任务：`rules.py` 加可选参数、`ledger.py` 加 `signals` 表、`Settings` 加日内路径、`trader/intraday/{paper,job,report}.py`、CLI `python -m trader intraday init\|run\|report\|resume`、launchd plist、测试 | A | 已合 `45986ad` |
| T2 | 日内信号：`trader/intraday/signal.py`（深度模型单次调用，输入当天研判 + OKX 日内数据，输出 SignalResult）、`okx.py` 加 `funding_rate`/`open_interest`、测试 | A | 已合 `5a8517f` |
| T3 | 看板接入第二账户：账户切换、`/api/accounts/{id}/signals`、信号页 | B | 已合 `9f9406d`、`ae8c8cc`、`15c011e`、`ea0400e`；2026-11-07 15:56 UTC 随 T6、T7 部署到 mini |
| T4 | 部署到 mini：init 日内账户、装 plist、核对首小时运行 | — | 完成（2026-11-07 05:29 UTC 首次运行，三币 Flat，$0.13） |

## Demo 账户（第三个账户：跟随日内信号在 OKX 模拟盘真实下单）

设计见 ADR 0008，代码在 `trader/okx_private.py`（私有接口客户端，只能连模拟盘）和 `trader/demo/`（对账、下单、交易所侧止损、作业、报告）。票：#19 客户端、#20 执行器、#21 看板、#22 并行验收。

- 在 OKX「模拟交易」里建一个只勾“交易”权限的 API，把三个变量写进 `.env`（名字见 `deploy/trader.env.example`，值不进 git、不进日志），`python -m trader demo check` 看账户模式、余额、持仓，并探一次交易权限（key 的交易权限要勾到加密货币/永续合约，否则到下单才报 50123；账户模式要合约模式或跨币种保证金）。
- `python -m trader demo init`：要求模拟账户没有持仓和挂单，本金取账户的 USDT 钱包余额，持仓模式切单向、三个合约设全仓 3×。
- 装 launchd 代理，方式同前（`for job in demo`）：每小时 :10 运行 `python -m trader demo run`，等日内账户 :03 的决定最多 15 分钟；等不到本小时不交易。等到之后再读一次现价，订单和止损按它算；现价或 ATR 不是大于 0 的有限数的币本小时不交易、止损也不按它调整，并告警；成交后单币仓位名义超过净值的单不下（防算错），只减仓的单不拦，反手按反手后的仓位算（#39）。止损挂在交易所，程序不在线也会触发；下次运行对账时按成交入账，当次就发通知：合约、张数、成交均价、按开仓均价算的扣费后盈亏（#36）。
- 日常：`demo sync` 只读交易所入账、打印持仓和问题；`demo report` 看绩效；`demo halt` 停止交易并市价平掉全部仓位（先确认，加 `--yes` 不问）；`demo pause [--note 原因]` 人工暂停：不下新单、不平仓，仓位和止损单原样留着，`demo resume` 解除（#54）；熔断后在交易所确认平干净，`demo resume --kill` 解除（交易所里还有仓位就拒绝，并再发一次平仓），不加 `--kill` 的 `demo resume` 只解除暂停。读不到 USDT 余额时这次运行按出错处理并告警，不当成净值 0。运行失败按错误类型告警（异常类型加 OKX 错误码或 HTTP 状态）：同一类 6 小时最多一次，新的一类立即发；账本里有持仓、或上次对账那个小时有没确认成交的单时，每次失败都报。Telegram 没收到的消息留在账本里（最多 50 条），下一次运行先补发并注明原本几点该发；失败告警等补发成功才开始计 6 小时（#36）。杠杆/保证金模式不对、持仓与成交推算不符时本小时不下单并告警，每个问题 6 小时最多提醒一次。程序解释不了的变化让账户暂停（#34）：非程序成交（含强平）、成交、资金费和出入金以外的余额变动（账单认不出，或转账后账户变成零、从零开始转入）、到下一个整点还对不上的持仓。暂停时不下新单，仓位和止损原样留着，每小时照常对账并记下本该下的单；每个原因告警一次，日报每天列出；回撤到线只告警。转入转出（OKX 的划转账单）记成出入金，提醒一次、不暂停：回撤、熔断和收益率按份额净值算（时间加权），不算这笔钱；看板的本金是投入的本金，日报和 `demo report` 写明出入金（#40）。查明后 `demo resume` 解除：它先对一次账，有新原因、原因还在（持仓仍对不上）、或回撤已到熔断线就不解除，并说明原因。持仓一直对不上（比如交易所晚报了一笔成交，每小时的对账已经读不到）时，先用 `demo reconcile` 修复账本（#37）：只在暂停或熔断时能用，从开户起（交易所只保留三个月）重读成交和资金费，补上漏记的；补完仍对不上的差额列出来，人确认后按最近一次对账读到的交易所持仓记成“调整”成交（不收手续费，日报和看板单独标出）。它只读交易所、只写账本，不解除暂停，之后照常 `demo resume`。

## 实盘账户（第四个账户：用真钱跟随日内信号，小额、带期限）

设计见 ADR 0010（用户 2026-11-13 决定，不等 #22 的报告和验证期结论）。它是一次验证执行链路的实验，不是对 Signal 的押注：

- 独立子账户先入 500 USDT，上限 2,000（2026-11-26 用户解除了净值上限，见 ADR 0010 文末）；跟随日内 Signal，规则和交易所设置同 demo。
- 跑到 2026-12-05，期间熔断一次就不再解除；到期按三方对照报告和验证期结论决定去留。
- 账户建立时处于暂停，这个阶段叫影子运行：照常对账、记录本该下的单、不下单。第一次解除暂停即解锁。
- 解锁的条件：第 1、2 档的票合入，mini 关闭睡眠（#3），mini 上设 `TRADER_WEB_TOKEN`。演练（#42）要做，但不卡解锁。
- 密钥和核对（#30）：live 的密钥放在 mini 的 `~/.config/tradingagents/okx-live.env`（权限 600，三行，格式见 `deploy/trader.env.example`；路径可用 `TRADER_OKX_LIVE_KEY_FILE` 改），不进 `.env`。`python -m trader live check` 只读核对账户模式、key 的权限、是不是子账户、有没有绑定 IP、余额、持仓和实际费率；加 `--base-url https://www.okx.com` 可以对比另一个域名。
- live 账户（#31）：`python -m trader live init` 只读建账，要求子账户空仓、没有条件单、有 USDT，确认是主账户的 key 就拒绝；建好即暂停，不改交易所的设置。装 launchd 代理方式同前（`for job in live`）：每小时 :10 运行 `python -m trader live run`，和 demo 用同一个执行器，暂停期间是影子运行。装之前要有密钥文件、`live init` 建好的账户，和 `.env` 里的 `TRADER_LIVE_HEARTBEAT_URL`（外部监控服务给的地址，每次运行正常结束后请求一次，2 小时收不到由那边通知；没设就不发）。日常：`live sync` 只读对账，`live report` 看绩效和影子运行按小时记下的单；`live resume` 解除暂停，第一次就是解锁：要求设了 `TRADER_WEB_TOKEN`、交易权限确立，和 `demo resume` 一样先对一次账（#34 打开了 `trader/live/account.py` 的 `UNLOCK_OPEN`）。持仓对不上时先用 `live reconcile` 修复账本，再 `live resume`（同 `demo reconcile`，#37）。live 另在代码或 Signal 的指纹变了时暂停：每次部署改了 `trader/` 都会暂停一次，部署后要 `live resume`；下单后单币仓位名义超过 4,000 USDT 拒单，只减仓的单不拦（#39）；净值不设上限（2026-11-26 解除），净值过了 4,000 USDT 后单币上限可能拦下开仓和反手的单（见 ADR 0010 文末）。`live halt` 停止并平仓，暂停中也能用；live 熔断一次就不再解除（`live resume --kill` 一律拒绝），实验到此结束。只想先停下来、不平仓时用 `live pause [--note 原因]`（#54）：加一个人工暂停的原因、提醒一次，之后按暂停处理，`live resume` 解除。各账户的 Telegram 消息前面带账户名（【demo】、【live】）。看板（#41）在 live 的账本建好后列出它：顶栏和每一页都标着「真钱」，显示影子运行、暂停原因或熔断，历史页能和日内、demo 对照；看板的读接口不要认证，tailnet 里的设备都能看到 live 的余额和持仓，要不要加访问控制由用户决定（ADR 0010）。

| 档 | 票 | 内容 | 状态 |
|---|---|---|---|
| 1 影子运行之前 | #30 | 私有接口客户端的正式环境开关、单独的密钥文件、`live check` | 已合 `ad6e8c4`，Python 3.14 上的修复 `03f9bb6`；2026-11-13 在 mini 上跑过 `live check`：两个域名结果一致，没有警告 |
| 1 | #31 | live 账户、生来暂停的影子运行、带账户名的告警、外部心跳 | 已合 `9c0ba2c`；2026-11-13 已部署，`live init` 建账（本金 500.00 USDT），影子运行从 11:10 UTC 开始，满 24 小时后核对 |
| 2 解锁之前 | #32 | 止损单更新期间不留空窗，成交后挂不上止损就平仓 | 已合 `68d68f2`；在演示环境上实测归 #42 |
| 2 | #33 | 熔断做扎实、`halt`（停止并平仓）、余额读不到按出错处理 | 已合 `d091e1d`；2026-11-13 已部署；在演示环境上演练 `halt` 归 #42 |
| 2 | #34 | 暂停状态和触发条件（demo 同样生效）、live 的指纹暂停和两个绝对上限；最后合入，打开解锁 | 已合 `94121a3`，解锁开关已打开；2026-11-13 已部署，mini 已关闭睡眠（#3），`TRADER_WEB_TOKEN` 已设；2026-11-14 12:28 UTC 已解锁 |
| 2 | #50 | 止损在交易所触发的成交按订单上的止损单编号归因（原来记成“非程序”，#34 之后会误暂停账户） | 已合 `0c946e7`；2026-11-13 已部署，demo 账本里 9 笔的原因已更正 |
| 用户 | #35 | 子账户、密钥、入金、mini 设置、心跳服务 | 密钥、入金和 mini 设置已完成（2026-11-13 核对）；2026-11-14 12:28 UTC 已解锁，心跳地址已设（2026-11-16 核对）；还剩追加入金之前的两项和到期的决定 |
| 3 解锁之后 | #36 | 止损成交即时通知、失败告警按类型限频、发送失败后补发 | 已合 `a336c3b`；2026-11-13 已部署 |
| 3 | #37 | 对不上账的修复命令（`demo reconcile` / `live reconcile`） | 已合 `b607713`；2026-11-13 已部署 |
| 3 | #38 | `trader backup` 包含 demo 和 live 的账本 | 已合 `4cf5e54` |
| 3 | #39 | 下单前的输入检查、顶格仓位的正常反手不再被拒 | 已合 `e619c9e`；2026-11-13 已部署 |
| 3 | #40 | 出入金记账（第二次入金之前必须完成） | 已合 `f08ef36`；收益率按时间加权（口径待用户确认）；2026-11-13 已部署；演示环境实测划转归 #42 |
| 3 | #41 | 看板显示 live 账户 | 已合 `c866e2b`；2026-11-13 已部署；读接口是否加访问控制等用户决定 |
| — | #42 | 在演示环境上演练执行器（不卡解锁，避开 #22 的观察期） | 第 1、2 档已合；等 #22 的观察期过去和用户授权 |
| — | #43 | 到期报告和去留决定 | 2026-12-05 |

顺序：#30 和 #32 可以同时开工：两张都会动 `trader/okx_private.py`，但在不同的小节，提示词里划了界。#31、#32、#33、#34 都改 `trader/demo/account.py` 和 `trader/demo/job.py`，这四张依次做，#34 最后。影子运行在 #31 部署后就能开始，用只读密钥提前暴露正式环境和演示环境的差别。

第 1 轮（2026-11-12 UTC，起点 `034961d`）：#30 → 分支 `cursor/issue-30-live-client-6e50`，worktree `../TradingAgents.worktrees/issue-30-live-client`；#32 → 分支 `cursor/issue-32-stop-no-gap-6e50`，worktree `../TradingAgents.worktrees/issue-32-stop-no-gap`；#38 → 分支 `cursor/issue-38-backup-ledgers-6e50`，worktree `../TradingAgents.worktrees/issue-38-backup-ledgers`。执行会话是 Cursor 里的 Task 子代理，worktree 由指挥会话手工建。报告目录 `~/.commander/TradingAgents/`，会话 id 和交接事项记在那里的 `live-rounds.md`。第 1 轮三张都已合入：#38 `4cf5e54`，#30 `ad6e8c4`（Python 3.14 上的修复 `03f9bb6`），#32 `68d68f2`。

#31：分支 `cursor/issue-31-live-account-6e50`，worktree `../TradingAgents.worktrees/issue-31-live-account`，合并 `9c0ba2c`。

## 离线评估（验证期内并行，ADR 0009）

用户 2026-11-10 要求“尽可能把策略做到最好”并选了“先建评估，再按数据改”。代码在 `trader/evaluation/`，命令 `python -m trader evaluate fetch | replay | rerun | signals`，报告在 `docs/reports/`。

- 一期（#27，已完成）：行情缓存、历史市场、用真引擎逐小时回放已记录的日内信号（参数可网格，策略层开关默认关）、信号质量报告。首次对照：回放与线上账本 16 笔成交一一对应、净值差 1.5 bp；3.4 天的样本不足以改参数，结论见 `docs/reports/evaluation-intraday-2026-11-10.md`。
- 二期（#28，前 14 天已出报告）：用同一提示词、同一模型在历史输入（15 分钟 K 线、资金费率历史、持仓量历史）上重跑小时信号，再用一期工具评估。实际约 1 美元/天。10-10 → 10-24 的结论见 `docs/reports/evaluation-rerun-2026-11-11.md`（重跑信号在这段是反向的，线上参数不动）；剩下的 10-24 → 11-06 暂不重跑（11-11 决定），先等线上信号积累（11-07 起，约 11-21 满 14 天）再用一期工具对照；以后要补时先在 .env 配评估专用的 `TRADER_EVAL_BACKEND_URL`、`TRADER_EVAL_API_KEY`，重跑不再与线上共用密钥（ADR 0009）。
- 三期（#29）：日频账户的回放（评级来自研究日志，`Paper` 收进 Params）。
- 每周跑一次默认与候选参数的对照并归档；改线上参数的门槛见 ADR 0009。

## 看板设置：LLM 模型切换（ADR 0007）

| 票 | 内容 | 档 | 状态 |
|---|---|---|---|
| T5 | 官方定价表 `trader/prices.py`：上游目录里各 provider 模型的官方单价（输入/输出，美元每百万 token），带来源 URL 和日期；测试 | B | 已合 `71f48cd`。维护项：`gpt-5.6-sol`/`gpt-5.6` 促销价 2026-11-30 到期、`gemini-3.8-flash` 2026-12-31 到期后改为 $1.50/$7.50；共用 ID 的 provider 存国际站价，DeepSeek 取空闲时段价 |
| T6 | 设置页 `/settings`：当前两档模型与单价、按 provider 分组的模型列表（只列有密钥的）、手填模型 ID 与单价、切换确认（提示验证期重算）、生效状态；对着 API 契约用 mock 开发 | B | 已合 `01e1f4b`；契约加的 `price_note`（促销价截止日）前端显示已补 `718f495`。2026-11-07 15:56 UTC 与 T7、T3 一起部署到 mini（`ea0400e`） |
| T7 | 后端写入面：`trader/overrides.py`（settings.json 读写与历史）、`Settings.from_env` 和 `build_config` 读取覆盖、`GET /api/models`、`POST /api/settings/llm`；测试 | A | 已合 `22eb598`（含返工 `1741e89`：`/api/strategy` 每次重读、契约加 `price_note`） |

第 3 轮（2026-11-07，起点 `904f637`）：T7 → 分支 `t7-llm-settings`，worktree `../TradingAgents.worktrees/t7-llm-settings`。

第 2 轮（2026-11-07，起点 `6aab66f`）：T5 → 分支 `t5-official-prices`，worktree `../TradingAgents.worktrees/t5-official-prices`；T6 → 分支 `t6-settings-ui`，worktree `../TradingAgents.worktrees/t6-settings-ui`。

第 1 轮（2026-11-07，起点 `8c39826`）：T1 → 分支 `t1-intraday-engine`，worktree `../TradingAgents.worktrees/t1-intraday-engine`；T2 → 分支 `t2-intraday-signal`，worktree `../TradingAgents.worktrees/t2-intraday-signal`。报告目录 `~/.commander/TradingAgents/`。

## 阶段 2：按证据扩展

优先级在验证期结束后再定。候选项：

- 数据：资金费率、持仓量、爆仓、恐惧贪婪指数、链上资金流，以及被屏蔽的 Polymarket。两条路：子类化 graph 把数据追加到标的上下文，或放开 ADR 0001、钉住上游版本后直接改。
- 反应速度：先做不用 LLM 的盘中规则层，比如每小时收紧跟踪止损、按波动率调仓；事件触发的 LLM 重研判放最后。
- 执行：先接 OKX Demo 验证下单流程，再小资金实盘。要新写下单、持仓对账和交易所侧止损，现在的 `okx.py` 只有公开行情。**已提前到验证期内并行建设**（用户 2026-11-10 决定）：设计见 ADR 0008，第三个账户 demo 跟随日内信号在模拟盘真实下单；票是 #19（私有接口客户端）、#20（执行器）、#21（看板）、#22（并行验收）。小资金实盘也已提前（用户 2026-11-13 决定），见上面的「实盘账户」一节和 ADR 0010。
- 自选池：验证期内维持 BTC/ETH/SOL（2026-11-07 决定）。扩池的代码准备已完成（Issue #8），等验证期结论：自选池已进两个账户的指纹，换币像换模型一样重启验证期（`check_fingerprint`）；新币在日报里没有 `baseline_ref` 时不计入基线；删币后的持仓不交易、止损照管到平仓。真扩池时还要改 `WATCHLIST`、报告/UI/文档里“三币等权”的措辞，并核对定价表。上游白名单内可直接加的币：XRP、ADA、DOGE、LTC、BCH、DOT、AVAX、LINK（OKX 均有 USDT 永续）；名单外的币要改上游。

## 阶段 3：产品

目标形态是实盘代操作：用户绑定交易所 API 密钥，系统按评级替他下单。前提是阶段 1 证明评级有预测力，并且在接触用户资金前完成法律合规评估（辖区、牌照、条款与风险披露）。中间形态按顺序推进：研判订阅（评级和辩论原文）→ 每人一个模拟账户 → 实盘。

共同的基础工作：用户系统与认证（含 2FA）、密钥加密存储与审计、共享的研判服务（按币 × 天计费，不按用户数）、集中的行情采集、多账户账本（Postgres）、每用户通知渠道、计费、监控与备份、钉住上游版本后自行维护分支（放开 ADR 0001）。
