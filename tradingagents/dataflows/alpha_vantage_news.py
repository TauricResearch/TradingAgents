from .alpha_vantage_common import _make_api_request, format_datetime_for_api
import json

import os


def get_news(ticker, start_date, end_date, use_toon: bool = True) -> dict[str, str] | str:
    """
    返回全球主要新聞機構的即時和歷史市場新聞與情緒數據。

    涵蓋股票、加密貨幣、外匯以及財政政策、併購、IPO 等主題。

    Args:
        ticker: 新聞文章的股票代碼。
        start_date: 新聞搜索的開始日期。
        end_date: 新聞搜索的結束日期。
        use_toon (bool): 是否使用toon格式。默認為 True

    Returns:
        包含新聞情緒數據的字典或 JSON/Toon 字串。
    """

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        "sort": "LATEST",
        "limit": "10",  # 降低限制從 50 到 10 以避免超過 token 限制
    }
    
    response = _make_api_request("NEWS_SENTIMENT", params)
    
    # 處理並總結回應以減少 token 使用量
    try:
        data = json.loads(response) if isinstance(response, str) else response
        
        # 如果回應包含新聞項目，提取關鍵資訊
        if isinstance(data, dict) and "feed" in data:
            summarized_feed = []
            for item in data.get("feed", []):
                # 只保留必要的欄位以減少大小
                summarized_item = {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "time_published": item.get("time_published", ""),
                    "summary": item.get("summary", "")[:200] if item.get("summary") else "",  # 限制摘要長度
                    "source": item.get("source", ""),
                    "overall_sentiment_score": item.get("overall_sentiment_score", 0),
                    "overall_sentiment_label": item.get("overall_sentiment_label", ""),
                }
                
                # 為此新聞項目添加相關的股票代碼情緒
                if "ticker_sentiment" in item:
                    ticker_sentiments = [
                        {
                            "ticker": ts.get("ticker", ""),
                            "relevance_score": ts.get("relevance_score", ""),
                            "ticker_sentiment_score": ts.get("ticker_sentiment_score", ""),
                            "ticker_sentiment_label": ts.get("ticker_sentiment_label", "")
                        }
                        for ts in item.get("ticker_sentiment", [])
                        if ts.get("ticker") == ticker  # 只包含相關的股票代碼
                    ]
                    if ticker_sentiments:
                        summarized_item["ticker_sentiment"] = ticker_sentiments
                
                summarized_feed.append(summarized_item)
            
            # 建立總結的回應
            summarized_data = {
                "items": data.get("items", "0"),
                "sentiment_score_definition": data.get("sentiment_score_definition", ""),
                "relevance_score_definition": data.get("relevance_score_definition", ""),
                "feed": summarized_feed
            }
            
            # 使用toon格式或JSON格式返回
            if use_toon:
                try:
                    from tradingagents.utils.toon_converter import convert_json_to_toon
                    toon_data = convert_json_to_toon(summarized_data)
                    return toon_data
                except Exception as e:
                    print(f"警告：toon轉換失敗：{e}，使用JSON格式")
                    return json.dumps(summarized_data, ensure_ascii=False, indent=2)
            else:
                return json.dumps(summarized_data, ensure_ascii=False, indent=2)
        
        # 如果格式不如預期，返回原始回應
        return response
        
    except (json.JSONDecodeError, Exception) as e:
        # 如果處理失敗，返回原始回應
        print(f"警告：無法總結新聞數據：{e}")
        return response

def get_insider_transactions(symbol: str, use_toon: bool = True) -> dict[str, str] | str:
    """
    返回主要利益相關者的最新和歷史內部交易。

    涵蓋創始人、高階主管、董事會成員等的交易。

    Args:
        symbol: 股票代碼。範例："IBM"。
        use_toon (bool): 是否使用toon格式。默認為 True

    Returns:
        包含內部交易數據的字典或 JSON/Toon 字串。
    """

    params = {
        "symbol": symbol,
    }

    response = _make_api_request("INSIDER_TRANSACTIONS", params)
    
    # 限制返回的交易數量以減少 token 使用量
    try:
        data = json.loads(response) if isinstance(response, str) else response
        
        if isinstance(data, dict) and "data" in data:
            # 只保留最近的 15 筆交易（而不是全部）
            if isinstance(data["data"], list):
                data["data"] = data["data"][:15]
            
            # 使用toon格式或JSON格式返回
            if use_toon:
                try:
                    from tradingagents.utils.toon_converter import convert_json_to_toon
                    return convert_json_to_toon(data)
                except Exception as e:
                    print(f"警告：toon轉換失敗：{e}，使用JSON格式")
                    return json.dumps(data, ensure_ascii=False, indent=2)
            else:
                return json.dumps(data, ensure_ascii=False, indent=2)
        
        return response
        
    except (json.JSONDecodeError, Exception) as e:
        print(f"警告：無法處理內部交易數據：{e}")
        return response
