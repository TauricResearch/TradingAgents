# 评级只表达方向，仓位由代码决定

调用 `propagate` 时不传持仓，评级只当作方向观点。目标仓位、止损和数量全部由 `trader/` 按固定规则计算，以满仓单位计：Buy +1，Overweight +0.5，Hold 维持现仓（沿用项目原定义），Underweight −0.25，Sell −0.5。REVIEW 不动仓，也不开新仓。

不传持仓，是因为研判的 prompt 是按只做多写的，Sell 的原文是 "Exit position or avoid entry"，对空头持仓没有任何指引，把空头传进去，模型无从处理。报告里模型给出的入场价和止损只是 markdown 文本，只记录，不用于执行。

空头先只开半仓，因为 Sell 可能只表示"别持有"。等结算数据证明 Sell 之后确实会跌，再把空头放开到与多头对称。
