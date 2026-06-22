"""
네이버 증권 종목 상세 정보 크롤러.

데이터 소스:
  1. stock.naver.com API  — Forward PER, 현재 PER/EPS/PBR, 컨센서스, 일별 시세
  2. navercomp.wisereport.co.kr — 연간/분기 재무표 (네이버 증권 회사 페이지 iframe 소스)

URL 예시: https://stock.naver.com/domestic/stock/000660/info/company
"""

import json
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

_NAVER_BASE = "https://stock.naver.com"
_WISE_BASE = "https://navercomp.wisereport.co.kr/v3"

_NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://stock.naver.com/",
}
_WISE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://navercomp.wisereport.co.kr/",
}


def _fetch_json(url: str, headers: dict):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _fetch_html(url: str, headers: dict) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip().replace("\xa0", "").replace(",", "")


@dataclass
class StockDetail:
    code: str
    name: str
    market: str               # KOSPI / KOSDAQ
    price: int
    change_rate: float
    per: Optional[float]      # 현재 PER (trailing)
    forward_per: Optional[float]  # 선행 PER (estimated)
    eps: Optional[float]
    forward_eps: Optional[float]
    pbr: Optional[float]
    bps: Optional[float]
    dividend: Optional[float]      # 배당금(원)
    dividend_rate: Optional[float] # 배당수익률(%)
    market_cap: int               # 시가총액(원)
    foreign_hold_rate: float      # 외국인보유율(%)
    industry: str
    industry_per: Optional[float]
    target_price: Optional[int]   # 컨센서스 목표가
    analyst_opinion: Optional[float]  # 1=매도 ~ 5=적극매수
    description: list[str]        # 회사 설명 comment1~3


def get_stock_detail(code: str) -> StockDetail:
    """종목 상세 정보 조회 (stock.naver.com API).

    Forward PER, 현재 PER/EPS/PBR, 배당, 시총, 컨센서스 목표가 포함.
    """
    detail = _fetch_json(
        f"{_NAVER_BASE}/api/domestic/detail/{code}/detail?codeType=",
        _NAVER_HEADERS,
    )
    consensus = _fetch_json(
        f"{_NAVER_BASE}/api/domestic/detail/{code}/consensus",
        _NAVER_HEADERS,
    )

    def _f(v):
        try: return float(v) if v is not None else None
        except: return None

    return StockDetail(
        code=detail["itemcode"],
        name=detail["itemname"],
        market="KOSDAQ" if detail.get("sosok") == "1" else "KOSPI",
        price=int(detail["nowPrice"]),
        change_rate=_f(detail.get("prevChangeRate")) or 0.0,
        per=_f(detail.get("per")),
        forward_per=_f(detail.get("estimatedPer")),
        eps=_f(detail.get("eps")),
        forward_eps=_f(detail.get("estimatedEps")),
        pbr=_f(detail.get("pbr")),
        bps=_f(detail.get("bps")),
        dividend=_f(detail.get("dividendAmount")),
        dividend_rate=_f(detail.get("dividendRate")),
        market_cap=int(float(detail.get("marketSum") or 0)),
        foreign_hold_rate=_f(detail.get("frgnHoldRate")) or 0.0,
        industry=detail.get("upJongName", ""),
        industry_per=_f(detail.get("sameIndustryPer")),
        target_price=int(float(consensus.get("targetPrice") or 0)) or None,
        analyst_opinion=_f(consensus.get("opinion")),
        description=[
            detail.get("comment1") or "",
            detail.get("comment2") or "",
            detail.get("comment3") or "",
        ],
    )


def get_annual_estimates(code: str, fin_gubun: str = "IFRSL") -> list[dict]:
    """연간 3년 실적 + 2년 추정 데이터 (cF1002.aspx).

    반환: [
      {'period': '2025.12', 'type': 'A', 'eps': 58955, 'per': 11.04, 'pbr': 3.73, ...},
      {'period': '2026.12', 'type': 'E', 'eps': 305208, 'per': 9.06, ...},
      {'period': '2027.12', 'type': 'E', 'eps': 419183, 'per': 6.59, ...},
    ]
    """
    url = (
        f"{_WISE_BASE}/company/cF1002.aspx"
        f"?cmp_cd={code}&frqTyp=A&finGubun={fin_gubun}&cn="
    )
    html = _fetch_html(url, _WISE_HEADERS)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    results = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        vals = [_clean(c) for c in cells]
        if not vals or not re.match(r"\d{4}\.\d{2}", vals[0]):
            continue
        m = re.match(r"(\d{4}\.\d{2})\((A|E)\)", vals[0])
        if not m:
            continue
        def _f(v):
            try: return float(v) if v and v != "N/A" else None
            except: return None
        results.append({
            "period": m.group(1),
            "type": m.group(2),       # 'A'=actual, 'E'=estimate
            "sales": _f(vals[1]),
            "sales_yoy": _f(vals[2]),
            "op_profit": _f(vals[3]),
            "net_profit": _f(vals[4]),
            "eps": _f(vals[5]),
            "per": _f(vals[6]),
            "pbr": _f(vals[7]),
            "roe": _f(vals[8]),
            "ev_ebitda": _f(vals[9]),
        })
    return results


def get_financials(code: str, freq: str = "A", fin_gubun: str = "MAIN") -> dict:
    """연간/분기 재무표 조회 (WiseReport - 네이버 회사정보 페이지 iframe 데이터).

    freq: 'A' = 연간, 'Q' = 분기
    fin_gubun: 'MAIN' = 주재무제표, 'IFRSL' = K-IFRS연결, 'IFRSS' = K-IFRS별도

    반환: {
      'periods': ['2022/12', '2023/12', ...],   # 기간 헤더
      'data': {                                   # 지표별 값 리스트
          '매출액': [446216, 327657, ...],
          '영업이익': [...],
          'PER(배)': [...],
          'EPS(원)': [...],
          ...
      }
    }
    """
    url = (
        f"{_WISE_BASE}/company/cF1001.aspx"
        f"?cmp_cd={code}&frq=0&rpt=1&finGubun={fin_gubun}&frqTyp={freq}&cn="
    )
    html = _fetch_html(url, _WISE_HEADERS)

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)

    # Parse header row: find date cells (YYYY/MM format)
    periods: list[str] = []
    data: dict[str, list] = {}

    for row in rows:
        cells_raw = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        cells = [_clean(c) for c in cells_raw]
        cells = [c for c in cells if c]
        if not cells:
            continue

        # Detect period header row (cells match YYYY/MM pattern)
        if re.match(r"\d{4}/\d{2}", cells[0]):
            periods = cells
            continue

        # Data row: first cell is the metric name
        label = cells[0]
        if not label or label in ("주요재무정보", "연간", "분기"):
            continue

        values = []
        for v in cells[1:]:
            try:
                values.append(float(v.replace("%", "").replace("배", "").replace("원", "")))
            except ValueError:
                values.append(None)

        if values:
            data[label] = values

    return {"periods": periods, "data": data}


def print_company_report(code: str) -> None:
    """종목 종합 리포트 출력."""
    d = get_stock_detail(code)
    print(f"\n{'='*60}")
    print(f"[{d.market}] {d.code} {d.name}")
    print(f"{'='*60}")
    print(f"현재가:        {d.price:>12,}원  ({d.change_rate:+.2f}%)")
    print(f"시가총액:      {d.market_cap//100_000_000:>12,}억원")
    print(f"외국인보유:    {d.foreign_hold_rate:>11.2f}%")
    print(f"업종:          {d.industry}")
    print()
    print(f"PER(현재):     {d.per or 'N/A':>12}배")
    print(f"Forward PER:   {d.forward_per or 'N/A':>12}배  ← 선행")
    print(f"EPS:           {d.eps or 'N/A':>12}원")
    print(f"Forward EPS:   {d.forward_eps or 'N/A':>12}원")
    print(f"PBR:           {d.pbr or 'N/A':>12}배")
    print(f"BPS:           {d.bps or 'N/A':>12}원")
    print(f"배당금:        {d.dividend or 'N/A':>12}원  ({d.dividend_rate or 0:.2f}%)")
    print(f"업종PER:       {d.industry_per or 'N/A':>12}배")
    print()
    print(f"목표주가:      {d.target_price:>12,}원" if d.target_price else "목표주가:      N/A")
    print(f"애널리스트:    {d.analyst_opinion or 'N/A':>12}  (1=매도~5=적극매수)")
    print()

    # Annual financials
    try:
        fin = get_financials(code, freq="A")
        if fin["periods"]:
            key_metrics = ["매출액", "영업이익", "당기순이익", "EPS(원)", "PER(배)", "PBR(배)"]
            header = f"{'지표':<20}" + "".join(f"{p:>16}" for p in fin["periods"])
            print(f"[연간 재무요약] (단위: 억원, 배수)")
            print(header)
            print("-" * len(header))
            for metric in key_metrics:
                if metric in fin["data"]:
                    vals = fin["data"][metric]
                    row = f"{metric:<20}"
                    for v in vals:
                        if v is None:
                            row += f"{'N/A':>16}"
                        elif metric in ("PER(배)", "PBR(배)"):
                            row += f"{v:>16.2f}"
                        elif metric == "EPS(원)":
                            row += f"{v:>16,.0f}"
                        else:
                            row += f"{v/100:>16,.0f}"
                    print(row)
    except Exception as e:
        print(f"[재무표 조회 실패: {e}]")


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "000660"
    print_company_report(code)
