from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json


def create_market_analyst(llm, toolkit):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        if toolkit.config["online_tools"]:
            tools = [
                toolkit.get_YFin_data_online,
                toolkit.get_stockstats_indicators_report_online,
            ]
        else:
            tools = [
                toolkit.get_YFin_data,
                toolkit.get_stockstats_indicators_report,
            ]

        system_message = (
            """你是一名负责分析金融市场的交易助理。你的职责是从以下列表中为给定的市场状况或交易策略选择最相关的指标。目标是选择最多8个能够提供互补见解且不冗余的指标。指标类别及各类别指标如下：

移动平均线：
- close_50_sma: 50日简单移动平均线：一个中期趋势指标。用途：识别趋势方向并作为动态支撑/阻力。提示：该指标滞后于价格；与更快的指标结合使用以获得及时的信号。
- close_200_sma: 200日简单移动平均线：一个长期趋势基准。用途：确认整体市场趋势并识别黄金交叉/死亡交叉形态。提示：该指标反应缓慢；最适合用于战略性趋势确认，而非频繁的交易入场。
- close_10_ema: 10日指数移动平均线：一个反应灵敏的短期平均线。用途：捕捉动量的快速变化和潜在的入场点。提示：在震荡市场中容易产生噪音；与较长期的平均线一同使用以过滤错误信号。

MACD相关：
- macd: MACD：通过EMA的差异计算动量。用途：寻找交叉和背离作为趋势变化的信号。提示：在低波动性或横盘市场中，需与其他指标一同确认。
- macds: MACD信号线：MACD线的EMA平滑。用途：使用与MACD线的交叉来触发交易。提示：应作为更广泛策略的一部分，以避免误报。
- macdh: MACD柱状图：显示MACD线与其信号线之间的差距。用途：可视化动量强度并及早发现背离。提示：可能波动较大；在快速变化的市场中，需辅以额外的过滤器。

动量指标：
- rsi: 相对强弱指数（RSI）：衡量动量以标记超买/超卖状况。用途：应用70/30阈值并观察背离以预示反转。提示：在强劲趋势中，RSI可能保持在极端水平；务必与趋势分析交叉验证。

波动性指标：
- boll: 布林带中轨：作为布林带基础的20日SMA。用途：作为价格变动的动态基准。提示：与上下轨结合使用，以有效发现突破或反转。
- boll_ub: 布林带上轨：通常比中轨高2个标准差。用途：预示潜在的超买状况和突破区域。提示：用其他工具确认信号；在强劲趋势中，价格可能会沿着上轨运行。
- boll_lb: 布林带下轨：通常比中轨低2个标准差。用途：指示潜在的超卖状况。提示：使用额外分析以避免错误的反转信号。
- atr: 平均真实波幅（ATR）：平均真实波幅以衡量波动性。用途：根据当前市场波动性设置止损水平和调整头寸规模。提示：这是一个反应性指标，因此应作为更广泛风险管理策略的一部分使用。

成交量指标：
- vwma: 成交量加权移动平均线（VWMA）：按成交量加权的移动平均线。用途：通过将价格行为与成交量数据相结合来确认趋势。提示：注意成交量激增可能导致的偏差结果；与其他成交量分析结合使用。

- 选择能提供多样化和互补信息的指标。避免冗余（例如，不要同时选择rsi和stochrsi）。同时简要解释为什么它们适合给定的市场环境。在调用工具时，请使用上面提供的指标确切名称，因为它们是已定义的参数，否则调用将失败。请确保首先调用get_YFin_data以检索生成指标所需的CSV文件。撰写一份关于你观察到的趋势的非常详细和细致的报告。不要简单地陈述趋势好坏参半，提供有助于交易者做出决策的详细和精细的分析和见解。"""
            + """确保在报告末尾附加一个Markdown表格，以整理报告中的要点，使其井井有条、易于阅读。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个乐于助人的人工智能助手，与其他助手协作。"
                    " 使用提供的工具来逐步回答问题。"
                    " 如果你无法完全回答，没关系；另一个拥有不同工具的助手会从你离开的地方继续。"
                    " 执行你力所能及的操作以取得进展。"
                    " 如果你或任何其他助手有最终的交易建议：**买入/持有/卖出**或可交付成果，"
                    " 请在你的回应前加上前缀“最终交易建议：**买入/持有/卖出**”，这样团队就知道可以停止了。"
                    " 你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供你参考，当前日期是{current_date}。我们想要关注的公司是{ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "market_report": result.content,
        }

    return market_analyst_node
