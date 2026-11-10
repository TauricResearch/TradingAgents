# 交易代码放在 `trader/`，不改 `tradingagents/`

评级换算、模拟账本、调度和告警都写在仓库顶层的 `trader/` 下，只通过公开接口（`TradingAgentsGraph.propagate` 和配置项）使用 `tradingagents`，不修改 `tradingagents/` 下的任何文件。原因有两个：这个 clone 直接跟踪上游，而上游更新频繁，不改它，拉更新时就不会和交易代码冲突；验证期内也能把研判部分整体固定在一个 commit 上。代价是拿不到研判过程中的结构化字段，入场价、止损等只存在于 markdown 里。这些字段本来也不用于执行（见 0003）。

## 例外（登记）

唯一的例外是 `tradingagents/dataflows/vendors/yahoo/news.py` 里的 3 行（`2a75a03`，2026-11-03）：`get_news_yfinance` 读 Yahoo quote feed 报 `VendorUnavailableError` 时按空 feed 处理，继续走上游已有的 Yahoo 搜索回退（上游 `4429078` 只覆盖“feed 为空”，不覆盖“feed 报错”）。不这样改，行情源抖动一次就会让一个币当天的研判失败；这是失败路径上的容错，不改变研判的输入构成。条件：改动有测试（`tests/test_news_lookahead.py`、`tests/test_yahoo_rate_limit.py`）；每次同步上游时用 `git diff origin/main -- tradingagents/` 核对只剩这一处，上游收了同等修复就去掉它；应向上游提 PR。其他任何对 `tradingagents/` 的改动仍不允许（Issue #6，2026-11-10）。

## Considered Options

- 直接改 `tradingagents/` 内部：能拿到结构化字段，但每次拉上游都可能冲突，验证期内也难以冻结研判部分。
- 另开独立仓库：隔离最彻底，但要多维护一套依赖和环境。
