"""Bulk data retrieval for stock screening.

Provides efficient batch operations for scanning entire markets,
bypassing LangChain tool wrappers for performance.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def get_krx_universe(
    min_market_cap: float = 500_000_000_000,
    min_volume: int = 100_000,
) -> pd.DataFrame:
    """Get all KRX-listed stocks filtered by market cap and volume.

    Returns DataFrame with columns: Code, Name, Market, Sector, MarketCap, Volume.
    """
    try:
        import FinanceDataReader as fdr
    except ImportError:
        raise ImportError("FinanceDataReader required: pip install finance-datareader")

    listing = None
    is_fallback = False
    try:
        listing = fdr.StockListing("KRX")
    except Exception as e:
        logger.warning(f"FDR KRX listing failed: {e}")

    if listing is None or listing.empty:
        logger.info("FDR failed, trying Naver Finance...")
        try:
            listing = _get_naver_krx_universe(
                min_market_cap=min_market_cap,
            )
            if listing is not None and not listing.empty:
                logger.info(f"Naver Finance universe: {len(listing)} stocks")
                return listing.reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Naver Finance failed: {e}")

        logger.info("Using fallback KRX universe (hardcoded top stocks)")
        listing = _get_krx_fallback_universe()
        is_fallback = True

    if listing.empty:
        return pd.DataFrame()

    # Normalize columns (FDR column names may vary)
    col_renames = {}
    for col in listing.columns:
        lower = col.lower()
        if lower in ("code", "symbol", "종목코드"):
            col_renames[col] = "Code"
        elif lower in ("name", "isu_abbrv", "종목명"):
            col_renames[col] = "Name"
        elif lower in ("market", "시장구분"):
            col_renames[col] = "Market"
        elif lower in ("sector", "업종명"):
            col_renames[col] = "Sector"
        elif lower in ("marketcap", "시가총액"):
            col_renames[col] = "MarketCap"

    listing = listing.rename(columns=col_renames)

    # Skip market cap / volume filters for fallback (already curated)
    if is_fallback:
        if "Volume" not in listing.columns:
            listing["Volume"] = 0
        return listing.reset_index(drop=True)

    # Filter by market cap if available
    if "MarketCap" in listing.columns:
        listing["MarketCap"] = pd.to_numeric(listing["MarketCap"], errors="coerce")
        listing = listing[listing["MarketCap"] >= min_market_cap]

    # Try to get volume data from pykrx for additional filtering
    try:
        from pykrx import stock as krx_stock

        vol_df = None
        for days_back in range(0, 10):
            try:
                target = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
                vol_df = krx_stock.get_market_ohlcv(target, market="ALL")
                if vol_df is not None and not vol_df.empty:
                    break
            except Exception:
                continue

        if vol_df is not None and not vol_df.empty:
            vol_df = vol_df.reset_index()
            vol_col = "거래량" if "거래량" in vol_df.columns else "Volume"
            ticker_col = "티커" if "티커" in vol_df.columns else vol_df.columns[0]

            vol_map = dict(zip(vol_df[ticker_col].astype(str), vol_df[vol_col]))
            listing["Volume"] = listing["Code"].map(vol_map).fillna(0)
            listing = listing[listing["Volume"] >= min_volume]
        else:
            logger.warning("Could not get volume data from pykrx")
            listing["Volume"] = 0
    except ImportError:
        logger.warning("pykrx not installed - skipping volume filter")
        listing["Volume"] = 0
    except Exception as e:
        logger.warning(f"Could not filter by volume: {e}")
        listing["Volume"] = 0

    return listing.reset_index(drop=True)


def get_us_universe(
    universe_type: str = "sp500",
    custom_watchlist: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Get US stock universe.

    Args:
        universe_type: "sp500", "nasdaq100", or "custom"
        custom_watchlist: List of tickers for custom universe
    """
    import yfinance as yf

    if universe_type == "custom" and custom_watchlist:
        tickers = custom_watchlist
    elif universe_type == "sp500":
        tickers = _get_sp500_tickers()
    elif universe_type == "nasdaq100":
        tickers = _get_nasdaq100_tickers()
    else:
        tickers = custom_watchlist or []

    if not tickers:
        return pd.DataFrame()

    rows = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            rows.append({
                "Code": ticker,
                "Name": info.get("longName", ticker),
                "Market": "US",
                "Sector": info.get("sector", ""),
                "MarketCap": info.get("marketCap", 0),
                "Volume": info.get("averageVolume", 0),
            })
        except Exception:
            rows.append({
                "Code": ticker,
                "Name": ticker,
                "Market": "US",
                "Sector": "",
                "MarketCap": 0,
                "Volume": 0,
            })

    return pd.DataFrame(rows)


def get_bulk_ohlcv(
    tickers: list[str],
    start_date: str,
    end_date: str,
    market: str = "KRX",
) -> dict[str, pd.DataFrame]:
    """Batch OHLCV retrieval for multiple tickers.

    Returns dict mapping ticker -> OHLCV DataFrame.
    """
    result = {}

    if market == "KRX":
        try:
            from pykrx import stock as krx_stock
        except ImportError:
            raise ImportError("pykrx required for KRX data: pip install pykrx")

        # pykrx uses YYYYMMDD format
        start_fmt = start_date.replace("-", "")
        end_fmt = end_date.replace("-", "")

        for ticker in tickers:
            try:
                ticker_padded = ticker.zfill(6)
                data = krx_stock.get_market_ohlcv(start_fmt, end_fmt, ticker_padded)
                if data is not None and not data.empty:
                    # Normalize column names to match expected format
                    col_map = {
                        "시가": "Open", "고가": "High", "저가": "Low",
                        "종가": "Close", "거래량": "Volume",
                    }
                    data = data.rename(columns=col_map)
                    result[ticker] = data
            except Exception as e:
                logger.warning(f"Failed to get OHLCV for {ticker}: {e}")

    elif market == "US":
        import yfinance as yf

        for ticker in tickers:
            try:
                data = yf.download(
                    ticker,
                    start=start_date,
                    end=end_date,
                    progress=False,
                    multi_level_index=False,
                    auto_adjust=True,
                )
                if data is not None and not data.empty:
                    result[ticker] = data
            except Exception as e:
                logger.warning(f"Failed to get OHLCV for {ticker}: {e}")

    return result


def compute_screening_indicators(df: pd.DataFrame) -> dict:
    """Compute screening indicators from OHLCV DataFrame.

    Returns dict with indicator values for screening decisions.
    """
    if df is None or len(df) < 20:
        return {}

    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else None

    indicators = {}

    # Moving averages
    if len(close) >= 50:
        indicators["sma_10"] = close.rolling(10).mean().iloc[-1]
        indicators["sma_20"] = close.rolling(20).mean().iloc[-1]
        indicators["sma_50"] = close.rolling(50).mean().iloc[-1]
        indicators["ema_10"] = close.ewm(span=10).mean().iloc[-1]
        indicators["ema_20"] = close.ewm(span=20).mean().iloc[-1]
    else:
        indicators["sma_10"] = close.rolling(10).mean().iloc[-1]
        indicators["sma_20"] = close.rolling(20).mean().iloc[-1]
        indicators["ema_10"] = close.ewm(span=10).mean().iloc[-1]

    indicators["current_price"] = close.iloc[-1]
    indicators["prev_close"] = close.iloc[-2] if len(close) >= 2 else close.iloc[-1]

    # RSI (14-day)
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("inf"))
        rsi = 100 - (100 / (1 + rs))
        indicators["rsi"] = rsi.iloc[-1]
        indicators["rsi_prev"] = rsi.iloc[-2] if len(rsi) >= 2 else rsi.iloc[-1]

    # Volume analysis
    if volume is not None and len(volume) >= 20:
        indicators["volume_current"] = volume.iloc[-1]
        vol_avg_20 = volume.rolling(20).mean().iloc[-1]
        indicators["volume_avg_20"] = vol_avg_20
        if vol_avg_20 and vol_avg_20 > 0:
            indicators["volume_ratio"] = volume.iloc[-1] / vol_avg_20
        else:
            indicators["volume_ratio"] = 0.0

    # Bollinger Bands
    if len(close) >= 20:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        indicators["boll_upper"] = (sma20 + 2 * std20).iloc[-1]
        indicators["boll_lower"] = (sma20 - 2 * std20).iloc[-1]
        indicators["boll_middle"] = sma20.iloc[-1]

    # Price change
    if len(close) >= 5:
        indicators["pct_change_1d"] = (close.iloc[-1] / close.iloc[-2] - 1) * 100
        indicators["pct_change_5d"] = (close.iloc[-1] / close.iloc[-5] - 1) * 100
    if len(close) >= 20:
        indicators["pct_change_20d"] = (close.iloc[-1] / close.iloc[-20] - 1) * 100

    return indicators


def _get_sp500_tickers() -> list[str]:
    """Get S&P 500 ticker list from Wikipedia."""
    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        return table[0]["Symbol"].tolist()
    except Exception:
        # Fallback: top 50 by market cap
        return [
            "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B", "TSLA",
            "UNH", "LLY", "JPM", "XOM", "V", "JNJ", "PG", "MA", "AVGO",
            "HD", "MRK", "COST", "ABBV", "CVX", "PEP", "KO", "ADBE",
            "WMT", "CRM", "MCD", "CSCO", "ACN", "BAC", "NFLX", "TMO",
            "AMD", "LIN", "ABT", "ORCL", "DHR", "CMCSA", "PFE", "DIS",
            "WFC", "PM", "INTC", "VZ", "INTU", "COP", "AMGN", "IBM", "GE",
        ]


def _get_nasdaq100_tickers() -> list[str]:
    """Get NASDAQ 100 ticker list."""
    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
        for t in table:
            if "Ticker" in t.columns:
                return t["Ticker"].tolist()
            if "Symbol" in t.columns:
                return t["Symbol"].tolist()
    except Exception:
        pass

    # Fallback: major NASDAQ 100 components
    return [
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO",
        "COST", "ADBE", "NFLX", "AMD", "PEP", "CSCO", "INTC", "INTU",
        "CMCSA", "AMGN", "TMUS", "TXN", "QCOM", "ISRG", "BKNG", "HON",
        "AMAT", "VRTX", "ADP", "GILD", "SBUX", "MDLZ", "ADI", "LRCX",
        "PANW", "MU", "REGN", "SNPS", "KLAC", "CDNS", "PYPL", "MAR",
    ]


def _get_naver_krx_universe(
    min_market_cap: float = 500_000_000_000,
    max_pages: int = 10,
) -> pd.DataFrame:
    """Get KRX stocks from Naver Finance market cap ranking.

    Scrapes KOSPI (sosok=0) and KOSDAQ (sosok=1) pages.
    Returns DataFrame with columns: Code, Name, Market, Sector, MarketCap, Volume.
    """
    from bs4 import BeautifulSoup

    all_rows = []

    for sosok, market_name in [(0, "KOSPI"), (1, "KOSDAQ")]:
        for page in range(1, max_pages + 1):
            url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
            try:
                resp = requests.get(url, headers=_NAVER_HEADERS, timeout=10)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"Naver Finance request failed (sosok={sosok}, page={page}): {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Parse table rows
            table = soup.select_one("table.type_2")
            if not table:
                break

            rows = table.select("tr")
            found_any = False
            for row in rows:
                tds = row.select("td")
                if len(tds) < 10:
                    continue

                # Extract ticker code from link
                link = tds[1].select_one("a[href*='/item/main.naver?code=']")
                if not link:
                    continue

                code_match = re.search(r"code=(\d+)", link["href"])
                if not code_match:
                    continue

                code = code_match.group(1).zfill(6)
                name = link.text.strip()

                # Parse numeric values (remove commas)
                def parse_num(td):
                    text = td.text.strip().replace(",", "").replace("%", "")
                    try:
                        return float(text)
                    except ValueError:
                        return 0

                market_cap = parse_num(tds[6]) * 1_0000_0000  # 억 → 원
                volume = parse_num(tds[9])

                all_rows.append({
                    "Code": code,
                    "Name": name,
                    "Market": market_name,
                    "Sector": "",
                    "MarketCap": market_cap,
                    "Volume": volume,
                })
                found_any = True

            if not found_any:
                break

            time.sleep(0.3)  # Rate limiting

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Filter by market cap
    if min_market_cap > 0:
        df = df[df["MarketCap"] >= min_market_cap]

    logger.info(f"Naver Finance: {len(df)} stocks loaded")
    return df.reset_index(drop=True)


def _get_krx_fallback_universe() -> pd.DataFrame:
    """Fallback KRX universe when API listing is unavailable.

    Returns top ~100 KRX stocks by market cap (hardcoded).
    """
    # Top KRX stocks (KOSPI large-cap + select KOSDAQ)
    stocks = [
        ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
        ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
        ("006400", "삼성SDI"), ("051910", "LG화학"), ("035420", "NAVER"),
        ("035720", "카카오"), ("068270", "셀트리온"), ("028260", "삼성물산"),
        ("105560", "KB금융"), ("055550", "신한지주"), ("012330", "현대모비스"),
        ("066570", "LG전자"), ("003670", "포스코퓨처엠"), ("096770", "SK이노베이션"),
        ("034730", "SK"), ("015760", "한국전력"), ("003550", "LG"),
        ("032830", "삼성생명"), ("086790", "하나금융지주"), ("316140", "우리금융지주"),
        ("010130", "고려아연"), ("009150", "삼성전기"), ("033780", "KT&G"),
        ("030200", "KT"), ("017670", "SK텔레콤"), ("000810", "삼성화재"),
        ("018260", "삼성에스디에스"), ("036570", "엔씨소프트"), ("034020", "두산에너빌리티"),
        ("003490", "대한항공"), ("011200", "HMM"), ("010950", "S-Oil"),
        ("326030", "SK바이오팜"), ("259960", "크래프톤"), ("352820", "하이브"),
        ("011170", "롯데케미칼"), ("090430", "아모레퍼시픽"), ("051900", "LG생활건강"),
        ("000720", "현대건설"), ("034220", "LG디스플레이"), ("010140", "삼성중공업"),
        ("009540", "HD한국조선해양"), ("329180", "HD현대중공업"), ("042670", "HD현대인프라코어"),
        ("267260", "HD현대"), ("402340", "SK스퀘어"), ("361610", "SK아이이테크놀로지"),
        ("377300", "카카오페이"), ("035900", "JYP Ent."), ("041510", "에스엠"),
        ("263750", "펄어비스"), ("112040", "위메이드"), ("293490", "카카오게임즈"),
        ("047050", "포스코인터내셔널"), ("005490", "POSCO홀딩스"), ("138040", "메리츠금융지주"),
        ("006800", "미래에셋증권"), ("003410", "쌍용C&E"), ("069500", "KODEX 200"),
        ("161390", "한국타이어앤테크놀로지"), ("024110", "기업은행"), ("078930", "GS"),
        ("036460", "한국가스공사"), ("004020", "현대제철"), ("011790", "SKC"),
        ("180640", "한진칼"), ("097950", "CJ제일제당"), ("028050", "삼성엔지니어링"),
        ("000100", "유한양행"), ("128940", "한미약품"), ("004990", "롯데지주"),
        ("032640", "LG유플러스"), ("009830", "한화솔루션"), ("272210", "한화시스템"),
        ("016360", "삼성증권"), ("088350", "한화생명"), ("001570", "금양"),
        ("053800", "안랩"), ("122870", "와이지엔터테인먼트"), ("145020", "휴젤"),
        ("247540", "에코프로비엠"), ("086520", "에코프로"),
    ]

    return pd.DataFrame([
        {"Code": code, "Name": name, "Market": "KRX", "Sector": "", "MarketCap": 0, "Volume": 0}
        for code, name in stocks
    ])

if __name__ == "__main__":
    get_krx_universe()