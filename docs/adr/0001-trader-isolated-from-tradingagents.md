# 交易代码放在 `trader/`，不改 `tradingagents/`

评级换算、模拟账本、调度和告警都写在仓库顶层的 `trader/` 下，只通过公开接口（`TradingAgentsGraph.propagate` 和配置项）使用 `tradingagents`，不修改 `tradingagents/` 下的任何文件。原因有两个：这个 clone 直接跟踪上游，而上游更新频繁，不改它，拉更新时就不会和交易代码冲突；验证期内也能把研判部分整体固定在一个 commit 上。代价是拿不到研判过程中的结构化字段，入场价、止损等只存在于 markdown 里。这些字段本来也不用于执行（见 0003）。

## Considered Options

- 直接改 `tradingagents/` 内部：能拿到结构化字段，但每次拉上游都可能冲突，验证期内也难以冻结研判部分。
- 另开独立仓库：隔离最彻底，但要多维护一套依赖和环境。
