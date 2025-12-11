# -*- coding: utf-8 -*-
"""
FinMind 技術指標資料模組
用於獲取台灣股市技術指標和籌碼面數據

API 文檔：
- 技術面：https://finmind.github.io/tutor/TaiwanMarket/Technical/
- 籌碼面：https://finmind.github.io/tutor/TaiwanMarket/Chip/

可用的資料集：
- TaiwanStockPER: 個股 PER、PBR 資料
- TaiwanStockMarginPurchaseShortSale: 個股融資融劵表
- TaiwanStockInstitutionalInvestorsBuySell: 法人買賣表
- TaiwanStockShareholding: 外資持股表

技術指標計算：
- 本模組會從 FinMind 獲取股價數據，自行計算技術指標（SMA、RSI、MACD 等）
- 不需要依賴 Alpha Vantage 或其他外部服務

注意：本模組不使用需要 backer/sponsor 會員資格的功能
"""

import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional
import pandas as pd
import numpy as np

from .finmind_common import (
    _make_api_request,
    format_date,
    get_default_start_date,
    normalize_stock_id,
    FinMindError,
    FinMindDataNotFoundError,
    format_output,
)


# 指標描述
INDICATOR_DESCRIPTIONS = {
    "per": "本益比（PER）：股價與每股盈餘之比，用於評估股票價值。較低的 PER 可能表示股票被低估。",
    "pbr": "股價淨值比（PBR）：股價與每股淨值之比，用於評估公司淨資產價值。PBR 低於 1 可能表示股票被低估。",
    "dividend_yield": "殖利率：股利與股價之比，衡量股票收益率。較高的殖利率可能吸引存股族。",
    "margin_purchase": "融資餘額：投資人向券商借錢買股票的未還金額。融資增加可能表示看多情緒。",
    "short_sale": "融券餘額：投資人借股票賣出的未補回數量。融券增加可能表示看空情緒。",
    "institutional": "三大法人買賣超：外資、投信、自營商的買賣超情況，是重要的市場動向指標。",
    "foreign_holding": "外資持股比例：外資持有該股票的比例。外資持續買超可能推升股價。",
    # 技術指標描述
    "sma": "簡單移動平均線（SMA）：過去 N 日收盤價的平均值，用於判斷趨勢方向。",
    "ema": "指數移動平均線（EMA）：加權移動平均，對近期價格給予較高權重。",
    "rsi": "相對強弱指標（RSI）：衡量價格動能，RSI>70 為超買，RSI<30 為超賣。",
    "macd": "MACD：趨勢動能指標，由快線、慢線和柱狀圖組成，用於判斷買賣時機。",
    "bbands": "布林通道（Bollinger Bands）：由中軌（SMA）和上下軌組成，用於判斷價格波動範圍。",
}

# 支援的技術指標列表
CALCULATED_INDICATORS = [
    "sma", "ema", "rsi", "macd", "bbands",
    "close_5_sma", "close_10_sma", "close_20_sma", "close_50_sma", "close_100_sma", "close_200_sma",
    "close_5_ema", "close_10_ema", "close_20_ema", "close_50_ema",
]


def _get_stock_price_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """獲取股價數據並轉換為 DataFrame"""
    response = _make_api_request(
        dataset="TaiwanStockPrice",
        data_id=symbol,
        start_date=start_date,
        end_date=end_date
    )
    
    if "data" not in response or not response["data"]:
        raise FinMindDataNotFoundError(f"找不到 {symbol} 的股價數據")
    
    df = pd.DataFrame(response["data"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # 重命名欄位
    df = df.rename(columns={
        "max": "high",
        "min": "low",
        "Trading_Volume": "volume"
    })
    
    return df


def _calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """計算簡單移動平均線"""
    return df["close"].rolling(window=period).mean()


def _calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """計算指數移動平均線"""
    return df["close"].ewm(span=period, adjust=False).mean()


def _calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """計算 RSI 指標"""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def _calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """計算 MACD 指標"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


def _calculate_bbands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> dict:
    """計算布林通道"""
    sma = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    
    return {
        "upper": sma + (std * std_dev),
        "middle": sma,
        "lower": sma - (std * std_dev)
    }


def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    interval: str = "daily",
    time_period: int = 14,
    series_type: str = "close"
) -> str:
    """
    返回 FinMind 在一個時間窗口內的技術指標/籌碼面數據。
    
    支援的籌碼面指標：
    - per: 本益比
    - pbr: 股價淨值比
    - dividend_yield: 殖利率
    - margin_purchase: 融資餘額
    - short_sale: 融券餘額
    - institutional: 三大法人買賣超
    - foreign_holding: 外資持股比例
    
    支援的技術指標（從股價計算）：
    - sma, close_N_sma: 簡單移動平均線
    - ema, close_N_ema: 指數移動平均線
    - rsi: 相對強弱指標
    - macd: MACD 指標
    - bbands: 布林通道
    
    Args:
        symbol: 股票代碼（例如 "2330"）
        indicator: 要獲取的指標類型
        curr_date: 當前交易日期，格式為 YYYY-mm-dd
        look_back_days: 回溯天數
        interval: 時間間隔（保留參數，FinMind 只支援日線）
        time_period: 用於計算的天數
        series_type: 價格類型（保留參數）
        
    Returns:
        str: 包含指標值和描述的字串
    """
    symbol = normalize_stock_id(symbol)
    indicator = indicator.lower()
    
    # 籌碼面指標
    chip_indicators = [
        "per", "pbr", "dividend_yield",
        "margin_purchase", "short_sale",
        "institutional", "foreign_holding"
    ]
    
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)
    start_date = format_date(before)
    end_date = format_date(curr_date_dt)
    
    try:
        # 籌碼面指標
        if indicator in chip_indicators:
            if indicator in ["per", "pbr", "dividend_yield"]:
                return _get_per_pbr_indicator(symbol, indicator, start_date, end_date)
            elif indicator in ["margin_purchase", "short_sale"]:
                return _get_margin_indicator(symbol, indicator, start_date, end_date)
            elif indicator == "institutional":
                return _get_institutional_indicator(symbol, start_date, end_date)
            elif indicator == "foreign_holding":
                return _get_foreign_holding_indicator(symbol, start_date, end_date)
        
        # 技術指標（從股價計算）
        else:
            return _calculate_technical_indicator(
                symbol=symbol,
                indicator=indicator,
                start_date=start_date,
                end_date=end_date,
                time_period=time_period,
                look_back_days=look_back_days
            )
            
    except Exception as e:
        print(f"獲取 {indicator} 的 FinMind 指標數據時出錯：{e}")
        return f"檢索 {indicator} 數據時出錯：{str(e)}"


def _calculate_technical_indicator(
    symbol: str,
    indicator: str,
    start_date: str,
    end_date: str,
    time_period: int,
    look_back_days: int
) -> str:
    """計算技術指標"""
    indicator = indicator.lower()
    
    # 解析指標名稱（例如 close_50_sma -> sma, period=50）
    period = time_period
    indicator_type = indicator
    
    # 解析 close_N_sma 或 close_N_ema 格式
    if "_sma" in indicator:
        parts = indicator.split("_")
        for i, p in enumerate(parts):
            if p.isdigit():
                period = int(p)
        indicator_type = "sma"
    elif "_ema" in indicator:
        parts = indicator.split("_")
        for i, p in enumerate(parts):
            if p.isdigit():
                period = int(p)
        indicator_type = "ema"
    
    # 需要更多歷史數據來計算指標
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
    extended_start = start_date_dt - relativedelta(days=max(period + 50, 300))
    extended_start_str = format_date(extended_start)
    
    try:
        # 獲取股價數據
        df = _get_stock_price_data(symbol, extended_start_str, end_date)
        
        if df.empty:
            return f"找不到 {symbol} 的股價數據來計算 {indicator}。"
        
        # 計算指標
        if indicator_type == "sma":
            df["indicator"] = _calculate_sma(df, period)
            desc = f"{period} 日簡單移動平均線"
        elif indicator_type == "ema":
            df["indicator"] = _calculate_ema(df, period)
            desc = f"{period} 日指數移動平均線"
        elif indicator_type == "rsi":
            df["indicator"] = _calculate_rsi(df, period)
            desc = f"{period} 日 RSI 相對強弱指標"
        elif indicator_type == "macd":
            macd_data = _calculate_macd(df)
            df["macd"] = macd_data["macd"]
            df["signal"] = macd_data["signal"]
            df["histogram"] = macd_data["histogram"]
            desc = "MACD 指標（12, 26, 9）"
        elif indicator_type == "bbands":
            bbands_data = _calculate_bbands(df, period)
            df["bb_upper"] = bbands_data["upper"]
            df["bb_middle"] = bbands_data["middle"]
            df["bb_lower"] = bbands_data["lower"]
            desc = f"{period} 日布林通道"
        else:
            return f"不支援的技術指標 {indicator}。支援的技術指標：sma, ema, rsi, macd, bbands, close_N_sma, close_N_ema"
        
        # 過濾日期範圍
        start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        df = df[df["date"] >= pd.Timestamp(start_date_dt)]
        
        # 只顯示最近的數據
        df = df.tail(min(look_back_days, 30))
        
        # 格式化輸出
        ind_string = ""
        
        if indicator_type == "macd":
            for _, row in df.iterrows():
                date = row["date"].strftime("%Y-%m-%d")
                macd_val = row["macd"]
                signal_val = row["signal"]
                hist_val = row["histogram"]
                if pd.notna(macd_val):
                    ind_string += f"{date}: MACD={macd_val:.4f}, Signal={signal_val:.4f}, Histogram={hist_val:.4f}\n"
        elif indicator_type == "bbands":
            for _, row in df.iterrows():
                date = row["date"].strftime("%Y-%m-%d")
                upper = row["bb_upper"]
                middle = row["bb_middle"]
                lower = row["bb_lower"]
                close = row["close"]
                if pd.notna(upper):
                    ind_string += f"{date}: Upper={upper:.2f}, Middle={middle:.2f}, Lower={lower:.2f}, Close={close:.2f}\n"
        else:
            for _, row in df.iterrows():
                date = row["date"].strftime("%Y-%m-%d")
                value = row["indicator"]
                close = row["close"]
                if pd.notna(value):
                    ind_string += f"{date}: {indicator.upper()}={value:.4f}, Close={close:.2f}\n"
        
        if not ind_string:
            ind_string = "指定日期範圍內無足夠數據計算指標。\n"
        
        result_str = (
            f"## 從 {start_date} 到 {end_date} 的 {desc} ({symbol})：\n\n"
            + ind_string
            + "\n\n"
            + INDICATOR_DESCRIPTIONS.get(indicator_type, "技術指標計算自 FinMind 股價數據。")
        )
        
        return result_str
        
    except FinMindError as e:
        return f"獲取 {indicator} 數據時出錯：{str(e)}"
    except Exception as e:
        return f"計算 {indicator} 時出錯：{str(e)}"


def _get_per_pbr_indicator(
    symbol: str,
    indicator: str,
    start_date: str,
    end_date: str
) -> str:
    """獲取 PER、PBR、殖利率指標"""
    try:
        response = _make_api_request(
            dataset="TaiwanStockPER",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            data = response["data"]
            
            # 欄位映射
            field_map = {
                "per": "PER",
                "pbr": "PBR",
                "dividend_yield": "dividend_yield"
            }
            
            field_name = field_map.get(indicator, indicator)
            
            # 格式化輸出
            ind_string = ""
            for row in sorted(data, key=lambda x: x.get("date", "")):
                date = row.get("date", "")
                value = row.get(field_name, "N/A")
                ind_string += f"{date}: {value}\n"
            
            if not ind_string:
                ind_string = "指定日期範圍內無可用數據。\n"
            
            result_str = (
                f"## 從 {start_date} 到 {end_date} 的 {indicator.upper()} 值：\n\n"
                + ind_string
                + "\n\n"
                + INDICATOR_DESCRIPTIONS.get(indicator, "無可用描述。")
            )
            
            return result_str
        else:
            return f"找不到 {symbol} 的 {indicator} 數據。"
            
    except FinMindError as e:
        return f"獲取 {indicator} 數據時出錯：{str(e)}"


def _get_margin_indicator(
    symbol: str,
    indicator: str,
    start_date: str,
    end_date: str
) -> str:
    """獲取融資融券指標"""
    try:
        response = _make_api_request(
            dataset="TaiwanStockMarginPurchaseShortSale",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            data = response["data"]
            
            # 欄位映射
            if indicator == "margin_purchase":
                field_name = "MarginPurchaseTodayBalance"
                display_name = "融資餘額"
            else:  # short_sale
                field_name = "ShortSaleTodayBalance"
                display_name = "融券餘額"
            
            # 格式化輸出
            ind_string = ""
            for row in sorted(data, key=lambda x: x.get("date", "")):
                date = row.get("date", "")
                value = row.get(field_name, "N/A")
                ind_string += f"{date}: {value:,}\n" if isinstance(value, (int, float)) else f"{date}: {value}\n"
            
            if not ind_string:
                ind_string = "指定日期範圍內無可用數據。\n"
            
            result_str = (
                f"## 從 {start_date} 到 {end_date} 的 {display_name} ({symbol})：\n\n"
                + ind_string
                + "\n\n"
                + INDICATOR_DESCRIPTIONS.get(indicator, "無可用描述。")
            )
            
            return result_str
        else:
            return f"找不到 {symbol} 的融資融券數據。"
            
    except FinMindError as e:
        return f"獲取融資融券數據時出錯：{str(e)}"


def _get_institutional_indicator(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """獲取三大法人買賣超指標"""
    try:
        response = _make_api_request(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            data = response["data"]
            df = pd.DataFrame(data)
            
            # 按日期分組計算各法人買賣超
            ind_string = ""
            
            # 獲取唯一日期
            dates = sorted(df["date"].unique())
            for date in dates:
                day_data = df[df["date"] == date]
                
                # 彙總各法人買賣超
                foreign = day_data[day_data["name"].str.contains("外資", na=False)]["buy"].sum() - \
                         day_data[day_data["name"].str.contains("外資", na=False)]["sell"].sum()
                investment_trust = day_data[day_data["name"].str.contains("投信", na=False)]["buy"].sum() - \
                                  day_data[day_data["name"].str.contains("投信", na=False)]["sell"].sum()
                dealer = day_data[day_data["name"].str.contains("自營商", na=False)]["buy"].sum() - \
                        day_data[day_data["name"].str.contains("自營商", na=False)]["sell"].sum()
                
                total = foreign + investment_trust + dealer
                ind_string += f"{date}: 外資 {foreign:+,} / 投信 {investment_trust:+,} / 自營 {dealer:+,} / 合計 {total:+,}\n"
            
            if not ind_string:
                ind_string = "指定日期範圍內無可用數據。\n"
            
            result_str = (
                f"## 從 {start_date} 到 {end_date} 的三大法人買賣超 ({symbol})：\n\n"
                + ind_string
                + "\n\n"
                + INDICATOR_DESCRIPTIONS.get("institutional", "無可用描述。")
            )
            
            return result_str
        else:
            return f"找不到 {symbol} 的三大法人買賣超數據。"
            
    except FinMindError as e:
        return f"獲取三大法人數據時出錯：{str(e)}"


def _get_foreign_holding_indicator(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """獲取外資持股比例指標"""
    try:
        response = _make_api_request(
            dataset="TaiwanStockShareholding",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            data = response["data"]
            
            # 格式化輸出
            ind_string = ""
            for row in sorted(data, key=lambda x: x.get("date", "")):
                date = row.get("date", "")
                holding_percent = row.get("ForeignInvestmentSharesRatio", "N/A")
                holding_shares = row.get("ForeignInvestmentShares", "N/A")
                
                if isinstance(holding_percent, (int, float)):
                    ind_string += f"{date}: {holding_percent:.2f}% ({holding_shares:,} 股)\n"
                else:
                    ind_string += f"{date}: {holding_percent}\n"
            
            if not ind_string:
                ind_string = "指定日期範圍內無可用數據。\n"
            
            result_str = (
                f"## 從 {start_date} 到 {end_date} 的外資持股比例 ({symbol})：\n\n"
                + ind_string
                + "\n\n"
                + INDICATOR_DESCRIPTIONS.get("foreign_holding", "無可用描述。")
            )
            
            return result_str
        else:
            return f"找不到 {symbol} 的外資持股數據。"
            
    except FinMindError as e:
        return f"獲取外資持股數據時出錯：{str(e)}"


def get_margin_data(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    獲取個股融資融劵表完整數據。
    
    資料區間：2001-01-01 ~ now
    
    返回欄位：
    - date: 日期
    - stock_id: 股票代碼
    - MarginPurchaseBuy: 融資買進
    - MarginPurchaseSell: 融資賣出
    - MarginPurchaseTodayBalance: 融資今日餘額
    - ShortSaleBuy: 融券買進
    - ShortSaleSell: 融券賣出
    - ShortSaleTodayBalance: 融券今日餘額
    
    Returns:
        str: JSON 格式的融資融券數據
    """
    symbol = normalize_stock_id(symbol)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockMarginPurchaseShortSale",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            result = {
                "stock_id": symbol,
                "data_type": "margin_trading",
                "data": response["data"]
            }
            return format_output(result)
        else:
            return format_output({
                "stock_id": symbol,
                "data": [],
                "message": "查無資料"
            })
            
    except FinMindError as e:
        return format_output({
            "error": str(e),
            "stock_id": symbol
        })


def get_institutional_data(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    獲取法人買賣表完整數據。
    
    資料區間：2005-01-01 ~ now
    
    返回欄位：
    - date: 日期
    - stock_id: 股票代碼
    - name: 法人名稱（外資、投信、自營商等）
    - buy: 買進金額
    - sell: 賣出金額
    
    Returns:
        str: JSON 格式的法人買賣數據
    """
    symbol = normalize_stock_id(symbol)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            result = {
                "stock_id": symbol,
                "data_type": "institutional_investors",
                "data": response["data"]
            }
            return format_output(result)
        else:
            return format_output({
                "stock_id": symbol,
                "data": [],
                "message": "查無資料"
            })
            
    except FinMindError as e:
        return format_output({
            "error": str(e),
            "stock_id": symbol
        })
