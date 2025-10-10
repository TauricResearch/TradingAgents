#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# yfinance - market data downloader
# https://github.com/ranaroussi/yfinance
#
# Copyright 2017-2019 Ran Aroussi
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
#

from __future__ import print_function

import json as _json
import warnings
from typing import Optional, Union
from urllib.parse import quote as urlencode

import numpy as np
import pandas as pd
from curl_cffi import requests


from . import utils, cache
from .const import _MIC_TO_YAHOO_SUFFIX
from .data import YfData
from .exceptions import YFEarningsDateMissing, YFRateLimitError
from .live import WebSocket
from .scrapers.analysis import Analysis
from .scrapers.fundamentals import Fundamentals
from .scrapers.holders import Holders
from .scrapers.quote import Quote, FastInfo
from .scrapers.history import PriceHistory
from .scrapers.funds import FundsData

from .const import _BASE_URL_, _ROOT_URL_, _QUERY1_URL_, _SENTINEL_

from io import StringIO
from bs4 import BeautifulSoup


_tz_info_fetch_ctr = 0

class TickerBase:
    def __init__(self, ticker, session=None, proxy=_SENTINEL_):
        """
        Initialize a Yahoo Finance Ticker object.

        Args:
            ticker (str | tuple[str, str]):
                Yahoo Finance symbol (e.g. "AAPL")
                or a tuple of (symbol, MIC) e.g. ('OR','XPAR')
                (MIC = market identifier code)

            session (requests.Session, optional):
                Custom requests session.
        """        
        if isinstance(ticker, tuple):
            if len(ticker) != 2:
                raise ValueError("Ticker tuple must be (symbol, mic_code)")
            base_symbol, mic_code = ticker
            # ticker = yahoo_ticker(base_symbol, mic_code)
            if mic_code.startswith('.'):
                mic_code = mic_code[1:]
            if mic_code.upper() not in _MIC_TO_YAHOO_SUFFIX:
                raise ValueError(f"Unknown MIC code: '{mic_code}'")
            sfx = _MIC_TO_YAHOO_SUFFIX[mic_code.upper()]
            if sfx != '':
                ticker = f'{base_symbol}.{sfx}'
            else:
                ticker = base_symbol

        self.ticker = ticker.upper()
        self.session = session or requests.Session(impersonate="chrome")
        self._tz = None

        self._isin = None
        self._news = []
        self._shares = None

        self._earnings_dates = {}

        self._earnings = None
        self._financials = None

        # raise an error if user tries to give empty ticker
        if self.ticker == "":
            raise ValueError("Empty ticker name")

        self._data: YfData = YfData(session=session)
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        # accept isin as ticker
        if utils.is_isin(self.ticker):
            isin = self.ticker
            c = cache.get_isin_cache()
            self.ticker = c.lookup(isin)
            if not self.ticker:
                self.ticker = utils.get_ticker_by_isin(isin)
            if self.ticker == "":
                raise ValueError(f"Invalid ISIN number: {isin}")
            if self.ticker:
                c.store(isin, self.ticker)

        # self._price_history = PriceHistory(self._data, self.ticker)
        self._price_history = None  # lazy-load
        self._analysis = Analysis(self._data, self.ticker)
        self._holders = Holders(self._data, self.ticker)
        self._quote = Quote(self._data, self.ticker)
        self._fundamentals = Fundamentals(self._data, self.ticker)
        self._funds_data = None

        self._fast_info = None

        self._message_handler = None
        self.ws = None

    @utils.log_indent_decorator
    def history(self, *args, **kwargs) -> pd.DataFrame:
        return self._lazy_load_price_history().history(*args, **kwargs)

    # ------------------------

    def _lazy_load_price_history(self):
        if self._price_history is None:
            self._price_history = PriceHistory(self._data, self.ticker, self._get_ticker_tz(timeout=10))
        return self._price_history

    def _get_ticker_tz(self, timeout):
        if self._tz is not None:
            return self._tz
        c = cache.get_tz_cache()
        tz = c.lookup(self.ticker)

        if tz and not utils.is_valid_timezone(tz):
            # Clear from cache and force re-fetch
            c.store(self.ticker, None)
            tz = None

        if tz is None:
            tz = self._fetch_ticker_tz(timeout)
            if tz is None:
                # _fetch_ticker_tz works in 99.999% of cases.
                # For rare fail get from info.
                global _tz_info_fetch_ctr
                if _tz_info_fetch_ctr < 2:
                    # ... but limit. If _fetch_ticker_tz() always
                    # failing then bigger problem.
                    _tz_info_fetch_ctr += 1
                    for k in ['exchangeTimezoneName', 'timeZoneFullName']:
                        if k in self.info:
                            tz = self.info[k]
                            break
            if utils.is_valid_timezone(tz):
                c.store(self.ticker, tz)
            else:
                tz = None

        self._tz = tz
        return tz

    @utils.log_indent_decorator
    def _fetch_ticker_tz(self, timeout):
        # Query Yahoo for fast price data just to get returned timezone
        logger = utils.get_yf_logger()

        params = {"range": "1d", "interval": "1d"}

        # Getting data from json
        url = f"{_BASE_URL_}/v8/finance/chart/{self.ticker}"

        try:
            data = self._data.cache_get(url=url, params=params, timeout=timeout)
            data = data.json()
        except YFRateLimitError:
            # Must propagate this
            raise
        except Exception as e:
            logger.error(f"Failed to get ticker '{self.ticker}' reason: {e}")
            return None
        else:
            error = data.get('chart', {}).get('error', None)
            if error:
                # explicit error from yahoo API
                logger.debug(f"Got error from yahoo api for ticker {self.ticker}, Error: {error}")
            else:
                try:
                    return data["chart"]["result"][0]["meta"]["exchangeTimezoneName"]
                except Exception as err:
                    logger.error(f"Could not get exchangeTimezoneName for ticker '{self.ticker}' reason: {err}")
                    logger.debug("Got response: ")
                    logger.debug("-------------")
                    logger.debug(f" {data}")
                    logger.debug("-------------")
        return None

    def get_recommendations(self, proxy=_SENTINEL_, as_dict=False):
        """
        Returns a DataFrame with the recommendations
        Columns: period  strongBuy  buy  hold  sell  strongSell
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._quote.recommendations
        if as_dict:
            return data.to_dict()
        return data

    def get_recommendations_summary(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self.get_recommendations(as_dict=as_dict)

    def get_upgrades_downgrades(self, proxy=_SENTINEL_, as_dict=False):
        """
        Returns a DataFrame with the recommendations changes (upgrades/downgrades)
        Index: date of grade
        Columns: firm toGrade fromGrade action
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._quote.upgrades_downgrades
        if as_dict:
            return data.to_dict()
        return data

    def get_calendar(self, proxy=_SENTINEL_) -> dict:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self._quote.calendar

    def get_sec_filings(self, proxy=_SENTINEL_) -> dict:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self._quote.sec_filings

    def get_major_holders(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._holders.major
        if as_dict:
            return data.to_dict()
        return data

    def get_institutional_holders(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._holders.institutional
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_mutualfund_holders(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._holders.mutualfund
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_insider_purchases(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._holders.insider_purchases
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_insider_transactions(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._holders.insider_transactions
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_insider_roster_holders(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._holders.insider_roster
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_info(self, proxy=_SENTINEL_) -> dict:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._quote.info
        return data

    def get_fast_info(self, proxy=_SENTINEL_):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        if self._fast_info is None:
            self._fast_info = FastInfo(self)
        return self._fast_info

    def get_sustainability(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._quote.sustainability
        if as_dict:
            return data.to_dict()
        return data

    def get_analyst_price_targets(self, proxy=_SENTINEL_) -> dict:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        """
        Keys:   current  low  high  mean  median
        """
        data = self._analysis.analyst_price_targets
        return data

    def get_earnings_estimate(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        """
        Index:      0q  +1q  0y  +1y
        Columns:    numberOfAnalysts  avg  low  high  yearAgoEps  growth
        """
        data = self._analysis.earnings_estimate
        return data.to_dict() if as_dict else data

    def get_revenue_estimate(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        """
        Index:      0q  +1q  0y  +1y
        Columns:    numberOfAnalysts  avg  low  high  yearAgoRevenue  growth
        """
        data = self._analysis.revenue_estimate
        return data.to_dict() if as_dict else data

    def get_earnings_history(self, proxy=_SENTINEL_, as_dict=False):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        """
        Index:      pd.DatetimeIndex
        Columns:    epsEstimate  epsActual  epsDifference  surprisePercent
        """
        data = self._analysis.earnings_history
        return data.to_dict() if as_dict else data

    def get_eps_trend(self, proxy=_SENTINEL_, as_dict=False):
        """
        Index:      0q  +1q  0y  +1y
        Columns:    current  7daysAgo  30daysAgo  60daysAgo  90daysAgo
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._analysis.eps_trend
        return data.to_dict() if as_dict else data

    def get_eps_revisions(self, proxy=_SENTINEL_, as_dict=False):
        """
        Index:      0q  +1q  0y  +1y
        Columns:    upLast7days  upLast30days  downLast7days  downLast30days
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._analysis.eps_revisions
        return data.to_dict() if as_dict else data

    def get_growth_estimates(self, proxy=_SENTINEL_, as_dict=False):
        """
        Index:      0q  +1q  0y  +1y +5y -5y
        Columns:    stock  industry  sector  index
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._analysis.growth_estimates
        return data.to_dict() if as_dict else data

    def get_earnings(self, proxy=_SENTINEL_, as_dict=False, freq="yearly"):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            freq: str
                "yearly" or "quarterly" or "trailing"
                Default is "yearly"
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        if self._fundamentals.earnings is None:
            return None
        data = self._fundamentals.earnings[freq]
        if as_dict:
            dict_data = data.to_dict()
            dict_data['financialCurrency'] = 'USD' if 'financialCurrency' not in self._earnings else self._earnings[
                'financialCurrency']
            return dict_data
        return data

    def get_income_stmt(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly"):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly" or "trailing"
                Default is "yearly"
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._fundamentals.financials.get_income_time_series(freq=freq)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["EBIT", "EBITDA", "EPS", "NI"])
        if as_dict:
            return data.to_dict()
        return data

    def get_incomestmt(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly"):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self.get_income_stmt(proxy, as_dict, pretty, freq)

    def get_financials(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly"):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self.get_income_stmt(proxy, as_dict, pretty, freq)

    def get_balance_sheet(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly"):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)


        data = self._fundamentals.financials.get_balance_sheet_time_series(freq=freq)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["PPE"])
        if as_dict:
            return data.to_dict()
        return data

    def get_balancesheet(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly"):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self.get_balance_sheet(proxy, as_dict, pretty, freq)

    def get_cash_flow(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly") -> Union[pd.DataFrame, dict]:
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)


        data = self._fundamentals.financials.get_cash_flow_time_series(freq=freq)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["PPE"])
        if as_dict:
            return data.to_dict()
        return data

    def get_cashflow(self, proxy=_SENTINEL_, as_dict=False, pretty=False, freq="yearly"):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        return self.get_cash_flow(proxy, as_dict, pretty, freq)

    def get_dividends(self, proxy=_SENTINEL_, period="max") -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        return self._lazy_load_price_history().get_dividends(period=period)

    def get_capital_gains(self, proxy=_SENTINEL_, period="max") -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        return self._lazy_load_price_history().get_capital_gains(period=period)

    def get_splits(self, proxy=_SENTINEL_, period="max") -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        return self._lazy_load_price_history().get_splits(period=period)

    def get_actions(self, proxy=_SENTINEL_, period="max") -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        return self._lazy_load_price_history().get_actions(period=period)

    def get_shares(self, proxy=_SENTINEL_, as_dict=False) -> Union[pd.DataFrame, dict]:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        data = self._fundamentals.shares
        if as_dict:
            return data.to_dict()
        return data

    @utils.log_indent_decorator
    def get_shares_full(self, start=None, end=None, proxy=_SENTINEL_):
        logger = utils.get_yf_logger()

        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        # Process dates
        tz = self._get_ticker_tz(timeout=10)
        dt_now = pd.Timestamp.utcnow().tz_convert(tz)
        if start is not None:
            start = utils._parse_user_dt(start, tz)
        if end is not None:
            end = utils._parse_user_dt(end, tz)
        if end is None:
            end = dt_now
        if start is None:
            start = end - pd.Timedelta(days=548)  # 18 months
        if start >= end:
            logger.error("Start date must be before end")
            return None
        start = start.floor("D")
        end = end.ceil("D")

        # Fetch
        ts_url_base = f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{self.ticker}?symbol={self.ticker}"
        shares_url = f"{ts_url_base}&period1={int(start.timestamp())}&period2={int(end.timestamp())}"
        try:
            json_data = self._data.cache_get(url=shares_url)
            json_data = json_data.json()
        except (_json.JSONDecodeError, requests.exceptions.RequestException):
            logger.error(f"{self.ticker}: Yahoo web request for share count failed")
            return None
        try:
            fail = json_data["finance"]["error"]["code"] == "Bad Request"
        except KeyError:
            fail = False
        if fail:
            logger.error(f"{self.ticker}: Yahoo web request for share count failed")
            return None

        shares_data = json_data["timeseries"]["result"]
        if "shares_out" not in shares_data[0]:
            return None
        try:
            df = pd.Series(shares_data[0]["shares_out"], index=pd.to_datetime(shares_data[0]["timestamp"], unit="s"))
        except Exception as e:
            logger.error(f"{self.ticker}: Failed to parse shares count data: {e}")
            return None

        df.index = df.index.tz_localize(tz)
        df = df.sort_index()
        return df

    def get_isin(self, proxy=_SENTINEL_) -> Optional[str]:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        # *** experimental ***
        if self._isin is not None:
            return self._isin

        ticker = self.ticker.upper()

        if "-" in ticker or "^" in ticker:
            self._isin = '-'
            return self._isin

        q = ticker

        if self._quote.info is None:
            # Don't print error message cause self._quote.info will print one
            return None
        if "shortName" in self._quote.info:
            q = self._quote.info['shortName']

        url = f'https://markets.businessinsider.com/ajax/SearchController_Suggest?max_results=25&query={urlencode(q)}'
        data = self._data.cache_get(url=url).text

        search_str = f'"{ticker}|'
        if search_str not in data:
            if q.lower() in data.lower():
                search_str = '"|'
                if search_str not in data:
                    self._isin = '-'
                    return self._isin
            else:
                self._isin = '-'
                return self._isin

        self._isin = data.split(search_str)[1].split('"')[0].split('|')[0]
        return self._isin

    def get_news(self, count=10, tab="news", proxy=_SENTINEL_) -> list:
        """Allowed options for tab: "news", "all", "press releases"""
        if self._news:
            return self._news

        logger = utils.get_yf_logger()

        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        tab_queryrefs = {
            "all": "newsAll",
            "news": "latestNews",
            "press releases": "pressRelease",
        }

        query_ref = tab_queryrefs.get(tab.lower())
        if not query_ref:
            raise ValueError(f"Invalid tab name '{tab}'. Choose from: {', '.join(tab_queryrefs.keys())}")

        url = f"{_ROOT_URL_}/xhr/ncp?queryRef={query_ref}&serviceKey=ncp_fin"
        payload = {
            "serviceConfig": {
                "snippetCount": count,
                "s": [self.ticker]
            }
        }

        data = self._data.post(url, body=payload)
        if data is None or "Will be right back" in data.text:
            raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***\n"
                               "Our engineers are working quickly to resolve "
                               "the issue. Thank you for your patience.")
        try:
            data = data.json()
        except _json.JSONDecodeError:
            logger.error(f"{self.ticker}: Failed to retrieve the news and received faulty response instead.")
            data = {}

        news = data.get("data", {}).get("tickerStream", {}).get("stream", [])

        self._news = [article for article in news if not article.get('ad', [])]
        return self._news

    def get_earnings_dates(self, limit = 12, offset = 0) -> Optional[pd.DataFrame]:
        return self._get_earnings_dates_using_scrape(limit, offset)

    @utils.log_indent_decorator
    def _get_earnings_dates_using_scrape(self, limit = 12, offset = 0) -> Optional[pd.DataFrame]:
        """
        Uses YfData.cache_get() to scrape earnings data from YahooFinance.
        (https://finance.yahoo.com/calendar/earnings?symbol=INTC)
    
        Args:
            limit (int): Number of rows to extract (max=100)
            offset (int): if 0, search from future EPS estimates. 
                          if 1, search from the most recent EPS. 
                          if x, search from x'th recent EPS. 
    
        Returns:
            pd.DataFrame in the following format.
    
                       EPS Estimate Reported EPS Surprise(%)
            Date
            2025-10-30         2.97            -           -
            2025-07-22         1.73         1.54      -10.88
            2025-05-06         2.63          2.7        2.57
            2025-02-06         2.09         2.42       16.06
            2024-10-31         1.92         1.55      -19.36
            ...                 ...          ...         ...
            2014-07-31         0.61         0.65        7.38
            2014-05-01         0.55         0.68       22.92
            2014-02-13         0.55         0.58        6.36
            2013-10-31         0.51         0.54        6.86
            2013-08-01         0.46          0.5        7.86
        """
        #####################################################
        # Define Constants
        #####################################################
        if limit > 0 and limit <= 25:
            size = 25
        elif limit > 25 and limit <= 50:
            size = 50
        elif limit > 50 and limit <= 100:
            size = 100
        else:
            raise ValueError("Please use limit <= 100")
    
        # Define the URL
        url = "https://finance.yahoo.com/calendar/earnings?symbol={}&offset={}&size={}".format(
            self.ticker, offset, size
        )
        #####################################################
        # Get data
        #####################################################
        response = self._data.cache_get(url)
    
        #####################################################
        # Response -> pd.DataFrame
        #####################################################
        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        # This page should have only one <table>
        table = soup.find("table")
        # If the table is found
        if table:
            # Get the HTML string of the table
            table_html = str(table)
    
            # Wrap the HTML string in a StringIO object
            html_stringio = StringIO(table_html)
    
            # Pass the StringIO object to pd.read_html()
            df = pd.read_html(html_stringio, na_values=['-'])[0]
    
            # Drop redundant columns
            df = df.drop(["Symbol", "Company"], axis=1)

            # Backwards compatibility
            df.rename(columns={'Surprise (%)': 'Surprise(%)'}, inplace=True)

            df = df.dropna(subset="Earnings Date")

            # Parse earnings date
            # - Pandas doesn't like EDT, EST
            df['Earnings Date'] = df['Earnings Date'].str.replace('EDT', 'America/New_York')
            df['Earnings Date'] = df['Earnings Date'].str.replace('EST', 'America/New_York')
            # - separate timezone string (last word)
            dt_parts = df['Earnings Date'].str.rsplit(' ', n=1, expand=True)
            dts = dt_parts[0]
            tzs = dt_parts[1]
            df['Earnings Date'] = pd.to_datetime(dts, format='%B %d, %Y at %I %p')
            df['Earnings Date'] = pd.Series([dt.tz_localize(tz) for dt, tz in zip(df['Earnings Date'], tzs)])
            df = df.set_index("Earnings Date")

        else:
            err_msg = "No earnings dates found, symbol may be delisted"
            logger = utils.get_yf_logger()
            logger.error(f'{self.ticker}: {err_msg}')
            return None
        return df

    @utils.log_indent_decorator
    def _get_earnings_dates_using_screener(self, limit=12, proxy=_SENTINEL_) -> Optional[pd.DataFrame]:
        """
        Get earning dates (future and historic)

        In Summer 2025, Yahoo stopped updating the data at this endpoint.
        So reverting to scraping HTML.
        
        Args:
            limit (int): max amount of upcoming and recent earnings dates to return.
                Default value 12 should return next 4 quarters and last 8 quarters.
                Increase if more history is needed.
        Returns:
            pd.DataFrame
        """
        logger = utils.get_yf_logger()

        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        clamped_limit = min(limit, 100)  # YF caps at 100, don't go higher

        if self._earnings_dates and clamped_limit in self._earnings_dates:
            return self._earnings_dates[clamped_limit]

        # Fetch data
        url = f"{_QUERY1_URL_}/v1/finance/visualization"
        params = {"lang": "en-US", "region": "US"}
        body = {
            "size": clamped_limit,
            "query": { "operator": "eq", "operands": ["ticker", self.ticker] },
            "sortField": "startdatetime",
            "sortType": "DESC",
            "entityIdType": "earnings",
            "includeFields": ["startdatetime", "timeZoneShortName", "epsestimate", "epsactual", "epssurprisepct", "eventtype"]
        }
        response = self._data.post(url, params=params, body=body)
        json_data = response.json()

        # Extract data
        columns = [row['label'] for row in json_data['finance']['result'][0]['documents'][0]['columns']]
        rows = json_data['finance']['result'][0]['documents'][0]['rows']
        df = pd.DataFrame(rows, columns=columns)

        if df.empty:
            _exception = YFEarningsDateMissing(self.ticker)
            err_msg = str(_exception)
            logger.error(f'{self.ticker}: {err_msg}')
            return None

        # Convert eventtype
        # - 1 = earnings call (manually confirmed)
        # - 2 = earnings report
        # - 11 = stockholders meeting (manually confirmed)
        df['Event Type'] = df['Event Type'].replace('^1$', 'Call', regex=True)
        df['Event Type'] = df['Event Type'].replace('^2$', 'Earnings', regex=True)
        df['Event Type'] = df['Event Type'].replace('^11$', 'Meeting', regex=True)

        # Calculate earnings date
        df['Earnings Date'] = pd.to_datetime(df['Event Start Date'])
        tz = self._get_ticker_tz(timeout=30)
        if df['Earnings Date'].dt.tz is None:
            df['Earnings Date'] = df['Earnings Date'].dt.tz_localize(tz)
        else:
            df['Earnings Date'] = df['Earnings Date'].dt.tz_convert(tz)

        # Convert types
        columns_to_update = ['Surprise (%)', 'EPS Estimate', 'Reported EPS']
        df[columns_to_update] = df[columns_to_update].astype('float64').replace(0.0, np.nan)

        # Format the dataframe
        df.drop(['Event Start Date', 'Timezone short name'], axis=1, inplace=True)
        df.set_index('Earnings Date', inplace=True)
        df.rename(columns={'Surprise (%)': 'Surprise(%)'}, inplace=True)  # Compatibility

        self._earnings_dates[clamped_limit] = df
        return df

    def get_history_metadata(self, proxy=_SENTINEL_) -> dict:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        return self._lazy_load_price_history().get_history_metadata(proxy)

    def get_funds_data(self, proxy=_SENTINEL_) -> Optional[FundsData]:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        if not self._funds_data:
            self._funds_data = FundsData(self._data, self.ticker)
        
        return self._funds_data

    def live(self, message_handler=None, verbose=True):
        self._message_handler = message_handler

        self.ws = WebSocket(verbose=verbose)
        self.ws.subscribe(self.ticker)
        self.ws.listen(self._message_handler)
