import akshare as ak
import pandas as pd
from datetime import datetime

def get_stock_data_akshare(symbol: str, start_date: str, end_date: str) -> str:
    """获取 A 股历史行情数据"""
    # 处理 symbol：akshare 通常需要纯数字，如 600519
    # 假设传入的是 600519.SS 或 000001.SZ
    clean_symbol = symbol.split('.')[0]
    
    start_d = start_date.replace("-", "")
    end_d = end_date.replace("-", "")
    
    try:
        # 使用 akshare 获取日频数据
        df = ak.stock_zh_a_hist(symbol=clean_symbol, period="daily", start_date=start_d, end_date=end_d, adjust="qfq")
        
        if df.empty:
            return f"No data found for {symbol}"
            
        # 统一列名以匹配 yfinance 格式，方便后续 Agent 处理
        df = df.rename(columns={
            "日期": "Date",
            "开盘": "Open",
            "最高": "High",
            "最低": "Low",
            "收盘": "Close",
            "成交量": "Volume"
        })
        df.set_index("Date", inplace=True)
        
        header = f"# Stock data for {symbol} (via akshare) from {start_date} to {end_date}\n\n"
        return header + df.to_csv()
    except Exception as e:
        return f"Error retrieving A-share data: {str(e)}"

if __name__ == "__main__":
    result = get_stock_data_akshare(symbol="600519.SS", start_date="2026-01-01", end_date="2026-04-13")
    print(result)