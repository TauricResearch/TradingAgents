import logging
import yfinance as yf
import pandas as pd
from langchain_core.tools import tool

_logger = logging.getLogger(__name__)

@tool
def run_strategy_backtest(ticker: str, strategy_type: str, curr_date: str | None = None) -> str:
    """Run a historical backtest for the given ticker over the past 5 years. 
    strategy_type must be either 'macd_crossover' or 'rsi_oversold'.
    Returns the win rate, total return, and max drawdown of the strategy."""
    
    try:
        from tradingagents.dataflows.stockstats_utils import load_ohlcv
        import pandas as pd
        
        if not curr_date:
            curr_date = pd.Timestamp.today().strftime("%Y-%m-%d")
            
        data = load_ohlcv(ticker, curr_date)
        if len(data) < 200:
            return f"Not enough data to backtest {ticker}."
            
        close = data['Close']
        
        trades = []
        in_position = False
        buy_price = 0
        
        if strategy_type == 'macd_crossover':
            # Simple MACD: 12 EMA - 26 EMA, Signal 9 EMA
            exp1 = close.ewm(span=12, adjust=False).mean()
            exp2 = close.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            
            for i in range(1, len(close)):
                if macd.iloc[i] > signal.iloc[i] and macd.iloc[i-1] <= signal.iloc[i-1] and not in_position:
                    buy_price = close.iloc[i]
                    in_position = True
                elif macd.iloc[i] < signal.iloc[i] and macd.iloc[i-1] >= signal.iloc[i-1] and in_position:
                    sell_price = close.iloc[i]
                    trades.append((sell_price - buy_price) / buy_price)
                    in_position = False
                    
        elif strategy_type == 'rsi_oversold':
            # Basic RSI (14 period)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            for i in range(14, len(close)):
                if rsi.iloc[i] < 30 and not in_position:
                    buy_price = close.iloc[i]
                    in_position = True
                elif rsi.iloc[i] > 70 and in_position:
                    sell_price = close.iloc[i]
                    trades.append((sell_price - buy_price) / buy_price)
                    in_position = False
        else:
            return "Invalid strategy_type. Choose 'macd_crossover' or 'rsi_oversold'."
            
        if in_position:
            # close open trade at current price
            trades.append((close.iloc[-1] - buy_price) / buy_price)
            
        if not trades:
            return f"No trades generated for {strategy_type} on {ticker}."
            
        win_rate = sum(1 for t in trades if t > 0) / len(trades)
        total_return = (pd.Series(trades) + 1).prod() - 1
        
        # Max Drawdown estimation on strategy
        cum_ret = (pd.Series(trades) + 1).cumprod()
        running_max = cum_ret.cummax()
        drawdown = (cum_ret - running_max) / running_max
        max_dd = drawdown.min() if not drawdown.empty else 0
        
        return (
            f"Backtest Results for {ticker} using {strategy_type} (5 Years):\n"
            f"- Total Trades: {len(trades)}\n"
            f"- Win Rate: {win_rate:.2%}\n"
            f"- Strategy Total Return: {total_return:.2%}\n"
            f"- Max Drawdown: {max_dd:.2%}"
        )
    except Exception as e:
        _logger.error("Backtest failed for %s using %s: %s", ticker, strategy_type, e, exc_info=True)
        return f"Error running backtest for {ticker}: {str(e)}"
