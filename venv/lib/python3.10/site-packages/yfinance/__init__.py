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

from . import version
from .search import Search
from .lookup import Lookup
from .ticker import Ticker
from .tickers import Tickers
from .multi import download
from .live import WebSocket, AsyncWebSocket
from .utils import enable_debug_mode
from .cache import set_tz_cache_location
from .domain.sector import Sector
from .domain.industry import Industry
from .domain.market import Market
from .data import YfData

from .screener.query import EquityQuery, FundQuery
from .screener.screener import screen, PREDEFINED_SCREENER_QUERIES

__version__ = version.version
__author__ = "Ran Aroussi"

import warnings
warnings.filterwarnings('default', category=DeprecationWarning, module='^yfinance')

__all__ = ['download', 'Market', 'Search', 'Lookup', 'Ticker', 'Tickers', 'enable_debug_mode', 'set_tz_cache_location', 'Sector', 'Industry', 'WebSocket', 'AsyncWebSocket']
# screener stuff:
__all__ += ['EquityQuery', 'FundQuery', 'screen', 'PREDEFINED_SCREENER_QUERIES']

# Config stuff:
_NOTSET=object()
def set_config(proxy=_NOTSET):
    if proxy is not _NOTSET:
        YfData(proxy=proxy)
__all__ += ["set_config"]
