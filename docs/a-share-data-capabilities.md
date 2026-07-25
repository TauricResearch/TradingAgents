# A 股补充数据能力

这些接口是研究补充，而不是行情或基本面的替代。每个结果都会标明实际来源；空结果、SDK 缺失、字段变化、限流或未配置的供应商都会返回类型化的不可用状态，不能被解释为“没有事件”。

| 能力 | 路由方法 | 当前来源 | 输入范围 |
|---|---|---|---|
| 资金流、两融 | `get_a_share_capital_flow`、`get_a_share_margin_financing` | EastMoney 公共接口 | 单只 A 股 |
| 交易所公告 | `get_a_share_exchange_announcements` | 上交所/深交所优先，EastMoney 公开备胎 | 单只 A 股 |
| 大宗交易 | `get_a_share_bulk_trades` | AKShare 的公开 EastMoney 适配 | 单只 A 股、日期区间 |
| 股东户数 | `get_a_share_shareholder_counts` | AKShare | 单只 A 股 |
| 限售解禁 | `get_a_share_lockup_releases` | AKShare 的公开 EastMoney 适配 | 单只 A 股、日期区间 |
| 龙虎榜 | `get_a_share_dragon_tiger` | AKShare | 单只 A 股、交易日、买入或卖出 |
| 涨停梯队 | `get_a_share_limit_up_ladder` | AKShare | 交易日；输出当日连板/题材字段计数和成分行 |
| 互动易 | `get_a_share_interactive_questions`、`get_a_share_interactive_answers` | AKShare/CNINFO | 单只 A 股；回答必须给已知问题 ID |
| iWenCai 查询 | `search_a_share_iwencai` | 可选 `pywencai` 客户端 | 自然语言查询 |

当前刻意不把下列内容伪装成已交付能力：

- “炸板率”需要可靠的盘中事件时间序列，当前涨停池只提供公开的日终事实，报告不会估算该指标。
- 财联社电报使用签名客户端契约；没有经过审查的本地签名提供方时，`get_cls_telegraph` 明确返回不可用，不复制或猜测浏览器签名。
- iWenCai 只在用户显式安装兼容的 `pywencai` 时启用；没有该客户端时返回不可用，系统不会抓取网页或制造查询结果。

路由默认把上述数据归为可降级的 A 股补充能力：它们的失败不会使 OHLCV、财务报表或最终研究流程被误判为数据缺失。

## 新闻降级与凭据健康

- 公司新闻默认先尝试配置的 Tavily、Yahoo Finance、Alpha Vantage。对于 A 股，只有这些来源均无可用结果时，才会调用已有的上交所/深交所公开公告适配器；输出会明确标记 `china_exchange`，公告不能被当作完整市场新闻。可通过 `a_share_news_official_fallback_enabled: false` 关闭这条降级链。
- Tavily 可使用单个 `TAVILY_API_KEY`，也可使用逗号分隔的 `TAVILY_API_KEYS`。轮换和冷却按**单个 key**处理：429 冷却 60 秒，5xx 或网络错误冷却 20 秒；401/403 明确报不可用，不会尝试用另一把 key 绕过访问策略。
- 日志、进度事件和健康状态只保留 key 的不可逆短哈希，不记录原始凭据。所有 key 都在冷却时，新闻包会显示来源不可用，而不会制造空新闻或事实结论。
