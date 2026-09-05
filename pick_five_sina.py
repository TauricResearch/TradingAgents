"""Pick five 60/000 main-board candidates using Sina Finance APIs."""

from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn",
}
MARKET_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)
KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)
EXCLUDED_TICKERS = {"601665", "601083", "000902", "603529", "600583"}

# Bounded concurrency so Sina isn't hammered, but the ~50 quote pages and the
# top-100 kline checks no longer run one-at-a-time over the network. Pages are
# fetched in small waves (like the old serial loop, which stopped at the first
# short page) so we never request pages past the end of the market — that is
# what triggers Sina's 456 rate-limit responses.
QUOTE_PAGE_WORKERS = 4
QUOTE_PAGE_WAVE = 4
KLINE_WORKERS = 6
MAX_QUOTE_PAGES = 60  # 60 x 100 rows covers the full A-share market
PAGE_RETRIES = 3


def _fetch_quote_page(page: int) -> list[dict]:
    """Fetch one quote page, retrying up to PAGE_RETRIES times."""
    params = {
        "page": page,
        "num": 100,
        "sort": "symbol",
        "asc": 1,
        "node": "hs_a",
        "symbol": "",
        "_s_r_a": "page",
    }
    for attempt in range(PAGE_RETRIES):
        try:
            resp = requests.get(MARKET_URL, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            batch = resp.json()
            if isinstance(batch, list):
                return batch
        except requests.RequestException as exc:
            print(f"quote page {page} attempt {attempt + 1}/{PAGE_RETRIES} failed: {exc}")
            # 456 is Sina's rate-limit signal: back off harder than for a plain
            # network blip so the retry has a chance to land.
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"quote page {page} failed after {PAGE_RETRIES} attempts")


def fetch_quotes() -> list[dict]:
    """Fetch A-share quote pages in small concurrent waves, preserving order.

    Page 1 is fetched alone (it reports the page size), then the remaining
    pages are fetched in waves of QUOTE_PAGE_WAVE. Collecting stops at the
    first short page — exactly like the previous serial loop — so no requests
    are made past the end of the market.
    """
    first = _fetch_quote_page(1)
    if not first:
        return []

    rows: list[dict] = []
    rows.extend(first)
    if len(first) < 100:
        return rows

    next_page = 2
    with ThreadPoolExecutor(max_workers=QUOTE_PAGE_WORKERS) as ex:
        while next_page <= MAX_QUOTE_PAGES:
            wave = range(next_page, min(next_page + QUOTE_PAGE_WAVE, MAX_QUOTE_PAGES + 1))
            futures = {ex.submit(_fetch_quote_page, page): page for page in wave}
            batches = {page: fut.result() for fut, page in futures.items()}
            for page in wave:
                batch = batches[page]
                rows.extend(batch)
                if len(batch) < 100:
                    return rows
            next_page += QUOTE_PAGE_WAVE
    if len(rows) % 100 == 0 and rows:
        print(
            f"warning: last page was full; market may extend past page "
            f"{MAX_QUOTE_PAGES} — raise MAX_QUOTE_PAGES if rows look truncated"
        )
    return rows


def _enrich_with_kline(top: list[dict]) -> list[dict]:
    """Check trend filters for the top candidates concurrently."""
    enriched = []
    with ThreadPoolExecutor(max_workers=KLINE_WORKERS) as ex:
        futures = {}
        for item in top:
            futures[ex.submit(fetch_kline, item["symbol"])] = item
            # Space out submissions so the kline endpoint never sees a hard
            # burst from the executor's queue.
            time.sleep(0.05)
        for fut in as_completed(futures):
            item = futures[fut]
            kline = fut.result()
            if len(kline) < 61:
                continue
            closes = [float(k["close"]) for k in kline]
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / 60
            mom60 = closes[-1] / closes[-61] - 1
            item["ma20"] = round(ma20, 2)
            item["ma60"] = round(ma60, 2)
            item["mom60"] = round(mom60 * 100, 2)
            if closes[-1] > ma20 and closes[-1] > ma60 and mom60 > 0:
                enriched.append(item)
    return enriched


def fetch_kline(symbol: str) -> list[dict]:
    params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": 80}
    for attempt in range(3):
        try:
            resp = requests.get(KLINE_URL, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except requests.RequestException as exc:
            print(f"kline {symbol} attempt {attempt + 1} failed: {exc}")
            time.sleep(2)
    return []


def quote_score(row: dict) -> float:
    per = row["per"]
    pb = row["pb"]
    cap_yi = row["mktcap_yi"]
    amount = row["amount"]
    turnover = row["turnoverratio"]

    s = 0.0
    if 0 < per <= 30:
        s += (30 - per) / 30 * 3
    if 0 < pb <= 5:
        s += (5 - pb) / 5 * 1.5
    if 80 <= cap_yi <= 600:
        s += 1.0
    elif 40 <= cap_yi < 80 or 600 < cap_yi <= 1000:
        s += 0.5
    if amount:
        s += min(math.log10(max(amount, 1)), 9.5) / 9.5 * 0.8
    if turnover:
        s += min(turnover, 10) / 10 * 0.5
    return round(s, 3)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    quotes = fetch_quotes()
    print(f"quotes total: {len(quotes)}")

    candidates = []
    for row in quotes:
        code = str(row.get("code", ""))
        name = str(row.get("name", ""))
        if not code.startswith(("60", "000")):
            continue
        if code in EXCLUDED_TICKERS:
            continue
        if "ST" in name.upper() or "退" in name:
            continue
        try:
            price = float(row.get("trade") or 0)
            amount = float(row.get("amount") or 0)
            per = float(row.get("per") or 0)
            pb = float(row.get("pb") or 0)
            cap_yi = float(row.get("mktcap") or 0) / 10000
            turnover = float(row.get("turnoverratio") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or amount < 2e8:
            continue
        if not (50 <= cap_yi <= 1000):
            continue
        if not (0 < per <= 30):
            continue
        if not (0 < pb <= 5):
            continue
        if turnover <= 0.3:
            continue

        item = {
            "code": code,
            "symbol": row["symbol"],
            "name": name,
            "price": price,
            "amount_yi": round(amount / 1e8, 2),
            "per": round(per, 2),
            "pb": round(pb, 2),
            "mktcap_yi": round(cap_yi, 0),
            "turnoverratio": round(turnover, 2),
            "score": quote_score(
                {
                    "per": per,
                    "pb": pb,
                    "mktcap_yi": cap_yi,
                    "amount": amount,
                    "turnoverratio": turnover,
                }
            ),
        }
        candidates.append(item)

    candidates.sort(key=lambda r: r["score"], reverse=True)
    top = candidates[:100]
    print(f"filtered candidates: {len(candidates)}, checking klines for top {len(top)}")

    enriched = _enrich_with_kline(top)
    enriched.sort(key=lambda r: r["score"], reverse=True)
    chosen = enriched[:5]

    print("\nchosen5:")
    for r in chosen:
        print(
            f"{r['code']} {r['name']} price={r['price']} pe={r['per']} "
            f"pb={r['pb']} cap={r['mktcap_yi']}e8 ma20={r['ma20']} "
            f"ma60={r['ma60']} mom60={r['mom60']}% score={r['score']}"
        )

    print("\ntop20 candidates (for reference):")
    for r in enriched[:20]:
        print(
            f"{r['code']} {r['name']} price={r['price']} pe={r['per']} "
            f"pb={r['pb']} cap={r['mktcap_yi']}e8 mom60={r['mom60']}% "
            f"score={r['score']}"
        )


if __name__ == "__main__":
    main()
