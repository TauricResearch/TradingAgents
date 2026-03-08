# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""OpenDART data provider — Korean DART disclosure and financial data."""

import os
from datetime import date, timedelta


def _get_dart():
    """Get OpenDartReader instance (lazy import)."""
    try:
        import OpenDartReader
    except ImportError:
        raise ImportError("opendartreader package required: pip install opendartreader")

    api_key = os.environ.get("OPENDART_API_KEY", "")
    if not api_key:
        raise ValueError("OPENDART_API_KEY environment variable is not set.")

    return OpenDartReader(api_key)


def _parse_amount(df_rows) -> float | None:
    """Parse DART monetary amount string to float."""
    if df_rows is None or df_rows.empty:
        return None
    try:
        val = df_rows.iloc[0].get("thstrm_amount", "")
        if isinstance(val, str):
            val = val.replace(",", "").replace(" ", "")
        return float(val) if val else None
    except (ValueError, TypeError, IndexError):
        return None


def get_dart_financials(ticker: str, curr_date: str) -> str:
    """Retrieve DART financial statements (revenue, operating profit, net income).

    Args:
        ticker: Korean stock ticker (6-digit code, e.g. '005930')
        curr_date: Current date in yyyy-mm-dd format

    Returns:
        Formatted string report of financial statements.
    """
    try:
        dart = _get_dart()
        year = int(curr_date[:4])

        quarter_names = {
            "11013": "Q1",
            "11012": "H1 (반기)",
            "11014": "Q3",
            "11011": "Annual",
        }

        lines = [f"=== DART Financial Statements for {ticker} ===\n"]

        for check_year in [year - 1, year]:
            for reprt_code, q_name in quarter_names.items():
                try:
                    df = dart.finstate(ticker, check_year, reprt_code=reprt_code)
                    if df is None or df.empty:
                        continue

                    revenue_row = df[df["account_nm"].str.contains("매출액|영업수익", na=False)]
                    op_row = df[df["account_nm"].str.contains("영업이익", na=False)]
                    ni_row = df[df["account_nm"].str.contains("당기순이익", na=False)]

                    revenue = _parse_amount(revenue_row)
                    op = _parse_amount(op_row)
                    ni = _parse_amount(ni_row)
                    opm = round(op / revenue * 100, 2) if revenue and op else None

                    lines.append(f"[{check_year} {q_name}]")
                    lines.append(f"  Revenue:          {revenue:,.0f}" if revenue else "  Revenue:          N/A")
                    lines.append(f"  Operating Profit: {op:,.0f}" if op else "  Operating Profit: N/A")
                    lines.append(f"  Net Income:       {ni:,.0f}" if ni else "  Net Income:       N/A")
                    if opm is not None:
                        lines.append(f"  OPM:              {opm}%")
                    lines.append("")
                except Exception:
                    continue

        if len(lines) == 1:
            return f"No DART financial data found for {ticker}."

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching DART financials for {ticker}: {e}"


def get_dart_disclosures(ticker: str, curr_date: str) -> str:
    """Retrieve recent DART disclosures/filings list.

    Args:
        ticker: Korean stock ticker (6-digit code, e.g. '005930')
        curr_date: Current date in yyyy-mm-dd format

    Returns:
        Formatted string report of recent disclosures.
    """
    try:
        dart = _get_dart()
        end = date.fromisoformat(curr_date)
        start = end - timedelta(days=30)

        df = dart.list(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            kind="",
        )

        if df is None or df.empty:
            return f"No DART disclosures found for {ticker} in the last 30 days."

        lines = [f"=== DART Disclosures for {ticker} (last 30 days) ===\n"]

        for _, row in df.iterrows():
            rcept_dt = str(row.get("rcept_dt", ""))
            title = str(row.get("report_nm", ""))
            pblntf_ty = str(row.get("pblntf_ty", ""))
            rcept_no = str(row.get("rcept_no", ""))
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

            lines.append(f"[{rcept_dt}] {title}")
            lines.append(f"  Type: {pblntf_ty} | URL: {url}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching DART disclosures for {ticker}: {e}"
