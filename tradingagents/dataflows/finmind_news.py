# -*- coding: utf-8 -*-
"""
FinMind 新聞資料模組
用於獲取台灣股市相關新聞和公告

API 文檔：https://finmind.github.io/

主要資料集：
- TaiwanStockNews: 台股相關新聞（主要新聞來源）
- TaiwanStockDividendResult: 除權息公告
- TaiwanStockMonthRevenue: 月營收公告
- TaiwanStockInstitutionalInvestorsBuySell: 法人買賣超
"""

import json
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd

from .finmind_common import (
    _make_api_request,
    format_date,
    get_default_start_date,
    normalize_stock_id,
    FinMindError,
    FinMindDataNotFoundError,
    format_output,
)


def get_news(
    ticker: str,
    start_date: str,
    end_date: str,
    use_toon: bool = True
) -> str:
    """
    獲取台灣股市相關新聞資訊。
    
    使用 FinMind 的 TaiwanStockNews 資料集獲取真正的台股新聞。
    資料區間：2019-04-01 ~ now
    
    返回欄位：
    - date: 新聞日期
    - stock_id: 股票代碼
    - description: 新聞內容
    - link: 新聞連結
    - source: 新聞來源
    - title: 新聞標題
    
    Args:
        ticker: 股票代碼（例如 "2330"）
        start_date: 開始日期
        end_date: 結束日期
        use_toon: 是否使用 toon 格式（保留參數）
        
    Returns:
        str: JSON 格式的新聞資訊
    """
    ticker = normalize_stock_id(ticker)
    
    news_items = []
    
    # 1. 獲取真正的新聞（TaiwanStockNews）
    # 注意：TaiwanStockNews 只支援 start_date，不支援 end_date
    try:
        import requests
        import os
        
        url = "https://api.finmindtrade.com/api/v4/data"
        token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params = {
            "dataset": "TaiwanStockNews",
            "data_id": ticker,
            "start_date": start_date,
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        news_response = response.json()
        
        if "data" in news_response and news_response["data"]:
            # 過濾日期範圍內的新聞
            filtered_news = []
            for item in news_response["data"]:
                news_date = item.get("date", "")[:10]  # 只取日期部分
                if news_date and start_date <= news_date <= end_date:
                    filtered_news.append(item)
            
            # 取最近 20 筆新聞
            for item in filtered_news[-20:]:
                news_items.append({
                    "title": item.get("title", "無標題"),
                    "date": item.get("date", "")[:10],  # 只保留日期部分
                    "type": "news",
                    "summary": "",  # TaiwanStockNews 沒有 description 欄位
                    "link": item.get("link", ""),
                    "source": item.get("source", "FinMind")
                })
    except FinMindError as e:
        print(f"獲取新聞時發生錯誤: {e}")
    
    # 2. 如果沒有新聞或新聞太少，補充其他資訊
    if len(news_items) < 5:
        # 補充股利公告
        try:
            dividend_response = _make_api_request(
                dataset="TaiwanStockDividendResult",
                data_id=ticker,
                start_date=start_date,
                end_date=end_date
            )
            
            if "data" in dividend_response and dividend_response["data"]:
                for item in dividend_response["data"][:3]:
                    news_items.append({
                        "title": f"{ticker} 除權息公告",
                        "date": item.get("date", ""),
                        "type": "dividend",
                        "summary": f"除權息日：{item.get('date', '')}，"
                                  f"參考價：{item.get('reference_price', 'N/A')}，"
                                  f"股利合計：{item.get('stock_and_cache_dividend', 'N/A')}",
                        "link": "",
                        "source": "FinMind"
                    })
        except FinMindError:
            pass
        
        # 補充月營收公告
        try:
            revenue_response = _make_api_request(
                dataset="TaiwanStockMonthRevenue",
                data_id=ticker,
                start_date=start_date,
                end_date=end_date
            )
            
            if "data" in revenue_response and revenue_response["data"]:
                for item in revenue_response["data"][-3:]:
                    revenue = item.get("revenue", 0)
                    if isinstance(revenue, (int, float)):
                        revenue_str = f"{revenue:,.0f}"
                    else:
                        revenue_str = str(revenue)
                        
                    news_items.append({
                        "title": f"{ticker} 月營收公告",
                        "date": item.get("date", ""),
                        "type": "revenue",
                        "summary": f"{item.get('revenue_year', '')}年{item.get('revenue_month', '')}月營收：{revenue_str}",
                        "link": "",
                        "source": "FinMind"
                    })
        except FinMindError:
            pass
    
    # 按日期排序（最新的在前）
    news_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    # 統計新聞類型
    news_count = len([n for n in news_items if n.get("type") == "news"])
    other_count = len(news_items) - news_count
    
    result = {
        "stock_id": ticker,
        "items": len(news_items),
        "news_count": news_count,
        "note": f"包含 {news_count} 則新聞" + (f"和 {other_count} 則公司公告" if other_count > 0 else ""),
        "feed": news_items[:15]  # 限制最多 15 筆
    }
    
    return format_output(result, use_toon)


def get_global_news(
    curr_date: str,
    look_back_days: int = 7
) -> str:
    """
    獲取台灣股市整體市場新聞/動態。
    
    注意：FinMind 不提供全球新聞 API，
    本函式透過市場整體指標提供替代資訊。
    
    Args:
        curr_date: 當前日期
        look_back_days: 回溯天數
        
    Returns:
        str: JSON 格式的市場動態
    """
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date_dt = curr_date_dt - timedelta(days=look_back_days)
    start_date = format_date(start_date_dt)
    end_date = format_date(curr_date_dt)
    
    market_news = []
    
    # 1. 獲取整體市場融資融券
    try:
        margin_response = _make_api_request(
            dataset="TaiwanStockTotalMarginPurchaseShortSale",
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in margin_response and margin_response["data"]:
            for item in margin_response["data"][-3:]:  # 取最近 3 筆
                market_news.append({
                    "title": "台股整體融資融券動態",
                    "date": item.get("date", ""),
                    "type": "margin_total",
                    "summary": f"{item.get('name', '')}：今日餘額 {item.get('TodayBalance', 'N/A'):,}，"
                              f"增減 {item.get('TodayBalance', 0) - item.get('YesBalance', 0):+,}",
                    "source": "FinMind"
                })
    except FinMindError:
        pass
    
    # 2. 獲取整體三大法人買賣超
    try:
        institutional_response = _make_api_request(
            dataset="TaiwanStockTotalInstitutionalInvestors",
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in institutional_response and institutional_response["data"]:
            df = pd.DataFrame(institutional_response["data"])
            
            dates = sorted(df["date"].unique(), reverse=True)[:3]
            for date in dates:
                day_data = df[df["date"] == date]
                
                summary_parts = []
                for _, row in day_data.iterrows():
                    name = row.get("name", "")
                    buy = row.get("buy", 0)
                    sell = row.get("sell", 0)
                    net = buy - sell
                    
                    if isinstance(net, (int, float)):
                        summary_parts.append(f"{name} {net/100000000:+,.2f} 億")
                
                if summary_parts:
                    market_news.append({
                        "title": "台股三大法人買賣超",
                        "date": date,
                        "type": "institutional_total",
                        "summary": "，".join(summary_parts),
                        "source": "FinMind"
                    })
    except FinMindError:
        pass
    
    # 按日期排序
    market_news.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    result = {
        "market": "Taiwan",
        "items": len(market_news),
        "note": "FinMind 不提供新聞 API，此為市場整體動態資訊",
        "feed": market_news
    }
    
    return format_output(result)


def get_insider_sentiment(ticker: str, curr_date: str) -> str:
    """
    獲取內部人交易情緒（透過法人買賣超資料模擬）。
    
    Args:
        ticker: 股票代碼
        curr_date: 當前日期
        
    Returns:
        str: JSON 格式的情緒分析
    """
    ticker = normalize_stock_id(ticker)
    
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date_dt = curr_date_dt - timedelta(days=30)
    start_date = format_date(start_date_dt)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=ticker,
            start_date=start_date,
            end_date=curr_date
        )
        
        if "data" in response and response["data"]:
            df = pd.DataFrame(response["data"])
            
            # 計算整體買賣超趨勢
            total_buy = df["buy"].sum()
            total_sell = df["sell"].sum()
            net = total_buy - total_sell
            
            # 判斷情緒
            if net > 0:
                sentiment = "正面"
                sentiment_score = min(1.0, net / (total_buy + total_sell) * 2) if (total_buy + total_sell) > 0 else 0
            else:
                sentiment = "負面"
                sentiment_score = max(-1.0, net / (total_buy + total_sell) * 2) if (total_buy + total_sell) > 0 else 0
            
            result = {
                "stock_id": ticker,
                "period": f"{start_date} ~ {curr_date}",
                "sentiment": sentiment,
                "sentiment_score": round(sentiment_score, 3),
                "total_buy": int(total_buy),
                "total_sell": int(total_sell),
                "net": int(net),
                "note": "基於法人買賣超資料計算的情緒指標"
            }
            
            return format_output(result)
        else:
            return format_output({
                "stock_id": ticker,
                "error": "查無資料"
            })
            
    except FinMindError as e:
        return format_output({
            "stock_id": ticker,
            "error": str(e)
        })


def get_insider_transactions(symbol: str) -> str:
    """
    獲取內部人交易資訊。
    
    注意：FinMind 未提供內部人交易 API，
    本函式透過法人買賣超資料提供類似資訊。
    
    Args:
        symbol: 股票代碼
        
    Returns:
        str: JSON 格式的交易資訊
    """
    symbol = normalize_stock_id(symbol)
    
    end_date = format_date(datetime.now())
    start_date = get_default_start_date(years_back=0)  # 最近 1 個月
    start_date_dt = datetime.now() - timedelta(days=30)
    start_date = format_date(start_date_dt)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            # 只保留最近 15 筆
            data = response["data"][-15:]
            
            result = {
                "stock_id": symbol,
                "data_type": "institutional_trading",
                "note": "FinMind 不提供內部人交易 API，此為法人買賣超資料",
                "data": data
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
