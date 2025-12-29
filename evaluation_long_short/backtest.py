"""
Backtesting engine for TradingAgents and baseline strategies.

Both TradingAgents and rule-based strategies use identical return calculation logic:
    1. Generate signals/actions: 1 (BUY), 0 (HOLD), -1 (SELL)
    2. Convert actions to positions: 1 (long), 0 (flat)
    3. Calculate returns: strategy_return = position.shift(1) * market_return

This ensures apples-to-apples comparison across all strategies.
"""

import pandas as pd
import numpy as np
from typing import Dict, List
from pathlib import Path
import json


STD_FIELDS = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}


class TradingAgentsBacktester:
    """Backtest engine for TradingAgents framework."""

    def __init__(self, trading_agents_graph, initial_capital=100000, output_dir=None):
        self.graph = trading_agents_graph
        self.initial_capital = float(initial_capital)
        self.name = "TradingAgents"
        self.output_dir = output_dir

    def backtest(self, ticker: str, start_date: str, end_date: str, data: pd.DataFrame) -> pd.DataFrame:
        """
        Backtest TradingAgents with realistic single-asset account simulation.
        Supports long, short, and flat positions with 1× leverage on shorts.
        """
        df = data.loc[start_date:end_date].copy()
        decisions = []
        signals = pd.Series(0, index=df.index, dtype=float)

        print(f"\nRunning TradingAgents backtest on {ticker} from {start_date} to {end_date}")
        print(f"Total trading days: {len(df)}")
        print("-" * 80)

        # === Step 1: Collect signals ===
        for i, (date, row) in enumerate(df.iterrows()):
            date_str = date.strftime("%Y-%m-%d")
            price = float(row["Close"])
            try:
                print(f"\n[{i+1}/{len(df)}] {date_str} ... ", end="")
                final_state, decision = self.graph.propagate(ticker, date_str)
                print(f"Decision: {decision}")
                signal = self._parse_decision(decision)
                decisions.append({"date": date_str, "decision": decision, "signal": signal, "price": price})
            except Exception as e:
                print(f"Error: {e}")
                signal = 0
                decisions.append({"date": date_str, "decision": "ERROR", "signal": 0, "price": price, "error": str(e)})
            signals.loc[date] = signal

        # === Step 2: Run realistic cash+shares backtest ===
        close = pd.to_numeric(df["Close"], errors="coerce")
        cash = self.initial_capital
        shares = 0.0
        prev_value = cash
        records = []

        for i, (date, price) in enumerate(close.items()):
            action = signals.iloc[i]

            # 先计算上一个交易日的组合价值
            portfolio_value = cash + shares * price

            # === 若方向改变，先平仓 ===
            if (shares > 0 and action <= 0) or (shares < 0 and action >= 0):
                cash += shares * price  # 卖出现有股票或回补空头
                shares = 0.0

            # === 建仓逻辑 ===
            if action == 1 and shares == 0:
                # 做多
                shares = cash / price
                cash = 0.0
            elif action == -1 and shares == 0:
                # 做空（1倍杠杆）
                shares = -cash / price
                cash = 2 * cash  # 保证金 + 卖出所得

            # === 更新组合价值 ===
            new_value = cash + shares * price
            daily_return = (new_value / prev_value) - 1 if prev_value != 0 else 0.0
            prev_value = new_value

            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "action": action,
                "shares": shares,
                "close_price": price,
                "cash": cash,
                "portfolio_value": new_value,
                "strategy_return": daily_return,
            })

        # === Step 3: 转为 DataFrame 并计算累计收益 ===
        portfolio = pd.DataFrame(records).set_index("date")
        portfolio["cumulative_return"] = (1 + portfolio["strategy_return"]).cumprod()
        portfolio["ticker"] = ticker
        self.latest_portfolio = portfolio
        self._save_decisions_log(ticker, decisions, start_date, end_date)
        return portfolio

    @staticmethod
    def _actions_to_position(actions: pd.Series) -> pd.Series:
        """
        Convert action series to a long-only position series in {0,1}.
        Same logic as baseline strategies for consistency.
        """
        a = actions.astype(float).fillna(0.0).clip(-1, 1).values
        pos = np.zeros_like(a, dtype=float)
        for i in range(len(a)):
            if i == 0:
                pos[i] = 1.0 if a[i] > 0 else 0.0
            else:
                if a[i] > 0:       # buy → long
                    pos[i] = 1.0
                elif a[i] < 0:     # sell → flat
                    pos[i] = 0.0
                else:              # hold → keep previous
                    pos[i] = pos[i-1]
        return pd.Series(pos, index=actions.index, name="position")

    def _parse_decision(self, decision: str) -> int:
        """
        Parse decision to signal.
        We interpret:
          - contains 'BUY' or 'LONG' -> 1
          - contains 'SELL' or 'EXIT' -> -1  (we use -1 as 'close to cash' here)
          - otherwise HOLD -> 0
        """
        d = str(decision).upper()
        if "BUY" in d or "LONG" in d:
            return 1
        if "SELL" in d or "EXIT" in d or "CLOSE" in d:
            return -1
        return 0

    def _save_decisions_log(self, ticker: str, decisions: List[Dict], start_date: str, end_date: str):
        """
        Save detailed TradingAgents decisions and portfolio state to JSON.
        Adds shares, cash, and cumulative return (cr) from the latest backtest results.
        """
        if self.output_dir:
            out = Path(self.output_dir) / ticker / "TradingAgents"
        else:
            out = Path(f"eval_results/{ticker}/TradingAgents")
        out.mkdir(parents=True, exist_ok=True)
        fp = out / f"decisions_{start_date}_to_{end_date}.json"

        # Try to include computed portfolio metrics if available
        try:
            # Attempt to load the latest portfolio CSV/DF from memory
            if hasattr(self, "latest_portfolio"):
                port = self.latest_portfolio
                port = port.reset_index()
                port_dict = {d["date"]: d for d in port.to_dict(orient="records")}
                # Merge portfolio stats into each decision record
                for d in decisions:
                    date = d["date"]
                    if date in port_dict:
                        d.update({
                            "shares": port_dict[date].get("shares"),
                            "cash": port_dict[date].get("cash"),
                            "portfolio_value": port_dict[date].get("portfolio_value"),
                            "cumulative_return": port_dict[date].get("cumulative_return"),
                        })
        except Exception as e:
            print(f"Warning: could not merge portfolio stats into log ({e})")

        with open(fp, "w") as f:
            json.dump({
                "strategy": "TradingAgents",
                "ticker": ticker,
                "start_date": start_date,
                "end_date": end_date,
                "total_days": len(decisions),
                "decisions": decisions
            }, f, indent=2)

        print(f"  ✓ Saved TradingAgents detailed decisions to: {fp}")


class BacktestEngine:
    """Engine to run and compare multiple strategies."""

    def __init__(self, data: pd.DataFrame, initial_capital: float = 100000):
        self.data = data
        self.initial_capital = float(initial_capital)
        self.results: Dict[str, pd.DataFrame] = {}

    def run_strategy(self, strategy, start_date: str = None, end_date: str = None, label = None) -> pd.DataFrame:
        data_filtered = self.data.loc[start_date:end_date] if (start_date and end_date) else self.data
        print(f"\nRunning {strategy.name}...")
        portfolio = strategy.backtest(data_filtered)
        self.results[label or strategy.name] = portfolio
        return portfolio

    def run_all_strategies(self, strategies: Dict, start_date: str = None, end_date: str = None):
        for name, strategy in strategies.items():
            try:
                self.run_strategy(strategy, start_date, end_date)
                print(f"✓ {name} completed")
            except Exception as e:
                print(f"✗ {name} failed: {e}")

    def get_results(self) -> Dict[str, pd.DataFrame]:
        return self.results


def load_stock_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        import yfinance as yf
        # Normalize accidental ('A','A','P','L') / ['A','A','P','L']
        if isinstance(ticker, (list, tuple)) and all(isinstance(c, str) and len(c) == 1 for c in ticker):
            ticker = "".join(ticker)

        if not isinstance(ticker, str):
            raise ValueError("Pass a single ticker symbol as a string, e.g., 'AAPL'.")

        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if df.empty:
            raise ValueError(f"No data found for {ticker}")
        return df

    except Exception as e:
        print(f"Error loading data: {e}")
        raise

def standardize_single_ticker(df: pd.DataFrame, ticker: str | None = None) -> pd.DataFrame:
    """Return a single-ticker OHLCV DataFrame with simple columns.
       Works with yfinance single or multi-ticker outputs.
    """
    df = df.copy()

    # If columns are MultiIndex (common with multi-ticker yfinance)
    if isinstance(df.columns, pd.MultiIndex):
        # Figure out which level is the field (Open/High/...) and which is ticker
        lvl0 = set(map(str, df.columns.get_level_values(0)))
        lvl1 = set(map(str, df.columns.get_level_values(1)))
        if len(STD_FIELDS & lvl0) > 0:
            field_level, ticker_level = 0, 1
        elif len(STD_FIELDS & lvl1) > 0:
            field_level, ticker_level = 1, 0
        else:
            raise ValueError("Cannot detect OHLCV field level in MultiIndex columns.")

        available = list(pd.Index(df.columns.get_level_values(ticker_level)).unique())

        # Normalize weird ticker inputs like ('A','A','P','L') -> 'AAPL'
        if isinstance(ticker, (list, tuple)) and all(isinstance(c, str) and len(c) == 1 for c in ticker):
            ticker = "".join(ticker)
        if ticker is None:
            if len(available) != 1:
                raise ValueError(f"Multi-ticker DataFrame. Pick one with ticker=..., available={available}")
            ticker = available[0]
        if str(ticker) not in map(str, available):
            raise ValueError(f"Ticker {ticker!r} not in columns. Available: {available}")

        # Slice to that ticker and drop the ticker level
        df = df.xs(ticker, axis=1, level=ticker_level)

    # Map Adj Close -> Close if Close missing
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df = df.rename(columns={"Adj Close": "Close"})

    # Final sanity
    req = ["Open", "High", "Low", "Close"]
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"Data missing columns: {missing}")

    # Ensure 'Close' is a Series (not 1-col DataFrame)
    close = df["Close"]
    if isinstance(close, pd.DataFrame) and close.shape[1] == 1:
        df["Close"] = close.iloc[:, 0]

    return df