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

from collections import namedtuple as _namedtuple
import warnings

import pandas as _pd

from .base import TickerBase
from .const import _BASE_URL_, _SENTINEL_
from .scrapers.funds import FundsData


class Ticker(TickerBase):
    def __init__(self, ticker, session=None, proxy=_SENTINEL_):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        super(Ticker, self).__init__(ticker, session=session)
        self._expirations = {}
        self._underlying  = {}

    def __repr__(self):
        return f'yfinance.Ticker object <{self.ticker}>'

    def _download_options(self, date=None):
        if date is None:
            url = f"{_BASE_URL_}/v7/finance/options/{self.ticker}"
        else:
            url = f"{_BASE_URL_}/v7/finance/options/{self.ticker}?date={date}"

        r = self._data.get(url=url).json()
        if len(r.get('optionChain', {}).get('result', [])) > 0:
            for exp in r['optionChain']['result'][0]['expirationDates']:
                self._expirations[_pd.Timestamp(exp, unit='s').strftime('%Y-%m-%d')] = exp

            self._underlying = r['optionChain']['result'][0].get('quote', {})

            opt = r['optionChain']['result'][0].get('options', [])

            return dict(**opt[0],underlying=self._underlying) if len(opt) > 0 else {}
        return {}

    def _options2df(self, opt, tz=None):
        data = _pd.DataFrame(opt).reindex(columns=[
            'contractSymbol',
            'lastTradeDate',
            'strike',
            'lastPrice',
            'bid',
            'ask',
            'change',
            'percentChange',
            'volume',
            'openInterest',
            'impliedVolatility',
            'inTheMoney',
            'contractSize',
            'currency'])

        data['lastTradeDate'] = _pd.to_datetime(
            data['lastTradeDate'], unit='s', utc=True)
        if tz is not None:
            data['lastTradeDate'] = data['lastTradeDate'].dt.tz_convert(tz)
        return data

    def option_chain(self, date=None, tz=None):
        if date is None:
            options = self._download_options()
        else:
            if not self._expirations:
                self._download_options()
            if date not in self._expirations:
                raise ValueError(
                    f"Expiration `{date}` cannot be found. "
                    f"Available expirations are: [{', '.join(self._expirations)}]")
            date = self._expirations[date]
            options = self._download_options(date)

        if not options:
            return _namedtuple('Options', ['calls', 'puts', 'underlying'])(**{
                "calls": None, "puts": None, "underlying": None
            })

        return _namedtuple('Options', ['calls', 'puts', 'underlying'])(**{
            "calls": self._options2df(options['calls'], tz=tz),
            "puts": self._options2df(options['puts'], tz=tz),
            "underlying": options['underlying']
        })

    # ------------------------

    @property
    def isin(self):
        return self.get_isin()

    @property
    def major_holders(self) -> _pd.DataFrame:
        return self.get_major_holders()

    @property
    def institutional_holders(self) -> _pd.DataFrame:
        return self.get_institutional_holders()

    @property
    def mutualfund_holders(self) -> _pd.DataFrame:
        return self.get_mutualfund_holders()

    @property
    def insider_purchases(self) -> _pd.DataFrame:
        return self.get_insider_purchases()

    @property
    def insider_transactions(self) -> _pd.DataFrame:
        return self.get_insider_transactions()

    @property
    def insider_roster_holders(self) -> _pd.DataFrame:
        return self.get_insider_roster_holders()

    @property
    def dividends(self) -> _pd.Series:
        return self.get_dividends()

    @property
    def capital_gains(self) -> _pd.Series:
        return self.get_capital_gains()

    @property
    def splits(self) -> _pd.Series:
        return self.get_splits()

    @property
    def actions(self) -> _pd.DataFrame:
        return self.get_actions()

    @property
    def shares(self) -> _pd.DataFrame:
        return self.get_shares()

    @property
    def info(self) -> dict:
        return self.get_info()

    @property
    def fast_info(self):
        return self.get_fast_info()

    @property
    def calendar(self) -> dict:
        """
        Returns a dictionary of events, earnings, and dividends for the ticker
        """
        return self.get_calendar()

    @property
    def sec_filings(self) -> dict:
        return self.get_sec_filings()

    @property
    def recommendations(self):
        return self.get_recommendations()

    @property
    def recommendations_summary(self):
        return self.get_recommendations_summary()

    @property
    def upgrades_downgrades(self):
        return self.get_upgrades_downgrades()

    @property
    def earnings(self) -> _pd.DataFrame:
        return self.get_earnings()

    @property
    def quarterly_earnings(self) -> _pd.DataFrame:
        return self.get_earnings(freq='quarterly')

    @property
    def income_stmt(self) -> _pd.DataFrame:
        return self.get_income_stmt(pretty=True)

    @property
    def quarterly_income_stmt(self) -> _pd.DataFrame:
        return self.get_income_stmt(pretty=True, freq='quarterly')

    @property
    def ttm_income_stmt(self) -> _pd.DataFrame:
        return self.get_income_stmt(pretty=True, freq='trailing')

    @property
    def incomestmt(self) -> _pd.DataFrame:
        return self.income_stmt

    @property
    def quarterly_incomestmt(self) -> _pd.DataFrame:
        return self.quarterly_income_stmt

    @property
    def ttm_incomestmt(self) -> _pd.DataFrame:
        return self.ttm_income_stmt

    @property
    def financials(self) -> _pd.DataFrame:
        return self.income_stmt

    @property
    def quarterly_financials(self) -> _pd.DataFrame:
        return self.quarterly_income_stmt

    @property
    def ttm_financials(self) -> _pd.DataFrame:
        return self.ttm_income_stmt

    @property
    def balance_sheet(self) -> _pd.DataFrame:
        return self.get_balance_sheet(pretty=True)

    @property
    def quarterly_balance_sheet(self) -> _pd.DataFrame:
        return self.get_balance_sheet(pretty=True, freq='quarterly')

    @property
    def balancesheet(self) -> _pd.DataFrame:
        return self.balance_sheet

    @property
    def quarterly_balancesheet(self) -> _pd.DataFrame:
        return self.quarterly_balance_sheet

    @property
    def cash_flow(self) -> _pd.DataFrame:
        return self.get_cash_flow(pretty=True, freq="yearly")

    @property
    def quarterly_cash_flow(self) -> _pd.DataFrame:
        return self.get_cash_flow(pretty=True, freq='quarterly')

    @property
    def ttm_cash_flow(self) -> _pd.DataFrame:
        return self.get_cash_flow(pretty=True, freq='trailing')

    @property
    def cashflow(self) -> _pd.DataFrame:
        return self.cash_flow

    @property
    def quarterly_cashflow(self) -> _pd.DataFrame:
        return self.quarterly_cash_flow

    @property
    def ttm_cashflow(self) -> _pd.DataFrame:
        return self.ttm_cash_flow

    @property
    def analyst_price_targets(self) -> dict:
        return self.get_analyst_price_targets()

    @property
    def earnings_estimate(self) -> _pd.DataFrame:
        return self.get_earnings_estimate()

    @property
    def revenue_estimate(self) -> _pd.DataFrame:
        return self.get_revenue_estimate()

    @property
    def earnings_history(self) -> _pd.DataFrame:
        return self.get_earnings_history()

    @property
    def eps_trend(self) -> _pd.DataFrame:
        return self.get_eps_trend()

    @property
    def eps_revisions(self) -> _pd.DataFrame:
        return self.get_eps_revisions()

    @property
    def growth_estimates(self) -> _pd.DataFrame:
        return self.get_growth_estimates()

    @property
    def sustainability(self) -> _pd.DataFrame:
        return self.get_sustainability()

    @property
    def options(self) -> tuple:
        if not self._expirations:
            self._download_options()
        return tuple(self._expirations.keys())

    @property
    def news(self) -> list:
        return self.get_news()

    @property
    def earnings_dates(self) -> _pd.DataFrame:
        return self.get_earnings_dates()

    @property
    def history_metadata(self) -> dict:
        return self.get_history_metadata()

    @property
    def funds_data(self) -> FundsData:
        return self.get_funds_data()
