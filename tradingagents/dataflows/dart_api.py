"""DART (Korean Electronic Disclosure System) API integration.

Provides access to Korean company financial statements, disclosures,
and fundamental data from the DART OpenAPI (https://opendart.fss.or.kr).

Requires DART_API_KEY environment variable to be set.
"""

import os
import requests
from datetime import datetime
from typing import Annotated, Optional


DART_BASE_URL = "https://opendart.fss.or.kr/api"


def _get_dart_api_key() -> str:
    """Get DART API key from environment."""
    key = os.environ.get("DART_API_KEY", "")
    if not key:
        raise ValueError(
            "DART_API_KEY 환경변수가 설정되지 않았습니다. "
            "https://opendart.fss.or.kr 에서 API 키를 발급받으세요."
        )
    return key


def _dart_request(endpoint: str, params: dict) -> dict:
    """Make a DART API request."""
    api_key = _get_dart_api_key()
    params["crtfc_key"] = api_key

    url = f"{DART_BASE_URL}/{endpoint}.json"
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()
    if data.get("status") != "000":
        msg = data.get("message", "Unknown error")
        raise ValueError(f"DART API error: {msg} (status: {data.get('status')})")

    return data


def _get_corp_code(ticker: str) -> str:
    """Get DART corporation code from stock code.

    DART uses its own corp_code which differs from stock ticker.
    This function maintains a cache for lookups.
    """
    import zipfile
    import io
    import xml.etree.ElementTree as ET
    from tradingagents.dataflows.config import get_config

    config = get_config()
    cache_dir = config.get("data_cache_dir", "./data_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "dart_corp_codes.xml")

    # Download corp code list if not cached
    if not os.path.exists(cache_file):
        api_key = _get_dart_api_key()
        url = f"{DART_BASE_URL}/corpCode.xml"
        response = requests.get(url, params={"crtfc_key": api_key}, timeout=30)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            xml_filename = zf.namelist()[0]
            with zf.open(xml_filename) as f:
                with open(cache_file, "wb") as out:
                    out.write(f.read())

    # Parse XML and find corp_code
    tree = ET.parse(cache_file)
    root = tree.getroot()

    ticker = ticker.strip().lstrip("0")  # Handle leading zeros
    ticker_padded = ticker.zfill(6)

    for corp in root.findall("list"):
        stock_code = corp.findtext("stock_code", "").strip()
        if stock_code == ticker_padded:
            return corp.findtext("corp_code", "").strip()

    raise ValueError(f"DART corp_code not found for ticker: {ticker_padded}")


def get_dart_financial_statements(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    year: Annotated[str, "Business year (e.g., '2024')"],
    report_code: Annotated[str, "Report code: '11013'=1Q, '11012'=반기, '11014'=3Q, '11011'=연간"] = "11011",
) -> str:
    """Retrieve financial statements from DART for a Korean company.

    Args:
        ticker: KRX stock code
        year: Business year
        report_code: '11013' (1Q), '11012' (반기), '11014' (3Q), '11011' (연간)
    """
    try:
        corp_code = _get_corp_code(ticker)
    except ValueError as e:
        return str(e)

    report_names = {
        "11013": "1분기보고서",
        "11012": "반기보고서",
        "11014": "3분기보고서",
        "11011": "사업보고서(연간)",
    }
    report_name = report_names.get(report_code, report_code)

    try:
        # Fetch single-company financial statements
        params = {
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": report_code,
            "fs_div": "CFS",  # Consolidated (연결재무제표)
        }

        data = _dart_request("fnlttSinglAcntAll", params)
        items = data.get("list", [])

        if not items:
            return f"No DART financial data for {ticker} ({year} {report_name})"

        # Organize by statement type
        statements = {}
        for item in items:
            sj_nm = item.get("sj_nm", "기타")  # Statement name
            if sj_nm not in statements:
                statements[sj_nm] = []
            statements[sj_nm].append(item)

        result = f"# DART 재무제표: {ticker} ({year} {report_name})\n"
        result += f"# 연결재무제표 (Consolidated)\n\n"

        for sj_name, items_list in statements.items():
            result += f"## {sj_name}\n"
            result += f"{'계정명':<30} | {'당기금액':>20} | {'전기금액':>20}\n"
            result += "-" * 75 + "\n"

            for item in items_list:
                account = item.get("account_nm", "")
                current = item.get("thstrm_amount", "")
                previous = item.get("frmtrm_amount", "")

                # Format amounts
                if current and current != "":
                    try:
                        current = f"{int(current.replace(',', '')):>20,}"
                    except (ValueError, AttributeError):
                        current = f"{current:>20}"

                if previous and previous != "":
                    try:
                        previous = f"{int(previous.replace(',', '')):>20,}"
                    except (ValueError, AttributeError):
                        previous = f"{previous:>20}"

                result += f"{account:<30} | {current:>20} | {previous:>20}\n"

            result += "\n"

        result += f"# 단위: 원 (KRW)\n"
        result += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        return result

    except ValueError as e:
        return f"DART API error for {ticker}: {str(e)}"
    except Exception as e:
        return f"Error fetching DART financial data for {ticker}: {str(e)}"


def get_dart_disclosures(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    disclosure_type: Annotated[str, "Type: 'A'=정기, 'B'=주요사항, 'C'=발행공시, 'D'=지분공시, 'E'=기타, 'F'=외부감사, 'G'=펀드, 'H'=자산유동화, 'I'=거래소공시, 'J'=공정위, ''=전체"] = "",
) -> str:
    """Retrieve recent disclosures/filings from DART for a Korean company.

    This is crucial for Korean market analysis as DART disclosures
    (공시) are the primary source of corporate events and regulatory filings.
    """
    try:
        corp_code = _get_corp_code(ticker)
    except ValueError as e:
        return str(e)

    try:
        params = {
            "corp_code": corp_code,
            "bgn_de": start_date.replace("-", ""),
            "end_de": end_date.replace("-", ""),
            "page_count": 20,
        }
        if disclosure_type:
            params["pblntf_ty"] = disclosure_type

        data = _dart_request("list", params)
        items = data.get("list", [])

        if not items:
            return f"No DART disclosures for {ticker} between {start_date} and {end_date}"

        result = f"# DART 공시목록: {ticker} ({start_date} ~ {end_date})\n\n"

        for item in items:
            report_nm = item.get("report_nm", "")
            rcept_dt = item.get("rcept_dt", "")
            flr_nm = item.get("flr_nm", "")  # Filing entity
            rcept_no = item.get("rcept_no", "")

            # Format date
            if len(rcept_dt) == 8:
                rcept_dt = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"

            result += f"### {report_nm}\n"
            result += f"접수일: {rcept_dt} | 제출인: {flr_nm}\n"
            result += f"DART 링크: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}\n\n"

        result += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        return result

    except ValueError as e:
        return f"DART API error for {ticker}: {str(e)}"
    except Exception as e:
        return f"Error fetching DART disclosures for {ticker}: {str(e)}"


def get_dart_major_shareholders(
    ticker: Annotated[str, "KRX ticker symbol (e.g., '005930')"],
) -> str:
    """Retrieve major shareholder information from DART.

    Shows the largest shareholders and their ownership percentages,
    which is important for Korean market analysis (대주주 지분 현황).
    """
    try:
        corp_code = _get_corp_code(ticker)
    except ValueError as e:
        return str(e)

    try:
        # Get the latest annual report year
        current_year = datetime.now().year
        data = None

        # Try current year first, then previous year
        for year in [str(current_year), str(current_year - 1)]:
            try:
                params = {
                    "corp_code": corp_code,
                    "bsns_year": year,
                    "reprt_code": "11011",  # Annual report
                }
                data = _dart_request("hyslrSttus", params)
                if data.get("list"):
                    break
            except ValueError:
                continue

        if not data or not data.get("list"):
            return f"No major shareholder data found for {ticker}"

        items = data["list"]

        result = f"# DART 대주주 현황: {ticker}\n\n"
        result += f"{'주주명':<20} | {'관계':<15} | {'보유주식수':>15} | {'지분율':>10}\n"
        result += "-" * 65 + "\n"

        for item in items:
            nm = item.get("nm", "")
            relate = item.get("relate", "")
            stock_cnt = item.get("trmend_posesn_stock_co", "")
            ratio = item.get("trmend_posesn_stock_qota_rt", "")

            if stock_cnt:
                try:
                    stock_cnt = f"{int(stock_cnt.replace(',', '')):>15,}"
                except (ValueError, AttributeError):
                    stock_cnt = f"{stock_cnt:>15}"

            result += f"{nm:<20} | {relate:<15} | {stock_cnt:>15} | {ratio:>10}%\n"

        result += f"\n# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        return result

    except ValueError as e:
        return f"DART API error for {ticker}: {str(e)}"
    except Exception as e:
        return f"Error fetching shareholder data for {ticker}: {str(e)}"
