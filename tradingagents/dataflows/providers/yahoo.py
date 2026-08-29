"""
Yahoo Finance data provider.

Wraps yfinance to provide OHLCV, fundamentals, and financial statements
for US and global markets.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from .base import DataProvider
from ..symbol_utils import normalize_symbol
from ..stockstats_utils import yf_retry


class YahooProvider(DataProvider):
    """Yahoo Finance data provider."""

    @property
    def name(self) -> str:
        return "yahoo"

    @property
    def supported_markets(self) -> list[str]:
        return ["US", "GLOBAL", "CRYPTO"]

    def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from Yahoo Finance."""
        try:
            canonical = normalize_symbol(symbol)
            ticker = yf.Ticker(canonical)

            # yfinance treats end as EXCLUSIVE
            from dateutil.relativedelta import relativedelta
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_inclusive = (end_dt + relativedelta(days=1)).strftime("%Y-%m-%d")

            data = yf_retry(lambda: ticker.history(
                start=start_date,
                end=end_inclusive,
                interval=interval,
            ))

            if data.empty:
                return None

            # Remove timezone info
            if data.index.tz is not None:
                data.index = data.index.tz_localize(None)

            # Round numeric columns
            numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
            for col in numeric_columns:
                if col in data.columns:
                    data[col] = data[col].round(2)

            return data

        except Exception as e:
            print(f"Error fetching OHLCV from Yahoo for {symbol}: {e}")
            return None

    def get_fundamentals(self, symbol: str) -> Optional[dict]:
        """Fetch company fundamentals from Yahoo Finance."""
        try:
            canonical = normalize_symbol(symbol)
            ticker_obj = yf.Ticker(canonical)
            info = yf_retry(lambda: ticker_obj.info)

            if not info:
                return None

            fields = {
                "name": info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "pe_ratio_ttm": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "eps_ttm": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "week_52_high": info.get("fiftyTwoWeekHigh"),
                "week_52_low": info.get("fiftyTwoWeekLow"),
                "day_50_avg": info.get("fiftyDayAverage"),
                "day_200_avg": info.get("twoHundredDayAverage"),
                "revenue_ttm": info.get("totalRevenue"),
                "gross_profit": info.get("grossProfits"),
                "ebitda": info.get("ebitda"),
                "net_income": info.get("netIncomeToCommon"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "return_on_assets": info.get("returnOnAssets"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "book_value": info.get("bookValue"),
                "free_cash_flow": info.get("freeCashflow"),
            }

            # Filter out None values
            return {k: v for k, v in fields.items() if v is not None}

        except Exception as e:
            print(f"Error fetching fundamentals from Yahoo for {symbol}: {e}")
            return None

    def get_financial_statement(
        self,
        symbol: str,
        statement_type: str,
        freq: str = "quarterly",
    ) -> Optional[pd.DataFrame]:
        """Fetch financial statements from Yahoo Finance."""
        try:
            canonical = normalize_symbol(symbol)
            ticker_obj = yf.Ticker(canonical)

            if statement_type == "balance_sheet":
                data = yf_retry(
                    lambda: ticker_obj.quarterly_balance_sheet
                    if freq == "quarterly"
                    else ticker_obj.balance_sheet
                )
            elif statement_type == "income_statement":
                data = yf_retry(
                    lambda: ticker_obj.quarterly_income_stmt
                    if freq == "quarterly"
                    else ticker_obj.income_stmt
                )
            elif statement_type == "cashflow":
                data = yf_retry(
                    lambda: ticker_obj.quarterly_cashflow
                    if freq == "quarterly"
                    else ticker_obj.cashflow
                )
            else:
                return None

            if data is None or data.empty:
                return None

            return data

        except Exception as e:
            print(f"Error fetching {statement_type} from Yahoo for {symbol}: {e}")
            return None
