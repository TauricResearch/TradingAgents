from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import yfinance as yf
import os
import time
import logging
from .stockstats_utils import StockstatsUtils
from .retry_utils import retry

logger = logging.getLogger(__name__)


@retry(max_attempts=3, backoff=2.0, exceptions=(Exception,))
def get_YFin_data_online(
    symbol: Annotated[str, "公司的股票代碼"],
    start_date: Annotated[str, "開始日期，格式為 yyyy-mm-dd"],
    end_date: Annotated[str, "結束日期，格式為 yyyy-mm-dd"],
):
    """
    從 Yahoo Finance 線上獲取股票數據。

    Args:
        symbol (str): 公司的股票代碼。
        start_date (str): 開始日期。
        end_date (str): 結束日期。

    Returns:
        str: 包含股票數據的 CSV 格式字串。
    """

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # 使用 yf.download() 獲取指定日期範圍的歷史數據
    try:
        data = yf.download(
            symbol.upper(),
            start=start_date,
            end=end_date,
            multi_level_index=False,
            progress=False,
            auto_adjust=False,
            timeout=30
        )
    except Exception as e:
        raise Exception(f"從 Yahoo Finance 獲取 {symbol} 數據失敗: {e}")

    # 檢查數據是否為空
    if data.empty:
        return (
            f"找不到 '{symbol}' 在 {start_date} 和 {end_date} 之間的數據"
        )

    # 從索引中移除時區資訊以獲得更清晰的輸出
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # 將數值四捨五入到小數點後兩位以便更清晰地顯示
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # 將 DataFrame 轉換為 CSV 字串
    csv_string = data.to_csv()

    # 新增標頭資訊
    header = f"# {symbol.upper()} 從 {start_date} 到 {end_date} 的股票數據\n"
    header += f"# 總記錄數：{len(data)}\n"
    header += f"# 數據檢索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "公司的股票代碼"],
    indicator: Annotated[str, "要獲取分析和報告的技術指標"],
    curr_date: Annotated[
        str, "您正在交易的當前交易日期，格式為 YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "回溯天數"],
) -> str:
    """
    獲取給定股票在一個時間窗口內的技術指標。

    Args:
        symbol (str): 公司的股票代碼。
        indicator (str): 技術指標。
        curr_date (str): 當前日期。
        look_back_days (int): 回溯天數。

    Returns:
        str: 包含指標值的格式化字串。
    """

    best_ind_params = {
        # 移動平均線
        "close_50_sma": (
            "50 SMA：一個中期趨勢指標。"
            "用法：識別趨勢方向並作為動態支撐/阻力。"
            "提示：它滯後於價格；與更快的指標結合以獲得及時信號。"
        ),
        "close_200_sma": (
            "200 SMA：一個長期趨勢基準。"
            "用法：確認整體市場趨勢並識別黃金/死亡交叉設置。"
            "提示：它反應緩慢；最適合戰略趨勢確認，而非頻繁的交易入場。"
        ),
        "close_10_ema": (
            "10 EMA：一個反應靈敏的短期平均線。"
            "用法：捕捉動能的快速轉變和潛在的入場點。"
            "提示：在震盪市場中容易產生噪音；與較長的平均線一起使用以過濾錯誤信號。"
        ),
        # MACD 相關
        "macd": (
            "MACD：通過 EMA 的差異計算動能。"
            "用法：尋找交叉和背離作為趨勢變化的信號。"
            "提示：在低波動性或橫盤市場中與其他指標確認。"
        ),
        "macds": (
            "MACD 信號線：MACD 線的 EMA 平滑。"
            "用法：使用與 MACD 線的交叉來觸發交易。"
            "提示：應作為更廣泛策略的一部分以避免誤報。"
        ),
        "macdh": (
            "MACD 柱狀圖：顯示 MACD 線與其信號線之間的差距。"
            "用法：可視化動能強度並及早發現背離。"
            "提示：可能不穩定；在快速變動的市場中輔以額外的過濾器。"
        ),
        # 動能指標
        "rsi": (
            "RSI：衡量動能以標記超買/超賣狀況。"
            "用法：應用 70/30 閾值並觀察背離以發出反轉信號。"
            "提示：在強勁趨勢中，RSI 可能保持極端；務必與趨勢分析交叉檢查。"
        ),
        # 波動性指標
        "boll": (
            "布林帶中軌：作為布林帶基礎的 20 SMA。"
            "用法：作為價格變動的動態基準。"
            "提示：與上下軌結合以有效發現突破或反轉。"
        ),
        "boll_ub": (
            "布林帶上軌：通常比中軌高 2 個標準差。"
            "用法：發出潛在超買狀況和突破區域的信號。"
            "提示：與其他工具確認信號；在強勁趨勢中價格可能會沿著軌道運行。"
        ),
        "boll_lb": (
            "布林帶下軌：通常比中軌低 2 個標準差。"
            "用法：指示潛在的超賣狀況。"
            "提示：使用額外分析以避免錯誤的反轉信號。"
        ),
        "atr": (
            "ATR：平均真實波幅，用於衡量波動性。"
            "用法：根據當前市場波動性設置止損水平和調整頭寸大小。"
            "提示：這是一個反應性指標，因此請將其用作更廣泛風險管理策略的一部分。"
        ),
        # 成交量指標
        "vwma": (
            "VWMA：成交量加權移動平均線。"
            "用法：通過將價格行為與成交量數據相結合來確認趨勢。"
            "提示：注意成交量激增導致的結果偏差；與其他成交量分析結合使用。"
        ),
        "mfi": (
            "MFI：資金流動指數是一種動能指標，使用價格和成交量來衡量買賣壓力。"
            "用法：識別超買 (>80) 或超賣 (<20) 狀況，並確認趨勢或反轉的強度。"
            "提示：與 RSI 或 MACD 一起使用以確認信號；價格與 MFI 之間的背離可能表示潛在的反轉。"
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"不支持指標 {indicator}。請從以下選項中選擇：{list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # 優化：一次性獲取股票數據並計算所有日期的指標
    try:
        indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)
        
        # 生成我們需要的日期範圍
        current_dt = curr_date_dt
        date_values = []
        
        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')
            
            # 查找此日期的指標值
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "N/A：非交易日 (週末或假日)"
            
            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)
        
        # 建立結果字串
        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"
        
    except Exception as e:
        print(f"獲取批量 stockstats 數據時出錯：{e}")
        # 如果批量方法失敗，則回退到原始實現
        ind_string = ""
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        while curr_date_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, curr_date_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{curr_date_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            curr_date_dt = curr_date_dt - relativedelta(days=1)

    result_str = (
        f"## 從 {before.strftime('%Y-%m-%d')} 到 {end_date} 的 {indicator} 值：\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "無可用描述。")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "公司的股票代碼"],
    indicator: Annotated[str, "要計算的技術指標"],
    curr_date: Annotated[str, "供參考的當前日期"]
) -> dict:
    """
    優化的股票統計指標批量計算。
    一次性獲取數據並計算所有可用日期的指標。
    返回將日期字串映射到指標值的字典。
    """
    from .config import get_config
    import polars as pl
    import pandas as pd
    from stockstats import wrap
    import os
    
    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"
    
    if not online:
        # 本地數據路徑
        try:
            data = pl.read_csv(
                os.path.join(
                    config.get("data_cache_dir", "data"),
                    f"{symbol}-YFin-data-2015-01-01-2025-03-25.csv",
                )
            )
            # stockstats 需要 pandas DataFrame
            data_pd = data.to_pandas()
            df = wrap(data_pd)
        except FileNotFoundError:
            raise Exception("Stockstats 失敗：尚未獲取 Yahoo Finance 數據！")
    else:
        # 帶有快取的線上數據獲取
        from datetime import datetime as dt, timedelta
        today_date = dt.now()
        curr_date_dt = dt.strptime(curr_date, "%Y-%m-%d")
        
        end_date = today_date
        start_date = today_date - timedelta(days=365*15)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        data_file = os.path.join(
            config["data_cache_dir"],
            f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
        )
        
        # 檢查緩存是否存在且有效（24小時內）
        cache_valid = False
        if os.path.exists(data_file):
            file_mtime = os.path.getmtime(data_file)
            current_time = time.time()
            cache_age_hours = (current_time - file_mtime) / 3600
            
            if cache_age_hours < 24:
                cache_valid = True
                logger.info(f"{symbol} 緩存有效（年齡：{cache_age_hours:.1f} 小時）")
            else:
                logger.info(f"{symbol} 緩存過期（年齡：{cache_age_hours:.1f} 小時），將重新下載")
        
        if cache_valid:
            data_pl = pl.read_csv(data_file)
            data_pl = data_pl.with_columns(pl.col("Date").str.to_datetime())
            # stockstats 需要 pandas DataFrame
            data = data_pl.to_pandas()
        else:
            # 使用重試機制下載數據
            @retry(max_attempts=3, backoff=2.0)
            def download_data():
                return yf.download(
                    symbol,
                    start=start_date_str,
                    end=end_date_str,
                    multi_level_index=False,
                    progress=False,
                    auto_adjust=False,
                    timeout=30
                )
            
            try:
                data = download_data()
                data = data.reset_index()
                data.to_csv(data_file, index=False)
                logger.info(f"成功下載並緩存 {symbol} 數據到 {data_file}")
            except Exception as e:
                logger.error(f"下載 {symbol} 數據失敗: {e}")
                # 如果下載失敗但有舊緩存，使用舊緩存
                if os.path.exists(data_file):
                    logger.warning(f"使用過期緩存作為備援")
                    data_pl = pl.read_csv(data_file)
                    data_pl = data_pl.with_columns(pl.col("Date").str.to_datetime())
                    data = data_pl.to_pandas()
                else:
                    raise
        
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    
    # 一次性計算所有行的指標
    df[indicator]  # 這會觸發 stockstats 計算指標
    
    # 建立一個將日期字串映射到指標值的字典
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]
        
        # 處理 NaN/None 值
        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
        else:
            result_dict[date_str] = str(indicator_value)
    
    return result_dict



def get_stockstats_indicator(
    symbol: Annotated[str, "公司的股票代碼"],
    indicator: Annotated[str, "要獲取分析和報告的技術指標"],
    curr_date: Annotated[
        str, "您正在交易的當前交易日期，格式為 YYYY-mm-dd"
    ],
) -> str:
    """
    獲取單個日期的 stockstats 指標。

    Args:
        symbol (str): 股票代碼。
        indicator (str): 指標名稱。
        curr_date (str): 日期。

    Returns:
        str: 指標值。
    """

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    try:
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
    except Exception as e:
        print(
            f"獲取指標 {indicator} 在 {curr_date} 的 stockstats 指標數據時出錯：{e}"
        )
        return ""

    return str(indicator_value)


def get_balance_sheet(
    ticker: Annotated[str, "公司的股票代碼"],
    freq: Annotated[str, "數據頻率：'annual' 或 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "當前日期 (yfinance 未使用)"] = None
):
    """從 yfinance 獲取資產負債表數據。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        
        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_balance_sheet
        else:
            data = ticker_obj.balance_sheet
            
        if data.empty:
            return f"找不到 '{ticker}' 的資產負債表數據"
            
        # 為與其他函式保持一致，轉換為 CSV 字串
        csv_string = data.to_csv()
        
        # 新增標頭資訊
        header = f"# {ticker.upper()} 的資產負債表數據 ({freq})\n"
        header += f"# 數據檢索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"檢索 {ticker} 的資產負債表時出錯：{str(e)}"


def get_cashflow(
    ticker: Annotated[str, "公司的股票代碼"],
    freq: Annotated[str, "數據頻率：'annual' 或 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "當前日期 (yfinance 未使用)"] = None
):
    """從 yfinance 獲取現金流量數據。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        
        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_cashflow
        else:
            data = ticker_obj.cashflow
            
        if data.empty:
            return f"找不到 '{ticker}' 的現金流量數據"
            
        # 為與其他函式保持一致，轉換為 CSV 字串
        csv_string = data.to_csv()
        
        # 新增標頭資訊
        header = f"# {ticker.upper()} 的現金流量數據 ({freq})\n"
        header += f"# 數據檢索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"檢索 {ticker} 的現金流量時出錯：{str(e)}"


def get_income_statement(
    ticker: Annotated[str, "公司的股票代碼"],
    freq: Annotated[str, "數據頻率：'annual' 或 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "當前日期 (yfinance 未使用)"] = None
):
    """從 yfinance 獲取損益表數據。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        
        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_income_stmt
        else:
            data = ticker_obj.income_stmt
            
        if data.empty:
            return f"找不到 '{ticker}' 的損益表數據"
            
        # 為與其他函式保持一致，轉換為 CSV 字串
        csv_string = data.to_csv()
        
        # 新增標頭資訊
        header = f"# {ticker.upper()} 的損益表數據 ({freq})\n"
        header += f"# 數據檢索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"檢索 {ticker} 的損益表時出錯：{str(e)}"


def get_fundamentals(
    ticker: Annotated[str, "公司的股票代碼"],
    curr_date: Annotated[str, "當前日期 (yfinance 未使用)"] = None
):
    """從 yfinance 獲取公司基本面數據。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = ticker_obj.info
        
        if not info or len(info) == 0:
            return f"找不到 '{ticker}' 的基本面數據"
        
        # 提取關鍵基本面指標（與 alpha_vantage 格式相似）
        fundamentals = {
            # 基本資訊
            "Symbol": info.get("symbol", ticker.upper()),
            "Name": info.get("longName", info.get("shortName", "")),
            "Description": (info.get("longBusinessSummary", "") or "")[:300],
            "Sector": info.get("sector", ""),
            "Industry": info.get("industry", ""),
            "MarketCapitalization": info.get("marketCap", ""),
            
            # 關鍵財務指標
            "EBITDA": info.get("ebitda", ""),
            "PERatio": info.get("trailingPE", info.get("forwardPE", "")),
            "PEGRatio": info.get("pegRatio", ""),
            "BookValue": info.get("bookValue", ""),
            "DividendPerShare": info.get("dividendRate", ""),
            "DividendYield": info.get("dividendYield", ""),
            "EPS": info.get("trailingEps", ""),
            "RevenuePerShareTTM": info.get("revenuePerShare", ""),
            "ProfitMargin": info.get("profitMargins", ""),
            "OperatingMarginTTM": info.get("operatingMargins", ""),
            "ReturnOnAssetsTTM": info.get("returnOnAssets", ""),
            "ReturnOnEquityTTM": info.get("returnOnEquity", ""),
            "RevenueTTM": info.get("totalRevenue", ""),
            "GrossProfitTTM": info.get("grossProfits", ""),
            
            # 交易指標
            "52WeekHigh": info.get("fiftyTwoWeekHigh", ""),
            "52WeekLow": info.get("fiftyTwoWeekLow", ""),
            "50DayMovingAverage": info.get("fiftyDayAverage", ""),
            "200DayMovingAverage": info.get("twoHundredDayAverage", ""),
            
            # 財務健康指標
            "QuarterlyEarningsGrowthYOY": info.get("earningsQuarterlyGrowth", ""),
            "QuarterlyRevenueGrowthYOY": info.get("revenueGrowth", ""),
            "AnalystTargetPrice": info.get("targetMeanPrice", ""),
            "Beta": info.get("beta", ""),
            
            # 額外的 yfinance 特有指標
            "CurrentPrice": info.get("currentPrice", info.get("regularMarketPrice", "")),
            "DebtToEquity": info.get("debtToEquity", ""),
            "CurrentRatio": info.get("currentRatio", ""),
            "QuickRatio": info.get("quickRatio", ""),
            "FreeCashFlow": info.get("freeCashflow", ""),
        }
        
        # 過濾掉空值和 None
        fundamentals = {k: v for k, v in fundamentals.items() if v not in (None, "", "None")}
        
        import json
        
        # 新增標頭資訊
        header = f"# {ticker.upper()} 的基本面數據 (來源: yfinance)\n"
        header += f"# 數據檢索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + json.dumps(fundamentals, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return f"檢索 {ticker} 的基本面數據時出錯：{str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "公司的股票代碼"]
):
    """從 yfinance 獲取內部人士交易數據。"""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.insider_transactions
        
        if data is None or data.empty:
            return f"找不到 '{ticker}' 的內部人士交易數據"
            
        # 為與其他函式保持一致，轉換為 CSV 字串
        csv_string = data.to_csv()
        
        # 新增標頭資訊
        header = f"# {ticker.upper()} 的內部人士交易數據\n"
        header += f"# 數據檢索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"檢索 {ticker} 的內部人士交易時出錯：{str(e)}"