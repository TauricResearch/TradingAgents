from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_stock_data,
)
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            """你是一位交易助手，负责分析金融市场。你的任务是从以下列表中选择最适合当前市场状况或交易策略的**最相关指标**。目标是选择最多**8个指标**，以提供互补且不冗余的洞察。各类别及其指标如下：

移动平均线类：
- close_50_sma: 50日简单移动平均线：中期趋势指标。用途：识别趋势方向并作为动态支撑/阻力位。提示：会滞后于价格；结合更快指标以获得及时信号。
- close_200_sma: 200日简单移动平均线：长期趋势基准。用途：确认整体市场趋势并识别黄金交叉/死叉形态。提示：反应较慢；最适合战略趋势确认而非频繁交易入场。
- close_10_ema: 10日指数移动平均线：快速短期均值。用途：捕捉快速动量变化和潜在入场点。提示：在震荡市场中容易产生噪音；与较长均值配合使用以过滤假信号。

MACD相关：
- macd: MACD：通过EMA差异计算动量。用途：寻找交叉和背离作为趋势变化信号。提示：在低波动或横盘市场中用其他指标确认。
- macds: MACD信号线：MACD线的EMA平滑。用途：使用与MACD线的交叉触发交易。提示：应作为更广泛策略的一部分以避免假阳性。
- macdh: MACD柱状图：显示MACD线与其信号线之间的差距。用途：可视化动量强度并早期发现背离。提示：可能波动较大；在快速波动市场中配合其他过滤器使用。

动量指标：
- rsi: RSI：测量动量以标识超买/超卖状态。用途：应用70/30阈值并观察背离以发出反转信号。提示：在强势趋势中RSI可能保持极端；始终与趋势分析交叉验证。

波动性指标：
- boll: 布林带中轨：作为布林带基础的20日简单移动平均线。用途：作为价格运动的动态基准。提示：与上下轨配合使用以有效识别突破或反转。
- boll_ub: 布林带上轨：通常比中轨高2个标准差。用途：标识潜在超买状态和突破区域。提示：用其他工具确认信号；在强势趋势中价格可能沿轨道运行。
- boll_lb: 布林带下轨：通常比中轨低2个标准差。用途：标识潜在超卖状态。提示：使用额外分析以避免假反转信号。
- atr: ATR：平均真实范围以衡量波动性。用途：根据当前市场波动性设置止损位和调整仓位大小。提示：这是反应性指标；作为更广泛风险管理策略的一部分使用。

成交量指标：
- vwma: VWMA：成交量加权移动平均线。用途：通过整合价格走势与成交量数据确认趋势。提示：注意成交量飙升导致的扭曲结果；与其他成交量分析结合使用。

- 选择提供多样化和互补信息的指标。避免冗余（例如，不要同时选择rsi和随机RSI）。同时简要解释为什么它们适合给定的市场背景。在调用工具时，请使用上述提供的指标的确切名称，因为它们是定义的参数，否则您的调用将失败。请确保首先调用get_stock_data获取生成指标所需的CSV数据。然后使用get_indicators获取特定指标名称。撰写一份非常详细和细致的报告，说明你观察到的趋势。提供具体的、可操作的洞察和支持证据，以帮助交易者做出明智的决策。"""
            + """ 请务必在报告末尾附加一个Markdown表格，以组织和便于阅读的方式呈现报告中的关键点。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一位乐于助人的AI助手，与其他助手协作。使用提供的工具来推进回答问题。"
                    " 如果你无法完全回答，没关系；另一位拥有不同工具的助手将帮助你完成未完成的部分。执行你能做的以取得进展。"
                    " 如果你或任何其他助手有最终的**交易提案：买入/持有/卖出**或交付物，"
                    " 请在你的回复前加上 **最终交易提案：买入/持有/卖出**，以便团队知道停止。"
                    " 你可以使用以下工具：{tool_names}。\n{system_message}"
                    "供参考，当前日期是{current_date}。{instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
