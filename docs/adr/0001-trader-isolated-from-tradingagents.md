# 交易代码放在 `trader/`，不改 `tradingagents/`

评级换算、模拟账本、调度和告警都写在仓库顶层的 `trader/` 下，只通过公开接口（`TradingAgentsGraph.propagate` 和配置项）使用 `tradingagents`，不修改 `tradingagents/` 下的任何文件。原因有两个：这个 clone 直接跟踪上游，而上游更新频繁，不改它，拉更新时就不会和交易代码冲突；验证期内也能把研判部分整体固定在一个 commit 上。代价是拿不到研判过程中的结构化字段，入场价、止损等只存在于 markdown 里。这些字段本来也不用于执行（见 0003）。

## 例外（登记）

例外有三处。每次同步上游时用 `git diff origin/main -- tradingagents/` 核对只剩这三处，上游收了同等修复就去掉对应的一处；应向上游提 PR。其他任何对 `tradingagents/` 的改动仍不允许（Issue #6，2026-11-10）。

1. `tradingagents/dataflows/vendors/yahoo/news.py` 里的 3 行（`2a75a03`，2026-11-03）：`get_news_yfinance` 读 Yahoo quote feed 报 `VendorUnavailableError` 时按空 feed 处理，继续走上游已有的 Yahoo 搜索回退（上游 `4429078` 只覆盖“feed 为空”，不覆盖“feed 报错”）。不这样改，行情源抖动一次就会让一个币当天的研判失败；这是失败路径上的容错，不改变研判的输入构成。改动有测试（`tests/test_news_lookahead.py`、`tests/test_yahoo_rate_limit.py`）。
2. `tradingagents/dataflows/vendors/reddit.py`（`5ac03cb`，2026-11-13，Issue #52）：Reddit 的搜索 RSS 从 2026-11-11 起对匿名请求返回 403，三次日频研判的社媒情绪没有 Reddit 数据，上游没有修。改读最新帖子列表（`/r/<a+b+c>/new.rss`），在本地按是否提到标的过滤；函数签名和抓取失败时的占位符不变，`sentiment_analyst.py` 不改。和第 1 处不同，这一处改的是整条取数路径，Reddit 这一路输入的构成也变了：从“过去 7 天里搜到的帖子”变成“最新 100 条里自己版块的和提到标的的帖子”，往回 1 到 5 天；每个版块给模型的仍是最新 5 条。按 ADR 0004 算修复坏掉的数据源，不算加数据源：验证期不重置，指纹照常记一次代码变更。验证期内 Reddit 这一路分三段，以后归因时要知道：交易日 11-06 至 11-09 是搜索结果，11-10 至 11-12 没有数据，11-13 起是列表（11-13 13:19 UTC 部署）。改动有测试（`tests/test_reddit_fallback.py`、`tests/test_social_lookahead.py`）；上游修好搜索或换了取数方式，就换回上游的实现。
3. `tradingagents/dataflows/vendors/yahoo/market.py` 里指标表的一句提示语（`69d9edb`，2026-11-17，Issue #53 的后续）：指标表（`get_stock_stats_indicators_window`，以及它逐日回退时用的 `get_stock_stats`）把数据源没有日线的日期一律写成「N/A: Not a trading day (weekend or holiday)」。币天天交易，这句话对币不成立；Yahoo 在 UTC 零点后几小时内不给刚结束那天的日线（#53），00:05 那次研判的指标表里研判日那一行每次都是这句话。改成只说看到的事实：「N/A: no daily bar from the data source for this date」，研判日当天那一行再加「(it may not be published yet)」。只改这句文字：取数、指标计算、函数签名都不变，提示词不改。按 ADR 0004 算修 bug：验证期不重置，指纹照常记一次代码变更。这个函数股票也用，股票周末和节假日那几行从此也只说没有日线。改动有测试（`tests/test_indicator_missing_bar.py`）；上游改了这句话，就换回上游的实现。

## Considered Options

- 直接改 `tradingagents/` 内部：能拿到结构化字段，但每次拉上游都可能冲突，验证期内也难以冻结研判部分。
- 另开独立仓库：隔离最彻底，但要多维护一套依赖和环境。
