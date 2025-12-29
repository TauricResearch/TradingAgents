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
        Backtest TradingAgents using the same return calculation logic as rule-based strategies.
        
        Process:
        1. Collect signals (actions: 1=BUY, 0=HOLD, -1=SELL) for all dates
        2. Convert actions to positions (0=flat, 1=long) using same logic as baselines
        3. Calculate returns as: strategy_return = position.shift(1) * market_return
        """
        # Restrict to window
        df = data.loc[start_date:end_date].copy()
        
        decisions: List[Dict] = []
        signals = pd.Series(0, index=df.index, dtype=float)

        print(f"\nRunning TradingAgents backtest on {ticker} from {start_date} to {end_date}")
        print(f"Total trading days: {len(df)}")
        print("-" * 80)

        # Step 1: Collect all signals/decisions
        for i, (date, row) in enumerate(df.iterrows()):
            date_str = date.strftime("%Y-%m-%d")
            price = float(row["Close"])

            # Get decision from TradingAgents graph
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

        # Step 2: Convert actions to positions (same logic as baseline strategies)
        position = self._actions_to_position(signals)
        
        # Step 3: Calculate returns using standardized logic
        close = pd.to_numeric(df["Close"], errors="coerce")
        market_ret = close.pct_change().fillna(0.0)
        exposure = position.shift(1).fillna(0.0)  # Yesterday's position determines today's exposure
        strat_ret = (exposure * market_ret).astype(float)
        
        cumret = (1.0 + strat_ret).cumprod()
        portval = self.initial_capital * cumret
        
        # Build portfolio DataFrame with same structure as baseline strategies
        portfolio = pd.DataFrame(index=df.index)
        portfolio["action"] = signals                       # 1=BUY, 0=HOLD, -1=SELL
        portfolio["position"] = position                    # 1=long, 0=flat
        portfolio["close"] = close
        if "Volume" in df.columns:
            vol = df["Volume"]
            if isinstance(vol, pd.DataFrame) and vol.shape[1] == 1:
                vol = vol.iloc[:, 0]
            if isinstance(vol, pd.Series):
                portfolio["Volume"] = vol
        portfolio["market_return"] = market_ret
        portfolio["strategy_return"] = strat_ret
        portfolio["cumulative_return"] = cumret
        portfolio["portfolio_value"] = portval
        portfolio["trade_delta"] = portfolio["position"].diff().fillna(0.0)  # +1=buy, -1=sell

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
        # Use output_dir if provided, otherwise use default
        if self.output_dir:
            out = Path(self.output_dir) / ticker / "TradingAgents"
        else:
            out = Path(f"eval_results/{ticker}/TradingAgents")
        out.mkdir(parents=True, exist_ok=True)
        fp = out / f"decisions_{start_date}_to_{end_date}.json"
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