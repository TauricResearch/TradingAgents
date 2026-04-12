# tradingagents/dataflows/akshare_news.py
import akshare as ak
from datetime import datetime
import pandas as pd

def get_news_akshare(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    使用 AkShare 获取 A 股特定股票的新闻 (东方财富数据源)
    """
    # 1. A股代码清洗: yfinance 习惯用 '600519.SS', akshare 通常只需要 '600519'
    clean_ticker = ticker.split('.')[0] 
    if not clean_ticker.isdigit():
        return f"Invalid A-share ticker format: {ticker}"

    try:
        # 获取个股新闻 (东方财富接口)
        news_df = ak.stock_news_em(symbol=clean_ticker)
        
        if news_df.empty:
            return f"No news found for {ticker}"

        # 将发布时间转换为 datetime 进行过滤
        news_df['发布时间'] = pd.to_datetime(news_df['发布时间'])
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # 过滤日期区间
        mask = (news_df['发布时间'] >= start_dt) & (news_df['发布时间'] <= end_dt)
        filtered_news = news_df.loc[mask]

        if filtered_news.empty:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        # 格式化输出为大模型易读的 Markdown 格式
        news_str = ""
        # 限制返回条数，避免 token 溢出
        for _, row in filtered_news.head(20).iterrows():
            pub_time = row['发布时间'].strftime('%Y-%m-%d %H:%M:%S')
            news_str += f"### {row['新闻标题']} (时间: {pub_time})\n"
            news_str += f"{row['新闻内容']}\n"
            news_str += f"来源: {row['文章来源']} | Link: {row['新闻链接']}\n\n"

        return f"## {ticker} A股新闻, 从 {start_date} 到 {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching A-share news for {ticker} via AkShare: {str(e)}"