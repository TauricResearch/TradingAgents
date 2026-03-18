"""Vietnam stock market data provider using vnstock library."""

import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from ...market_registry import MarketProvider
from . import config as vn_config


class VNMarketProvider(MarketProvider):
    market_code = vn_config.MARKET_CODE
    market_name = vn_config.MARKET_NAME
    currency = vn_config.CURRENCY

    def _get_source(self):
        from ...config import get_config
        cfg = get_config()
        return cfg.get("market_config", {}).get("VN", {}).get(
            "vnstock_source", vn_config.DEFAULT_SOURCE
        )

    def _get_cache_dir(self):
        from ...config import get_config
        cfg = get_config()
        cache_dir = cfg.get("data_cache_dir", "data")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _create_stock(self, symbol):
        from vnstock import Vnstock
        return Vnstock().stock(symbol=symbol.upper(), source=self._get_source())

    def get_listed_tickers(self) -> set:
        """Fetch all listed tickers from HOSE/HNX/UPCOM."""
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol="VCB", source=self._get_source())
        df = stock.listing.all_symbols()
        return set(df["symbol"].str.upper().tolist())

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        """Fetch OHLCV data for a VN stock."""
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")

            stock = self._create_stock(symbol)
            data = stock.quote.history(start=start_date, end=end_date)

            if data is None or data.empty:
                return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

            # Rename columns to match yfinance output format
            column_map = {
                "time": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
            data = data.rename(columns=column_map)

            # Round numerical values
            for col in ["Open", "High", "Low", "Close"]:
                if col in data.columns:
                    data[col] = data[col].round(2)

            # Set Date as index for CSV output matching yfinance format
            if "Date" in data.columns:
                data = data.set_index("Date")

            csv_string = data.to_csv()

            header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
            header += f"# Market: Vietnam ({self.currency})\n"
            header += f"# Total records: {len(data)}\n"
            header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            return header + csv_string

        except Exception as e:
            return f"Error fetching VN stock data for {symbol}: {str(e)}"

    def get_indicators(self, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        """Calculate technical indicators using stockstats on vnstock OHLCV data."""
        best_ind_params = {
            "close_50_sma": "50 SMA: Medium-term trend indicator.",
            "close_200_sma": "200 SMA: Long-term trend benchmark.",
            "close_10_ema": "10 EMA: Responsive short-term average.",
            "macd": "MACD: Momentum via differences of EMAs.",
            "macds": "MACD Signal: EMA smoothing of MACD line.",
            "macdh": "MACD Histogram: Gap between MACD and signal.",
            "rsi": "RSI: Overbought/oversold momentum indicator.",
            "boll": "Bollinger Middle: 20 SMA basis for Bollinger Bands.",
            "boll_ub": "Bollinger Upper Band: 2 std dev above middle.",
            "boll_lb": "Bollinger Lower Band: 2 std dev below middle.",
            "atr": "ATR: Average true range volatility measure.",
            "vwma": "VWMA: Volume-weighted moving average.",
            "mfi": "MFI: Money Flow Index using price and volume.",
        }

        if indicator not in best_ind_params:
            raise ValueError(
                f"Indicator {indicator} is not supported. Choose from: {list(best_ind_params.keys())}"
            )

        try:
            curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
            before = curr_date_dt - relativedelta(days=look_back_days)

            # Fetch historical data for indicator calculation (need enough history)
            cache_dir = self._get_cache_dir()
            today_date = pd.Timestamp.today()
            start_date = today_date - pd.DateOffset(years=5)
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = today_date.strftime("%Y-%m-%d")

            cache_file = os.path.join(
                cache_dir, f"{symbol.upper()}-VN-data-{start_date_str}-{end_date_str}.csv"
            )

            if os.path.exists(cache_file):
                data = pd.read_csv(cache_file)
                data["Date"] = pd.to_datetime(data["Date"])
            else:
                stock = self._create_stock(symbol)
                raw = stock.quote.history(start=start_date_str, end=end_date_str)
                if raw is None or raw.empty:
                    return f"No data found for {symbol} to calculate indicators"

                # Normalize column names for stockstats
                data = raw.rename(columns={
                    "time": "Date", "open": "Open", "high": "High",
                    "low": "Low", "close": "Close", "volume": "Volume",
                })
                data.to_csv(cache_file, index=False)

            df = wrap(data)
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

            # Calculate indicator
            df[indicator]

            # Build result for the requested date range
            date_values = []
            current_dt = curr_date_dt
            while current_dt >= before:
                date_str = current_dt.strftime("%Y-%m-%d")
                matching = df[df["Date"] == date_str]
                if not matching.empty:
                    val = matching[indicator].values[0]
                    if pd.isna(val):
                        date_values.append((date_str, "N/A"))
                    else:
                        date_values.append((date_str, str(val)))
                else:
                    date_values.append((date_str, "N/A: Not a trading day (weekend or holiday)"))
                current_dt = current_dt - relativedelta(days=1)

            ind_string = "".join(f"{d}: {v}\n" for d, v in date_values)

            return (
                f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n"
                f"## Market: Vietnam ({self.currency})\n\n"
                + ind_string + "\n\n"
                + best_ind_params.get(indicator, "")
            )

        except Exception as e:
            return f"Error calculating indicators for {symbol}: {str(e)}"

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        """Get company fundamentals overview."""
        try:
            stock = self._create_stock(ticker)

            # Get company overview
            overview = stock.company.overview()
            if overview is None or overview.empty:
                return f"No fundamentals data found for {ticker}"

            # Get financial ratios
            try:
                ratio = stock.finance.ratio(period="quarter")
                has_ratio = ratio is not None and not ratio.empty
            except Exception:
                has_ratio = False

            lines = [
                f"# Company Fundamentals for {ticker.upper()}",
                f"# Market: Vietnam ({self.currency})",
                f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]

            # Overview fields
            row = overview.iloc[0]
            for col in overview.columns:
                val = row.get(col)
                if val is not None and str(val).strip():
                    lines.append(f"{col}: {val}")

            # Financial ratios (latest quarter)
            if has_ratio:
                lines.append("")
                lines.append("## Financial Ratios (Latest Quarter)")
                latest = ratio.iloc[0]
                if isinstance(ratio.columns, pd.MultiIndex):
                    for col in ratio.columns:
                        label = col[-1] if isinstance(col, tuple) else col
                        val = latest[col]
                        if val is not None and str(val).strip() and label not in ("ticker", "yearReport", "lengthReport"):
                            lines.append(f"{label}: {val}")
                else:
                    for col in ratio.columns:
                        val = latest[col]
                        if val is not None and str(val).strip() and col not in ("ticker", "yearReport", "lengthReport"):
                            lines.append(f"{col}: {val}")

            return "\n".join(lines)

        except Exception as e:
            return f"Error retrieving fundamentals for {ticker}: {str(e)}"

    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        """Get balance sheet data."""
        try:
            stock = self._create_stock(ticker)
            period = "quarter" if freq.lower() == "quarterly" else "year"
            data = stock.finance.balance_sheet(period=period)

            if data is None or data.empty:
                return f"No balance sheet data found for {ticker}"

            csv_string = data.to_csv(index=False)
            header = f"# Balance Sheet for {ticker.upper()} ({freq})\n"
            header += f"# Market: Vietnam ({self.currency})\n"
            header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            return header + csv_string

        except Exception as e:
            return f"Error retrieving balance sheet for {ticker}: {str(e)}"

    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        """Get cash flow data."""
        try:
            stock = self._create_stock(ticker)
            period = "quarter" if freq.lower() == "quarterly" else "year"
            data = stock.finance.cash_flow(period=period)

            if data is None or data.empty:
                return f"No cash flow data found for {ticker}"

            csv_string = data.to_csv(index=False)
            header = f"# Cash Flow for {ticker.upper()} ({freq})\n"
            header += f"# Market: Vietnam ({self.currency})\n"
            header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            return header + csv_string

        except Exception as e:
            return f"Error retrieving cash flow for {ticker}: {str(e)}"

    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        """Get income statement data."""
        try:
            stock = self._create_stock(ticker)
            period = "quarter" if freq.lower() == "quarterly" else "year"
            data = stock.finance.income_statement(period=period)

            if data is None or data.empty:
                return f"No income statement data found for {ticker}"

            csv_string = data.to_csv(index=False)
            header = f"# Income Statement for {ticker.upper()} ({freq})\n"
            header += f"# Market: Vietnam ({self.currency})\n"
            header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            return header + csv_string

        except Exception as e:
            return f"Error retrieving income statement for {ticker}: {str(e)}"

    def get_insider_transactions(self, ticker: str) -> str:
        """Get insider transaction data."""
        try:
            stock = self._create_stock(ticker)
            data = stock.company.insider_deals()

            if data is None or data.empty:
                return f"No insider transaction data found for {ticker} on VN market"

            csv_string = data.to_csv(index=False)
            header = f"# Insider Transactions for {ticker.upper()}\n"
            header += f"# Market: Vietnam ({self.currency})\n"
            header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            return header + csv_string

        except Exception as e:
            return f"No insider transaction data available for {ticker} on VN market"

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        """Get news for a VN stock ticker. Delegates to news module."""
        from .news import get_news_vn
        return get_news_vn(ticker, start_date, end_date, source=self._get_source())

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
        """Get global/macro VN market news. Delegates to news module."""
        from .news import get_global_news_vn
        return get_global_news_vn(curr_date, look_back_days, limit)

    def get_market_context(self) -> str:
        return vn_config.MARKET_CONTEXT
