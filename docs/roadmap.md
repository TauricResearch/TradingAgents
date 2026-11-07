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

  Mac 要保持开机并登录；睡眠时错过的触发会在唤醒后补跑一次。卸载用 `launchctl bootout gui/$(id -u)/com.tradingagents.trader.<job>`。
- [x] 把分支备份到私有仓库 `kissman911/tradingagents-crypto-trader`（远程名 `backup`；`origin` 仍指向上游，用来拉更新）

完成标准：连续 3 天收到日报，账本里有成交和每日净值快照。

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

## 阶段 2：按证据扩展

优先级在验证期结束后再定。候选项：

- 数据：资金费率、持仓量、爆仓、恐惧贪婪指数、链上资金流，以及被屏蔽的 Polymarket。两条路：子类化 graph 把数据追加到标的上下文，或放开 ADR 0001、钉住上游版本后直接改。
- 反应速度：先做不用 LLM 的盘中规则层，比如每小时收紧跟踪止损、按波动率调仓；事件触发的 LLM 重研判放最后。
- 执行：先接 OKX Demo 验证下单流程，再小资金实盘。要新写下单、持仓对账和交易所侧止损，现在的 `okx.py` 只有公开行情。
- 自选池：上游只识别 11 个币，扩充到名单外要改上游。
