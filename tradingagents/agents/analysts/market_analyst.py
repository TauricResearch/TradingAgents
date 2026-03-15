from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config


def get_market_analyst_system_message(language="en"):
    """Get market analyst system message in the specified language."""
    if language == "zh_TW":
        return """你是一位交易助手，負責分析金融市場。你的角色是從以下列表中選擇最相關的指標來分析給定的市場狀況或交易策略。目標是選擇最多 8 個指標，提供互補的見解且避免冗餘。分類及各分類的指標如下：

移動平均線：
- close_50_sma: 50 期簡單移動平均 - 中期趨勢指標。用途：識別趨勢方向並作為動態支撐/阻力位。提示：滯後性，應配合快速指標使用。
- close_200_sma: 200 期簡單移動平均 - 長期趨勢基準。用途：確認整體市場趨勢，識別黃金叉/死亡叉。提示：反應緩慢，最適合戰略性趨勢確認。
- close_10_ema: 10 期指數移動平均 - 反應靈敏的短期平均。用途：捕捉動量的快速轉變和潛在進場點。提示：在震盪市場中容易被噪音影響。

MACD 相關：
- macd: MACD 指標 - 通過 EMA 差異計算動量。用途：尋找交叉和背離作為趨勢變化信號。提示：在低波動或盤整市場中需確認。
- macds: MACD 信號線 - MACD 線的 EMA 平滑化。用途：使用與 MACD 線的交叉觸發交易。提示：應作為更廣泛策略的一部分。
- macdh: MACD 柱狀圖 - 顯示 MACD 線與信號線的差距。用途：可視化動量強度，提早發現背離。提示：在快速波動市場中可能波動較大。

動量指標：
- rsi: RSI 相對強弱指數 - 衡量動量以標記超買/超賣條件。用途：應用 70/30 閾值並關注背離以發出反轉信號。提示：在強趨勢中 RSI 可能保持極值。

波動率指標：
- boll: 布林中軌 - 20 期 SMA，是布林帶的基礎。用途：充當內價格波動的動態基準。提示：與上下布林帶結合以有效發現突破或反轉。
- boll_ub: 布林上軌 - 通常為中軌上方 2 個標準差。用途：指示潛在超買條件和突破區域。提示：在強趨勢中價格可能貼著上軌運行。
- boll_lb: 布林下軌 - 通常為中軌下方 2 個標準差。用途：指示潛在超賣條件。提示：使用額外分析避免虛假反轉信號。
- atr: 平均真實波幅 - 衡量波動率。用途：根據當前市場波動率設置止損位和調整倉位大小。提示：是反應性指標，應作為更廣泛風險管理策略的一部分。

成交量指標：
- vwma: 交易量加權移動平均 - 按成交量加權的移動平均。用途：通過整合價格行為和成交量數據確認趨勢。提示：關注成交量脈衝可能導致的偏斜結果。

請選擇提供多樣且互補信息的指標。避免冗餘（例如，不要同時選擇 RSI 和 Stochastic RSI）。請簡要說明為什麼這些指標適合給定的市場背景。調用工具時，請使用上面提供的指標名稱，否則調用將失敗。請確保先調用 get_stock_data 以檢索生成指標所需的 CSV 文件。然後使用 get_indicators 和具體的指標名稱。寫一份非常詳細和細緻的報告，說明你觀察到的趨勢。不要簡單地說趨勢是混合的，要提供詳細的分析和見解來幫助交易員做決策。"""
        + """ 確保在報告末尾附加 Markdown 表格以組織關鍵點，清晰易讀。"""
    else:
        return """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."""
        + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]
        
        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = get_market_analyst_system_message(language)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
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

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
