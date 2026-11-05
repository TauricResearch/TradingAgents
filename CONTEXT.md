# TradingAgents 智能交易

用 TradingAgents 的多智能体研判，对一个固定的加密货币自选池做每日全自动交易，可以做多、做空和加杠杆。先在模拟盘上验证，再考虑投入真实资金。

## 研判

**Instrument（标的）**:
被研判的单个品种，用 Yahoo 现货代码表示，例如 `BTC-USD`。实际交易的是它对应的 Contract。
_Avoid_: company、股票、币种

**Watchlist（自选池）**:
每次都要研判的固定标的集合，由人手工维护，系统不自行选币。
_Avoid_: universe、股票池

**Trade Date（研判日）**:
一次研判所依据的最后一根已收盘 UTC 日线的日期。按日运行时，它是运行时刻所在 UTC 日的前一天。
_Avoid_: 运行日、今天

**Rating（评级）**:
一次研判对一个标的给出的五档观点：Buy / Overweight / Hold / Underweight / Sell。它是观点，不是交易指令。
_Avoid_: signal、decision、信号

**Review（待复核）**:
研判没有产出可识别评级时的结果，不能据此交易。
_Avoid_: Hold（无法识别不等于持有）

## 执行

**Contract（合约）**:
实际交易的 USDT 本位永续合约，与一个 Instrument 一一对应，例如 BTC 对应 BTC-USDT 永续。
_Avoid_: 标的（标的指研判对象）

**Full Position Unit（满仓单位）**:
单个合约上，止损触发时恰好亏掉固定比例净值的仓位大小，随该合约的波动变化。
_Avoid_: 满仓（不等于投入全部资金）

**Target Position（目标仓位）**:
由评级换算出的某个合约应持有的带方向仓位，以满仓单位计，正为多、负为空。
_Avoid_: 建议仓位

**Order（订单）**:
把当前仓位调整到目标仓位所需的具体买卖指令，包含合约、方向和数量。
_Avoid_: trade、signal

**Kill Switch（熔断）**:
净值从峰值回撤到阈值后全部平仓、停止交易的状态，只能由人手动解除。
_Avoid_: 止损（止损针对单个仓位）

## 验证

**Paper Trading（模拟盘）**:
从当下起按日前向运行，用真实行情做虚拟成交和记账，是判断策略是否有效的主要依据。
_Avoid_: simulation、仿真、Demo

**Demo（演示环境）**:
交易所提供的假资金交易环境，只用来在切换实盘前验证下单流程，不是模拟盘。
_Avoid_: testnet、模拟盘

**Backtest（回测）**:
在历史日期上批量研判，只用来确认流程能跑通，不作为策略有效的证据。

**Settlement（结算）**:
评级发出一段时间后，计算该标的这段时间的原始收益和相对 Benchmark 的 alpha，并写入记忆。

**Benchmark（基准）**:
结算时计算单个评级的 alpha 所参照的品种。加密货币用稳定币作基准，alpha 即相对持有现金的收益。
_Avoid_: Baseline（两者不是一回事）

**Baseline（对照组合）**:
把同一自选池等权买入、从验证期初持有到期末的组合，用来判断策略有没有带来增益。单独持有 BTC 作为次要对照。
_Avoid_: Benchmark

**Rating Accuracy（评级准确度）**:
由结算结果衡量的"评级看得准不准"，不等于组合赚钱。

**Strategy Performance（策略表现）**:
模拟盘或实盘组合扣除 LLM 费用、交易成本和资金费率后的风险调整收益，用 Sharpe 和"年化收益 ÷ 最大回撤"衡量，与 Baseline 按同一口径对比。
