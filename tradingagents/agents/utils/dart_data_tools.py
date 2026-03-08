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

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_dart_financials(
    ticker: Annotated[str, "Korean stock ticker (6-digit code, e.g. '005930')"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve Korean DART financial statements including revenue, operating profit,
    and net income. Use this for Korean-listed companies to get official financial
    data from the DART (Data Analysis, Retrieval and Transfer) system.
    Args:
        ticker (str): Korean stock ticker (6-digit code)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing DART financial statement data
    """
    return route_to_vendor("get_dart_financials", ticker, curr_date)


@tool
def get_dart_disclosures(
    ticker: Annotated[str, "Korean stock ticker (6-digit code, e.g. '005930')"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve recent Korean DART disclosures and regulatory filings for the company.
    Use this for Korean-listed companies to get official disclosure data including
    earnings reports, major corporate actions, and regulatory filings.
    Args:
        ticker (str): Korean stock ticker (6-digit code)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing recent DART disclosures
    """
    return route_to_vendor("get_dart_disclosures", ticker, curr_date)
