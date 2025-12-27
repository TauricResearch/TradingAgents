"""
Price data service for loading and processing stock price data
"""
import polars as pl
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class PriceService:
    """Service for loading and processing price data from data_cache"""
    
    @staticmethod
    def load_price_data(ticker: str, data_cache_dir: str) -> Optional[pl.DataFrame]:
        """
        Load price data from data_cache CSV files
        
        Args:
            ticker: Stock ticker symbol
            data_cache_dir: Path to data cache directory
            
        Returns:
            DataFrame with price data or None if not found
        """
        try:
            cache_path = Path(data_cache_dir)
            
            # Search for {ticker}-YFin-data-*.csv files
            csv_files = list(cache_path.glob(f"{ticker}-YFin-data-*.csv"))
            
            if not csv_files:
                logger.warning(f"No price data found for {ticker} in {data_cache_dir}")
                logger.info(f"嘗試主動獲取 {ticker} 的價格數據...")
                
                # 主動獲取數據
                df = PriceService._fetch_and_cache_data(ticker, data_cache_dir)
                if df is not None:
                    return df
                else:
                    return None
            
            # Use the most recent file and check if it's still valid (< 24 hours)
            latest_file = max(csv_files, key=lambda p: p.stat().st_mtime)
            
            if not PriceService._is_cache_valid(latest_file):
                logger.info(f"{ticker} 緩存過期，重新獲取數據...")
                df = PriceService._fetch_and_cache_data(ticker, data_cache_dir)
                if df is not None:
                    return df
                # 如果獲取失敗，使用舊緩存
                logger.warning(f"使用過期緩存作為備援")
            
            logger.info(f"Loading price data from {latest_file}")
            
            df = pl.read_csv(str(latest_file))
            df = df.with_columns(pl.col("Date").str.to_datetime())
            
            return df.sort("Date")
            
        except Exception as e:
            logger.error(f"Error loading price data for {ticker}: {e}")
            return None
    
    @staticmethod
    def _is_cache_valid(file_path: Path, max_age_hours: int = 24) -> bool:
        """
        Check if cache file is still valid based on modification time
        
        Args:
            file_path: Path to the cache file
            max_age_hours: Maximum age in hours before cache is considered stale
            
        Returns:
            True if cache is valid, False otherwise
        """
        import time
        file_mtime = file_path.stat().st_mtime
        current_time = time.time()
        cache_age_hours = (current_time - file_mtime) / 3600
        return cache_age_hours < max_age_hours
    
    @staticmethod
    def _fetch_and_cache_data(ticker: str, data_cache_dir: str, max_retries: int = 3) -> Optional[pl.DataFrame]:
        """
        Fetch data from yfinance and cache it
        
        Args:
            ticker: Stock ticker symbol
            data_cache_dir: Path to data cache directory
            max_retries: Maximum number of retry attempts
            
        Returns:
            DataFrame with price data or None if failed
        """
        import yfinance as yf
        from datetime import datetime, timedelta
        import time as time_module
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * 15)  # 15 years of data
        
        # 處理台股代碼
        yf_ticker = ticker
        original_ticker = ticker
        
        # 檢查是否為台股代碼（4-6位數字）
        clean_ticker = ticker.replace(".TW", "").replace(".TWO", "").strip()
        if clean_ticker.isdigit() and 4 <= len(clean_ticker) <= 6:
            # 嘗試從傳入的 market_type 判斷（如果有的話）
            # 否則使用 FinMind API 判斷
            try:
                from tradingagents.dataflows.finmind_common import get_yfinance_ticker
                yf_ticker = get_yfinance_ticker(clean_ticker)
                logger.info(f"台股代碼 {ticker} 轉換為 Yahoo Finance 格式: {yf_ticker}")
            except ImportError:
                # 如果無法導入 FinMind，預設使用 .TW
                yf_ticker = f"{clean_ticker}.TW"
                logger.info(f"無法導入 FinMind，預設使用上市後綴: {yf_ticker}")
            except Exception as e:
                logger.warning(f"獲取市場類型失敗，嘗試 .TW: {e}")
                yf_ticker = f"{clean_ticker}.TW"
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"嘗試從 Yahoo Finance 獲取 {yf_ticker} 數據（第 {attempt} 次嘗試）...")
                
                # Download data with timeout
                data = yf.download(
                    yf_ticker,
                    start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d"),
                    multi_level_index=False,
                    progress=False,
                    auto_adjust=False,
                    timeout=30
                )
                
                if data.empty:
                    # 如果是台股，嘗試另一個後綴
                    if ".TW" in yf_ticker:
                        alt_ticker = yf_ticker.replace(".TW", ".TWO")
                        logger.info(f"嘗試上櫃代碼: {alt_ticker}")
                        data = yf.download(
                            alt_ticker,
                            start=start_date.strftime("%Y-%m-%d"),
                            end=end_date.strftime("%Y-%m-%d"),
                            multi_level_index=False,
                            progress=False,
                            auto_adjust=False,
                            timeout=30
                        )
                        if not data.empty:
                            yf_ticker = alt_ticker
                    elif ".TWO" in yf_ticker:
                        alt_ticker = yf_ticker.replace(".TWO", ".TW")
                        logger.info(f"嘗試上市代碼: {alt_ticker}")
                        data = yf.download(
                            alt_ticker,
                            start=start_date.strftime("%Y-%m-%d"),
                            end=end_date.strftime("%Y-%m-%d"),
                            multi_level_index=False,
                            progress=False,
                            auto_adjust=False,
                            timeout=30
                        )
                        if not data.empty:
                            yf_ticker = alt_ticker
                    
                    if data.empty:
                        logger.error(f"{yf_ticker} 無可用數據")
                        return None
                
                # 處理 yfinance 多索引 DataFrame
                # yfinance 可能返回多層索引的 DataFrame
                if isinstance(data.columns, pd.MultiIndex):
                    # 移除多層索引，只保留第一層
                    data.columns = data.columns.get_level_values(0)
                    logger.info("已處理 yfinance 多索引 DataFrame")
                
                # Reset index to make Date a column
                data = data.reset_index()
                
                # 確保 Date 欄位名稱正確
                if 'Date' not in data.columns and 'date' in data.columns:
                    data = data.rename(columns={'date': 'Date'})
                elif 'Date' not in data.columns:
                    # 如果第一個欄位是日期，重命名它
                    first_col = data.columns[0]
                    data = data.rename(columns={first_col: 'Date'})
                
                # 標準化欄位名稱
                column_mapping = {
                    'open': 'Open', 'high': 'High', 'low': 'Low', 
                    'close': 'Close', 'volume': 'Volume', 'adj close': 'Adj Close'
                }
                data = data.rename(columns={k: v for k, v in column_mapping.items() if k in data.columns})
                
                # Ensure cache directory exists
                Path(data_cache_dir).mkdir(parents=True, exist_ok=True)
                
                # Save to cache - 使用原始代碼作為檔名（不含後綴）
                cache_file = Path(data_cache_dir) / f"{original_ticker}-YFin-data-{start_date.strftime('%Y-%m-%d')}-{end_date.strftime('%Y-%m-%d')}.csv"
                data.to_csv(cache_file, index=False)
                
                logger.info(f"成功獲取並緩存 {yf_ticker} 數據到 {cache_file}")
                
                # Prepare and return DataFrame - convert to polars
                df = pl.read_csv(str(cache_file))
                
                # 嘗試轉換 Date 欄位
                try:
                    df = df.with_columns(pl.col("Date").str.to_datetime())
                except Exception as date_err:
                    logger.warning(f"日期轉換失敗: {date_err}，嘗試其他格式")
                    try:
                        df = df.with_columns(pl.col("Date").cast(pl.Datetime))
                    except:
                        pass
                
                return df.sort("Date")
                
            except Exception as e:
                logger.warning(f"第 {attempt} 次嘗試失敗: {e}")
                if attempt < max_retries:
                    wait_time = 2 ** (attempt - 1)  # Exponential backoff
                    logger.info(f"將在 {wait_time} 秒後重試...")
                    time_module.sleep(wait_time)
                else:
                    logger.error(f"在 {max_retries} 次嘗試後仍無法獲取 {yf_ticker} 數據")
                    return None
        
        return None

    
    @staticmethod
    def calculate_stats(df: pl.DataFrame) -> Dict[str, Any]:
        """
        Calculate price statistics
        
        Args:
            df: DataFrame with price data
            
        Returns:
            Dictionary with statistics
        """
        # Use Adj Close if available, otherwise use Close
        close_field = "Adj Close" if "Adj Close" in df.columns else "Close"
        
        start_price = float(df.row(0, named=True)[close_field])
        end_price = float(df.row(-1, named=True)[close_field])
        growth_rate = ((end_price - start_price) / start_price) * 100
        duration_days = (df.row(-1, named=True)["Date"] - df.row(0, named=True)["Date"]).days
        
        return {
            "growth_rate": round(growth_rate, 2),
            "duration_days": int(duration_days),
            "start_date": df.row(0, named=True)["Date"].strftime('%Y-%m-%d'),
            "end_date": df.row(-1, named=True)["Date"].strftime('%Y-%m-%d'),
            "start_price": round(start_price, 2),
            "end_price": round(end_price, 2),
        }
    
    @staticmethod
    def prepare_chart_data(df: pl.DataFrame, limit: int = 365) -> List[Dict[str, Any]]:
        """
        Prepare price data for charting (limit to recent data)
        
        Args:
            df: DataFrame with price data
            limit: Maximum number of data points to return
            
        Returns:
            List of dictionaries with price data
        """
        # Get recent data
        recent_df = df.tail(limit)
        
        # Check if 'Adj Close' column exists
        has_adj_close = "Adj Close" in recent_df.columns
        
        # Convert to list of dicts using polars to_dicts()
        data = []
        for row in recent_df.iter_rows(named=True):
            item = {
                "Date": row['Date'].strftime('%Y-%m-%d'),
                "Open": round(float(row['Open']), 2),
                "High": round(float(row['High']), 2),
                "Low": round(float(row['Low']), 2),
                "Close": round(float(row['Close']), 2),
                "Volume": int(row['Volume']),
            }
            
            # Add Adj Close if available
            if has_adj_close:
                item["Adj Close"] = round(float(row['Adj Close']), 2)
            
            data.append(item)
        
        return data
