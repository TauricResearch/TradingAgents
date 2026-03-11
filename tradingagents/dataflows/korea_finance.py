"""Korean market data source using FinanceDataReader and web scraping.

Provides KRX stock data (OHLCV), technical indicators, exchange rates,
KOSPI/KOSDAQ index data, and foreign/institutional investor flow data.
"""

from typing import Annotated
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
import pandas as pd

try:
    import FinanceDataReader as fdr
except ImportError:
    fdr = None


def _ensure_fdr():
    if fdr is None:
        raise ImportError(
            "FinanceDataReader is required for Korean market data. "
            "Install it with: pip install finance-datareader"
        )


def _normalize_krx_symbol(symbol: str) -> str:
    """Normalize KRX stock symbol (e.g., '005930' for Samsung Electronics).

    Handles both pure numeric codes and codes with market suffix like '005930.KS'.
    """
    symbol = symbol.strip().upper()
    # Remove market suffixes
    for suffix in [".KS", ".KQ", ".KRX"]:
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
    return symbol


def get_krx_stock_data(
    symbol: Annotated[str, "KRX ticker symbol (e.g., '005930' for Samsung Electronics)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve KRX stock OHLCV data using FinanceDataReader."""
    _ensure_fdr()

    symbol = _normalize_krx_symbol(symbol)

    try:
        data = fdr.DataReader(symbol, start_date, end_date)

        if data is None or data.empty:
            return f"No data found for KRX symbol '{symbol}' between {start_date} and {end_date}"

        # Standardize column names
        col_map = {
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Volume": "Volume",
            "Change": "Change",
        }
        data = data.rename(columns={k: v for k, v in col_map.items() if k in data.columns})

        # Round numeric columns
        for col in ["Open", "High", "Low", "Close"]:
            if col in data.columns:
                data[col] = data[col].round(0).astype(int)

        csv_string = data.to_csv()

        header = f"# KRX Stock data for {symbol} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(data)}\n"
        header += f"# Currency: KRW (Korean Won)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving KRX stock data for {symbol}: {str(e)}"


def get_krx_indicators(
    symbol: Annotated[str, "KRX ticker symbol"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "Current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Calculate technical indicators for KRX stocks using FinanceDataReader + stockstats."""
    _ensure_fdr()
    from stockstats import wrap

    symbol = _normalize_krx_symbol(symbol)

    best_ind_params = {
        "close_50_sma": "50 SMA: 중기 추세 지표. 추세 방향 및 동적 지지/저항 확인.",
        "close_200_sma": "200 SMA: 장기 추세 기준선. 골든크로스/데드크로스 확인.",
        "close_10_ema": "10 EMA: 단기 반응형 이동평균. 빠른 모멘텀 변화 포착.",
        "macd": "MACD: EMA 차이 기반 모멘텀 지표. 크로스오버/다이버전스 확인.",
        "macds": "MACD Signal: MACD 스무딩 라인. 매매 시그널 트리거.",
        "macdh": "MACD Histogram: MACD와 시그널 차이. 모멘텀 강도/다이버전스.",
        "rsi": "RSI: 과매수/과매도 판단. 70/30 기준선, 다이버전스 확인.",
        "boll": "Bollinger Middle: 20 SMA 기반. 가격 움직임 기준선.",
        "boll_ub": "Bollinger Upper: +2σ. 과매수/돌파 구간.",
        "boll_lb": "Bollinger Lower: -2σ. 과매도/반등 구간.",
        "atr": "ATR: 변동성 측정. 손절가/포지션 사이즈 결정 기준.",
        "vwma": "VWMA: 거래량 가중 이동평균. 거래량과 가격 통합 추세 확인.",
        "mfi": "MFI: 자금흐름지수. 가격+거래량 기반 과매수(>80)/과매도(<20) 판단.",
    }

    if indicator not in best_ind_params:
        return (
            f"Indicator '{indicator}' not supported. "
            f"Available: {list(best_ind_params.keys())}"
        )

    try:
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        # Fetch extra data for indicator calculation warmup
        fetch_start = (curr_date_dt - relativedelta(years=1)).strftime("%Y-%m-%d")
        fetch_end = curr_date

        data = fdr.DataReader(symbol, fetch_start, fetch_end)
        if data is None or data.empty:
            return f"No data for KRX symbol '{symbol}'"

        data = data.reset_index()
        # Ensure Date column exists
        if "Date" not in data.columns:
            data = data.rename(columns={data.columns[0]: "Date"})

        df = wrap(data)
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

        # Calculate indicator
        df[indicator]

        # Build result for look_back period
        before = curr_date_dt - relativedelta(days=look_back_days)
        result_dict = {}
        for _, row in df.iterrows():
            date_str = row["Date"]
            val = row[indicator]
            result_dict[date_str] = "N/A" if pd.isna(val) else str(round(float(val), 4))

        ind_string = ""
        current_dt = curr_date_dt
        while current_dt >= before:
            date_str = current_dt.strftime("%Y-%m-%d")
            value = result_dict.get(date_str, "N/A: 비거래일 (주말/공휴일)")
            ind_string += f"{date_str}: {value}\n"
            current_dt -= timedelta(days=1)

        return (
            f"## {indicator} values for KRX:{symbol} "
            f"from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + ind_string
            + f"\n\n{best_ind_params[indicator]}"
        )

    except Exception as e:
        return f"Error calculating indicator for KRX:{symbol}: {str(e)}"


def get_exchange_rate(
    currency_pair: Annotated[str, "Currency pair (e.g., 'USD/KRW', 'JPY/KRW', 'EUR/KRW')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve exchange rate data using FinanceDataReader."""
    _ensure_fdr()

    try:
        data = fdr.DataReader(currency_pair, start_date, end_date)

        if data is None or data.empty:
            return f"No exchange rate data for '{currency_pair}' between {start_date} and {end_date}"

        csv_string = data.to_csv()

        header = f"# Exchange Rate: {currency_pair} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(data)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving exchange rate for {currency_pair}: {str(e)}"


def get_korea_index_data(
    index_code: Annotated[str, "Index code: 'KS11' (KOSPI), 'KQ11' (KOSDAQ), 'KS200' (KOSPI200)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve Korean market index data (KOSPI, KOSDAQ, KOSPI200)."""
    _ensure_fdr()

    index_names = {
        "KS11": "KOSPI",
        "KQ11": "KOSDAQ",
        "KS200": "KOSPI 200",
        "KS50": "KOSPI 50",
    }

    index_name = index_names.get(index_code, index_code)

    try:
        data = fdr.DataReader(index_code, start_date, end_date)

        if data is None or data.empty:
            return f"No index data found for '{index_name}' between {start_date} and {end_date}"

        csv_string = data.to_csv()

        header = f"# {index_name} Index Data from {start_date} to {end_date}\n"
        header += f"# Total records: {len(data)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving {index_name} index data: {str(e)}"


def get_investor_trading_data(
    symbol: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve foreign and institutional investor trading (buy/sell) data for a KRX stock.

    Uses pykrx for detailed investor flow data.
    """
    symbol = _normalize_krx_symbol(symbol)

    try:
        from pykrx import stock as krx_stock

        # Get investor trading data by investor type
        df = krx_stock.get_market_trading_value_by_investor(
            start_date.replace("-", ""),
            end_date.replace("-", ""),
            symbol,
        )

        if df is None or df.empty:
            return f"No investor trading data found for '{symbol}' between {start_date} and {end_date}"

        csv_string = df.to_csv()

        header = f"# 투자자별 매매동향: {symbol} ({start_date} ~ {end_date})\n"
        header += f"# 단위: KRW (원)\n"
        header += f"# 양수 = 순매수 (Net Buy), 음수 = 순매도 (Net Sell)\n"
        header += f"# 컬럼: 금융투자, 보험, 투신, 사모, 은행, 기타금융, 연기금, 기관합계, 기타법인, 개인, 외국인, 기타외국인, 전체\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except ImportError:
        # Fallback: try to get basic data from FinanceDataReader
        return _get_investor_data_fallback(symbol, start_date, end_date)
    except Exception as e:
        return f"Error retrieving investor trading data for {symbol}: {str(e)}"


def _get_investor_data_fallback(symbol: str, start_date: str, end_date: str) -> str:
    """Fallback for investor data when pykrx is not available."""
    return (
        f"투자자별 매매동향 데이터를 가져올 수 없습니다 (symbol: {symbol}).\n"
        f"pykrx 패키지가 필요합니다: pip install pykrx\n"
        f"pykrx 설치 후 외국인/기관 수급 데이터를 확인할 수 있습니다."
    )


def get_krx_market_cap(
    symbol: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """Retrieve market capitalization and trading info for a KRX stock."""
    _ensure_fdr()
    symbol = _normalize_krx_symbol(symbol)

    try:
        from pykrx import stock as krx_stock

        date_str = curr_date.replace("-", "")
        # Get market cap for specific date
        df = krx_stock.get_market_cap_by_date(date_str, date_str, symbol)

        if df is None or df.empty:
            return f"No market cap data for '{symbol}' on {curr_date}"

        result = f"# KRX 시가총액 정보: {symbol} ({curr_date})\n\n"
        for _, row in df.iterrows():
            result += f"시가총액: {row.get('시가총액', 'N/A'):,} 원\n"
            result += f"거래량: {row.get('거래량', 'N/A'):,} 주\n"
            result += f"거래대금: {row.get('거래대금', 'N/A'):,} 원\n"
            result += f"상장주식수: {row.get('상장주식수', 'N/A'):,} 주\n"

        return result

    except ImportError:
        return f"시가총액 데이터를 가져오려면 pykrx 패키지가 필요합니다: pip install pykrx"
    except Exception as e:
        return f"Error retrieving market cap for {symbol}: {str(e)}"


def get_krx_fundamentals(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    curr_date: Annotated[str, "current date in yyyy-mm-dd format"] = None,
) -> str:
    """Get fundamental data for a KRX-listed company.

    Combines FinanceDataReader stock info with pykrx fundamental ratios.
    """
    _ensure_fdr()
    ticker = _normalize_krx_symbol(ticker)

    result_lines = []
    result_lines.append(f"# KRX 기업 기본정보: {ticker}\n")

    # Try to get basic info from FinanceDataReader
    try:
        listing = fdr.StockListing("KRX")
        if listing is not None and not listing.empty:
            # Search for the ticker
            match = listing[listing["Code"] == ticker]
            if match.empty:
                match = listing[listing["Symbol"] == ticker]

            if not match.empty:
                row = match.iloc[0]
                name = row.get("Name", row.get("ISU_ABBRV", "N/A"))
                market = row.get("Market", "N/A")
                sector = row.get("Sector", row.get("업종명", "N/A"))
                industry = row.get("Industry", "N/A")

                result_lines.append(f"종목명: {name}")
                result_lines.append(f"시장: {market}")
                result_lines.append(f"업종: {sector}")
                if industry != "N/A":
                    result_lines.append(f"산업: {industry}")
    except Exception:
        pass

    # Try to get fundamental ratios from pykrx
    try:
        from pykrx import stock as krx_stock

        if curr_date:
            date_str = curr_date.replace("-", "")
        else:
            date_str = datetime.now().strftime("%Y%m%d")

        # Get PER, PBR, DIV from pykrx
        fund_df = krx_stock.get_market_fundamental_by_date(date_str, date_str, ticker)
        if fund_df is not None and not fund_df.empty:
            row = fund_df.iloc[0]
            result_lines.append(f"\n## 투자지표 ({curr_date or 'latest'})")
            if "BPS" in fund_df.columns:
                result_lines.append(f"BPS (주당순자산): {row['BPS']:,.0f} 원")
            if "PER" in fund_df.columns:
                result_lines.append(f"PER (주가수익비율): {row['PER']:.2f}")
            if "PBR" in fund_df.columns:
                result_lines.append(f"PBR (주가순자산비율): {row['PBR']:.2f}")
            if "EPS" in fund_df.columns:
                result_lines.append(f"EPS (주당순이익): {row['EPS']:,.0f} 원")
            if "DIV" in fund_df.columns:
                result_lines.append(f"배당수익률: {row['DIV']:.2f}%")
            if "DPS" in fund_df.columns:
                result_lines.append(f"DPS (주당배당금): {row['DPS']:,.0f} 원")

        # Get market cap
        cap_df = krx_stock.get_market_cap_by_date(date_str, date_str, ticker)
        if cap_df is not None and not cap_df.empty:
            cap_row = cap_df.iloc[0]
            result_lines.append(f"\n## 시가총액 정보")
            if "시가총액" in cap_df.columns:
                market_cap = cap_row["시가총액"]
                # Format in 억 원
                result_lines.append(f"시가총액: {market_cap:,.0f} 원 ({market_cap / 100_000_000:,.0f} 억원)")
            if "상장주식수" in cap_df.columns:
                result_lines.append(f"상장주식수: {cap_row['상장주식수']:,.0f} 주")

    except ImportError:
        result_lines.append("\n(pykrx 패키지 미설치 - 투자지표 데이터 제한)")
    except Exception as e:
        result_lines.append(f"\n투자지표 조회 오류: {str(e)}")

    if len(result_lines) <= 1:
        return f"No fundamental data found for KRX symbol '{ticker}'"

    result_lines.append(f"\n# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(result_lines)
