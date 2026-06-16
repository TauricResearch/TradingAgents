import pandas as pd
from datetime import datetime
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.symbol_utils import NoMarketDataError

class MarketWatcher:
    def __init__(self, curr_date=None):
        self.curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")

    def fetch_snapshots(self, watchlist):
        # Always fetch watchlist + "SPY"
        tickers_to_fetch = list(watchlist)
        if "SPY" not in tickers_to_fetch:
            tickers_to_fetch.append("SPY")
            
        snapshots = {}
        for ticker in tickers_to_fetch:
            try:
                df = load_ohlcv(ticker, self.curr_date)
                if df is not None and not df.empty:
                    last_row = df.iloc[-1]
                    
                    open_val = float(last_row.get("Open") if "Open" in last_row else last_row.get("open", 0.0))
                    high_val = float(last_row.get("High") if "High" in last_row else last_row.get("high", 0.0))
                    low_val = float(last_row.get("Low") if "Low" in last_row else last_row.get("low", 0.0))
                    close_val = float(last_row.get("Close") if "Close" in last_row else last_row.get("close", 0.0))
                    vol_val = float(last_row.get("Volume") if "Volume" in last_row else last_row.get("volume", 0.0))
                    
                    date_val = last_row.get("Date") if "Date" in last_row else last_row.get("date")
                    if date_val is None:
                        date_val = last_row.name
                    if isinstance(date_val, (pd.Timestamp, datetime)):
                        date_str = date_val.strftime("%Y-%m-%d")
                    elif date_val is not None:
                        date_str = str(date_val)[:10]
                    else:
                        date_str = self.curr_date
                        
                    snapshots[ticker] = {
                        "open": open_val,
                        "high": high_val,
                        "low": low_val,
                        "close": close_val,
                        "volume": vol_val,
                        "date": date_str
                    }
            except (NoMarketDataError, Exception) as e:
                # Isolate exception for each ticker
                pass
                
        return snapshots

class OpportunityScanner:
    def __init__(self, config=None):
        self.config = config or {}

    def score_candidates(self, snapshots):
        # returns candidate dictionaries with score stub, sorted by score descending, excluding SPY
        candidates = []
        for ticker, snapshot in snapshots.items():
            if ticker == "SPY":
                continue
            candidates.append({
                "ticker": ticker,
                "score": 1.0,
                "snapshot": snapshot
            })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates
