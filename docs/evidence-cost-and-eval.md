# 证据成本分层与决策质量闸门

`tradingagents.dataflows.news_layers` 是新闻处理的无副作用契约：Layer 0 在模型调用前过滤标题缺失、列表文、重复标题和过短摘要；Layer 1 将最多 50 条保留文章压缩为稳定 JSON，并只接受 `+`、`-`、`0`、`?` 四种情绪码；Layer 2 仅在证据不足、来源分歧或高严重度冲突时生成可缓存请求。

这些函数本身不调用供应商或 LLM。`analyze_news_coverage()` 已将它们接入运行时，但两个模型层均为显式 opt-in：默认 `news_layer1_enabled=false`、`news_layer2_enabled=false`，所以没有可用 LLM 或未启用配置时仍走原有顾问/规则降级路径。启用后，Layer 1 只使用既有 quick-LLM 抽象执行一个紧凑情绪批次；Layer 2 只有 `Layer2Trigger.should_run` 为真且本地缓存未命中时才执行深度审阅。`news_layer2_cache_dir` 的内容寻址 JSON 缓存只保存审阅后的公开结论，会递归拒绝 `thinking`、`reasoning`、`chain_of_thought`、`raw_response`、`prompt` 和 `analysis` 字段；不会写入模型私有推理链、原始提示词或原始响应。

`tradingagents.evaluation.source_alignment` 将不同来源的归一化结论投影为 Bullish、Bearish、Tight alignment、Wide divergence、Mixed 或 No coverage。`tradingagents.evaluation.contradictions` 是独立的评估硬闸门：看多却卖出、看空却买入、弃权却采取方向性动作均直接得到 0 分。CSV fixture 要求 target 与 judge 模型名不同；真正的 judge 调用应在该校验之后由外层执行。

这些记录是结论、来源和规则结果，绝不保存模型私有推理链或原始提示词。
