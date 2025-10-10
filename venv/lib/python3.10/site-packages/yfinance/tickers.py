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

import warnings

from . import Ticker, multi
from .live import WebSocket
from .data import YfData
from .const import _SENTINEL_


class Tickers:

    def __repr__(self):
        return f"yfinance.Tickers object <{','.join(self.symbols)}>"

    def __init__(self, tickers, session=None):
        tickers = tickers if isinstance(
            tickers, list) else tickers.replace(',', ' ').split()
        self.symbols = [ticker.upper() for ticker in tickers]
        self.tickers = {ticker: Ticker(ticker, session=session) for ticker in self.symbols}

        self._data = YfData(session=session)

        self._message_handler = None
        self.ws = None

        # self.tickers = _namedtuple(
        #     "Tickers", ticker_objects.keys(), rename=True
        # )(*ticker_objects.values())

    def history(self, period="1mo", interval="1d",
                start=None, end=None, prepost=False,
                actions=True, auto_adjust=True, repair=False,
                proxy=_SENTINEL_,
                threads=True, group_by='column', progress=True,
                timeout=10, **kwargs):

        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
            proxy = _SENTINEL_

        return self.download(
            period, interval,
            start, end, prepost,
            actions, auto_adjust, repair, 
            proxy,
            threads, group_by, progress,
            timeout, **kwargs)

    def download(self, period="1mo", interval="1d",
                 start=None, end=None, prepost=False,
                 actions=True, auto_adjust=True, repair=False, 
                 proxy=_SENTINEL_,
                 threads=True, group_by='column', progress=True,
                 timeout=10, **kwargs):

        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
            proxy = _SENTINEL_

        data = multi.download(self.symbols,
                              start=start, end=end,
                              actions=actions,
                              auto_adjust=auto_adjust,
                              repair=repair,
                              period=period,
                              interval=interval,
                              prepost=prepost,
                              group_by='ticker',
                              threads=threads,
                              progress=progress,
                              timeout=timeout,
                              **kwargs)

        for symbol in self.symbols:
            self.tickers.get(symbol, {})._history = data[symbol]

        if group_by == 'column':
            data.columns = data.columns.swaplevel(0, 1)
            data.sort_index(level=0, axis=1, inplace=True)

        return data

    def news(self):
        return {ticker: [item for item in Ticker(ticker).news] for ticker in self.symbols}

    def live(self, message_handler=None, verbose=True):
        self._message_handler = message_handler

        self.ws = WebSocket(verbose=verbose)
        self.ws.subscribe(self.symbols)
        self.ws.listen(self._message_handler)
