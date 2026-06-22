"""
네이버 증권 상위 종목 크롤러.

API: stock.naver.com 내부 엔드포인트 (비공식)
- 국내: /api/domestic/market/stock/default?orderType=<type>
- 미국: /api/foreign/market/stock/global?nation=usa&orderType=<type>

orderType 값:
  quantTop  — 거래량 상위
  priceTop  — 거래대금 상위
  searchTop — 검색 상위
  marketSum — 시가총액 상위 (국내)
  marketValue — 시가총액 상위 (미국)
"""

import json
import urllib.request
from datetime import datetime

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://stock.naver.com/",
}
_BASE = "https://stock.naver.com"


def _fetch(path: str) -> list:
    req = urllib.request.Request(_BASE + path, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get_domestic_ranking(order_type: str, page: int = 1, page_size: int = 20) -> list[dict]:
    """국내 주식 랭킹.

    order_type: 'quantTop' | 'priceTop' | 'searchTop' | 'marketSum'
    반환: code, name, market, price, change_rate, trade_volume, trade_amount, per, eps, pbr
    """
    raw = _fetch(
        f"/api/domestic/market/stock/default"
        f"?orderType={order_type}&page={page}&pageSize={page_size}"
    )
    return [
        {
            "code": s["itemcode"],
            "name": s["itemname"],
            "market": "KOSDAQ" if s.get("sosok") == "1" else "KOSPI",
            "price": int(s.get("nowPrice") or 0),
            "change_rate": float(s.get("prevChangeRate") or 0),
            "trade_volume": int(s.get("tradeVolume") or 0),
            "trade_amount": int(s.get("tradeAmount") or 0),
            "per": s.get("per"),
            "eps": s.get("eps"),
            "pbr": s.get("pbr"),
        }
        for s in raw
    ]


def get_us_ranking(
    order_type: str,
    trade_type: str = "ALL",
    page_size: int = 20,
    start: int = 0,
) -> list[dict]:
    """미국 주식 랭킹.

    order_type: 'quantTop' | 'priceTop' | 'marketValue'
    trade_type: 'ALL' | 'NSQ' | 'NYS' | 'AMX'
    반환: code, name, exchange, price, change_rate, trade_volume, trade_amount
    """
    raw = _fetch(
        f"/api/foreign/market/stock/global"
        f"?nation=usa&tradeType={trade_type}&orderType={order_type}"
        f"&start={start}&pageSize={page_size}"
    )
    results = []
    for s in raw:
        exch = s.get("stockExchangeType") or {}
        results.append(
            {
                "code": s.get("reutersCode", ""),
                "name": s.get("stockName", ""),
                "exchange": exch.get("code", "") if isinstance(exch, dict) else str(exch),
                "price": float(s.get("closePrice") or 0),
                "change_rate": float(s.get("risefall") or 0),
                "trade_volume": int(s.get("accumulatedTradingVolume") or 0),
                "trade_amount": int(s.get("accumulatedTradingValue") or 0),
            }
        )
    return results


def print_ranking_report(top_n: int = 10) -> None:
    """국내/미국 5개 카테고리 랭킹 출력."""
    print(f"=== 네이버 증권 상위 종목 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===\n")

    sections = [
        ("【국내 거래량 상위】", get_domestic_ranking("quantTop", page_size=top_n), "domestic"),
        ("【국내 거래대금 상위】", get_domestic_ranking("priceTop", page_size=top_n), "domestic"),
        ("【국내 검색 상위】", get_domestic_ranking("searchTop", page_size=top_n), "domestic"),
        ("【미국 거래량 상위】", get_us_ranking("quantTop", page_size=top_n), "us"),
        ("【미국 거래대금 상위】", get_us_ranking("priceTop", page_size=top_n), "us"),
    ]

    for title, stocks, kind in sections:
        print(title)
        for i, s in enumerate(stocks[:top_n], 1):
            if kind == "domestic":
                amt = s["trade_amount"] // 100_000_000
                print(
                    f"  {i:2d}. [{s['market']}] {s['code']} {s['name']} | "
                    f"거래량:{s['trade_volume']:,} | 거래대금:{amt:,}억 | PER:{s['per'] or 'N/A'}"
                )
            else:
                print(
                    f"  {i:2d}. [{s['exchange']}] {s['code']} {s['name']} | "
                    f"${s['price']:.2f} | 거래량:{s['trade_volume']:,}"
                )
        print()


if __name__ == "__main__":
    print_ranking_report(top_n=10)
