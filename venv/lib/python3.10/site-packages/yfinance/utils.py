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

import datetime as _datetime
import logging
import re
import re as _re
import sys as _sys
import threading
from functools import wraps
from inspect import getmembers
from types import FunctionType
from typing import List, Optional

import numpy as _np
import pandas as _pd
import pytz as _tz
from dateutil.relativedelta import relativedelta
from pytz import UnknownTimeZoneError

from yfinance import const

# From https://stackoverflow.com/a/59128615
def attributes(obj):
    disallowed_names = {
        name for name, value in getmembers(type(obj))
        if isinstance(value, FunctionType)}
    return {
        name: getattr(obj, name) for name in dir(obj)
        if name[0] != '_' and name not in disallowed_names and hasattr(obj, name)}


# Logging
# Note: most of this logic is adding indentation with function depth,
#       so that DEBUG log is readable.
class IndentLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        if get_yf_logger().isEnabledFor(logging.DEBUG):
            i = ' ' * self.extra['indent']
            if not isinstance(msg, str):
                msg = str(msg)
            msg = '\n'.join([i + m for m in msg.split('\n')])
        return msg, kwargs


_indentation_level = threading.local()


class IndentationContext:
    def __init__(self, increment=1):
        self.increment = increment

    def __enter__(self):
        _indentation_level.indent = getattr(_indentation_level, 'indent', 0) + self.increment

    def __exit__(self, exc_type, exc_val, exc_tb):
        _indentation_level.indent -= self.increment


def get_indented_logger(name=None):
    # Never cache the returned value! Will break indentation.
    return IndentLoggerAdapter(logging.getLogger(name), {'indent': getattr(_indentation_level, 'indent', 0)})


def log_indent_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_indented_logger('yfinance')
        logger.debug(f'Entering {func.__name__}()')

        with IndentationContext():
            result = func(*args, **kwargs)

        logger.debug(f'Exiting {func.__name__}()')
        return result

    return wrapper


class MultiLineFormatter(logging.Formatter):
    # The 'fmt' formatting further down is only applied to first line
    # of log message, specifically the padding after %level%.
    # For multi-line messages, need to manually copy over padding.
    def __init__(self, fmt):
        super().__init__(fmt)
        # Extract amount of padding
        match = _re.search(r'%\(levelname\)-(\d+)s', fmt)
        self.level_length = int(match.group(1)) if match else 0

    def format(self, record):
        original = super().format(record)
        lines = original.split('\n')
        levelname = lines[0].split(' ')[0]
        if len(lines) <= 1:
            return original
        else:
            # Apply padding to all lines below first
            formatted = [lines[0]]
            if self.level_length == 0:
                padding = ' ' * len(levelname)
            else:
                padding = ' ' * self.level_length
            padding += ' '  # +1 for space between level and message
            formatted.extend(padding + line for line in lines[1:])
            return '\n'.join(formatted)


yf_logger = None
yf_log_indented = False


class YFLogFormatter(logging.Filter):
    # Help be consistent with structuring YF log messages
    def filter(self, record):
        msg = record.msg
        if hasattr(record, 'yf_cat'):
            msg = f"{record.yf_cat}: {msg}"
        if hasattr(record, 'yf_interval'):
            msg = f"{record.yf_interval}: {msg}"
        if hasattr(record, 'yf_symbol'):
            msg = f"{record.yf_symbol}: {msg}"
        record.msg = msg
        return True


def get_yf_logger():
    global yf_logger
    global yf_log_indented
    if yf_log_indented:
        yf_logger = get_indented_logger('yfinance')
    elif yf_logger is None:
        yf_logger = logging.getLogger('yfinance')
        yf_logger.addFilter(YFLogFormatter())
    return yf_logger


def enable_debug_mode():
    global yf_logger
    global yf_log_indented
    if not yf_log_indented:
        yf_logger = logging.getLogger('yfinance')
        yf_logger.setLevel(logging.DEBUG)
        if yf_logger.handlers is None or len(yf_logger.handlers) == 0:
            h = logging.StreamHandler()
            # Ensure different level strings don't interfere with indentation
            formatter = MultiLineFormatter(fmt='%(levelname)-8s %(message)s')
            h.setFormatter(formatter)
            yf_logger.addHandler(h)
        yf_logger = get_indented_logger()
        yf_log_indented = True


def is_isin(string):
    return bool(_re.match("^([A-Z]{2})([A-Z0-9]{9})([0-9])$", string))


def get_all_by_isin(isin):
    if not (is_isin(isin)):
        raise ValueError("Invalid ISIN number")

    # Deferred this to prevent circular imports
    from .search import Search

    search = Search(query=isin, max_results=1)

    # Extract the first quote and news
    ticker = search.quotes[0] if search.quotes else {}
    news = search.news

    return {
        'ticker': {
            'symbol': ticker.get('symbol', ''),
            'shortname': ticker.get('shortname', ''),
            'longname': ticker.get('longname', ''),
            'type': ticker.get('quoteType', ''),
            'exchange': ticker.get('exchDisp', ''),
        },
        'news': news
    }


def get_ticker_by_isin(isin):
    data = get_all_by_isin(isin)
    return data.get('ticker', {}).get('symbol', '')


def get_info_by_isin(isin):
    data = get_all_by_isin(isin)
    return data.get('ticker', {})


def get_news_by_isin(isin):
    data = get_all_by_isin(isin)
    return data.get('news', {})


def empty_df(index=None):
    if index is None:
        index = []
    empty = _pd.DataFrame(index=index, data={
        'Open': _np.nan, 'High': _np.nan, 'Low': _np.nan,
        'Close': _np.nan, 'Adj Close': _np.nan, 'Volume': _np.nan})
    empty.index.name = 'Date'
    return empty


def empty_earnings_dates_df():
    empty = _pd.DataFrame(
        columns=["Symbol", "Company", "Earnings Date",
                 "EPS Estimate", "Reported EPS", "Surprise(%)"])
    return empty


def build_template(data):
    """
    build_template returns the details required to rebuild any of the yahoo finance financial statements in the same order as the yahoo finance webpage. The function is built to be used on the "FinancialTemplateStore" json which appears in any one of the three yahoo finance webpages: "/financials", "/cash-flow" and "/balance-sheet".

    Returns:
        - template_annual_order: The order that annual figures should be listed in.
        - template_ttm_order: The order that TTM (Trailing Twelve Month) figures should be listed in.
        - template_order: The order that quarterlies should be in (note that quarterlies have no pre-fix - hence why this is required).
        - level_detail: The level of each individual line item. E.g. for the "/financials" webpage, "Total Revenue" is a level 0 item and is the summation of "Operating Revenue" and "Excise Taxes" which are level 1 items.

    """
    template_ttm_order = []  # Save the TTM (Trailing Twelve Months) ordering to an object.
    template_annual_order = []  # Save the annual ordering to an object.
    template_order = []  # Save the ordering to an object (this can be utilized for quarterlies)
    level_detail = []  # Record the level of each line item of the income statement ("Operating Revenue" and "Excise Taxes" sum to return "Total Revenue" we need to keep track of this)

    def traverse(node, level):
        """
        A recursive function that visits a node and its children.

        Args:
            node: The current node in the data structure.
            level: The depth of the current node in the data structure.
        """
        if level > 5:  # Stop when level is above 5
            return
        template_ttm_order.append(f"trailing{node['key']}")
        template_annual_order.append(f"annual{node['key']}")
        template_order.append(f"{node['key']}")
        level_detail.append(level)
        if 'children' in node:  # Check if the node has children
            for child in node['children']:  # If yes, traverse each child
                traverse(child, level + 1)  # Increment the level by 1 for each child

    for key in data['template']:  # Loop through the data
        traverse(key, 0)  # Call the traverse function with initial level being 0

    return template_ttm_order, template_annual_order, template_order, level_detail


def retrieve_financial_details(data):
    """
    retrieve_financial_details returns all of the available financial details under the
    "QuoteTimeSeriesStore" for any of the following three yahoo finance webpages:
    "/financials", "/cash-flow" and "/balance-sheet".

    Returns:
        - TTM_dicts: A dictionary full of all of the available Trailing Twelve Month figures, this can easily be converted to a pandas dataframe.
        - Annual_dicts: A dictionary full of all of the available Annual figures, this can easily be converted to a pandas dataframe.
    """
    TTM_dicts = []  # Save a dictionary object to store the TTM financials.
    Annual_dicts = []  # Save a dictionary object to store the Annual financials.

    for key, timeseries in data.get('timeSeries', {}).items():  # Loop through the time series data to grab the key financial figures.
        try:
            if timeseries:
                time_series_dict = {'index': key}
                for each in timeseries:  # Loop through the years
                    if not each:
                        continue
                    time_series_dict[each.get('asOfDate')] = each.get('reportedValue')
                if 'trailing' in key:
                    TTM_dicts.append(time_series_dict)
                elif 'annual' in key:
                    Annual_dicts.append(time_series_dict)
        except KeyError as e:
            print(f"An error occurred while processing the key: {e}")
    return TTM_dicts, Annual_dicts


def format_annual_financial_statement(level_detail, annual_dicts, annual_order, ttm_dicts=None, ttm_order=None):
    """
    format_annual_financial_statement formats any annual financial statement

    Returns:
        - _statement: A fully formatted annual financial statement in pandas dataframe.
    """
    Annual = _pd.DataFrame.from_dict(annual_dicts).set_index("index")
    Annual = Annual.reindex(annual_order)
    Annual.index = Annual.index.str.replace(r'annual', '')

    # Note: balance sheet is the only financial statement with no ttm detail
    if ttm_dicts and ttm_order:
        TTM = _pd.DataFrame.from_dict(ttm_dicts).set_index("index").reindex(ttm_order)
        # Add 'TTM' prefix to all column names, so if combined we can tell
        # the difference between actuals and TTM (similar to yahoo finance).
        TTM.columns = ['TTM ' + str(col) for col in TTM.columns]
        TTM.index = TTM.index.str.replace(r'trailing', '')
        _statement = Annual.merge(TTM, left_index=True, right_index=True)
    else:
        _statement = Annual

    _statement.index = camel2title(_statement.T.index)
    _statement['level_detail'] = level_detail
    _statement = _statement.set_index([_statement.index, 'level_detail'])
    _statement = _statement[sorted(_statement.columns, reverse=True)]
    _statement = _statement.dropna(how='all')
    return _statement


def format_quarterly_financial_statement(_statement, level_detail, order):
    """
    format_quarterly_financial_statements formats any quarterly financial statement

    Returns:
        - _statement: A fully formatted quarterly financial statement in pandas dataframe.
    """
    _statement = _statement.reindex(order)
    _statement.index = camel2title(_statement.T)
    _statement['level_detail'] = level_detail
    _statement = _statement.set_index([_statement.index, 'level_detail'])
    _statement = _statement[sorted(_statement.columns, reverse=True)]
    _statement = _statement.dropna(how='all')
    _statement.columns = _pd.to_datetime(_statement.columns).date
    return _statement


def camel2title(strings: List[str], sep: str = ' ', acronyms: Optional[List[str]] = None) -> List[str]:
    if isinstance(strings, str) or not hasattr(strings, '__iter__'):
        raise TypeError("camel2title() 'strings' argument must be iterable of strings")
    if len(strings) == 0:
        return strings
    if not isinstance(strings[0], str):
        raise TypeError("camel2title() 'strings' argument must be iterable of strings")
    if not isinstance(sep, str) or len(sep) != 1:
        raise ValueError(f"camel2title() 'sep' argument = '{sep}' must be single character")
    if _re.match("[a-zA-Z0-9]", sep):
        raise ValueError(f"camel2title() 'sep' argument = '{sep}' cannot be alpha-numeric")
    if _re.escape(sep) != sep and sep not in {' ', '-'}:
        # Permit some exceptions, I don't understand why they get escaped
        raise ValueError(f"camel2title() 'sep' argument = '{sep}' cannot be special character")

    if acronyms is None:
        pat = "([a-z])([A-Z])"
        rep = rf"\g<1>{sep}\g<2>"
        return [_re.sub(pat, rep, s).title() for s in strings]

    # Handling acronyms requires more care. Assumes Yahoo returns acronym strings upper-case
    if isinstance(acronyms, str) or not hasattr(acronyms, '__iter__') or not isinstance(acronyms[0], str):
        raise TypeError("camel2title() 'acronyms' argument must be iterable of strings")
    for a in acronyms:
        if not _re.match("^[A-Z]+$", a):
            raise ValueError(f"camel2title() 'acronyms' argument must only contain upper-case, but '{a}' detected")

    # Insert 'sep' between lower-then-upper-case
    pat = "([a-z])([A-Z])"
    rep = rf"\g<1>{sep}\g<2>"
    strings = [_re.sub(pat, rep, s) for s in strings]

    # Insert 'sep' after acronyms
    for a in acronyms:
        pat = f"({a})([A-Z][a-z])"
        rep = rf"\g<1>{sep}\g<2>"
        strings = [_re.sub(pat, rep, s) for s in strings]

    # Apply str.title() to non-acronym words
    strings = [s.split(sep) for s in strings]
    strings = [[j.title() if j not in acronyms else j for j in s] for s in strings]
    strings = [sep.join(s) for s in strings]

    return strings


def snake_case_2_camelCase(s):
    sc = s.split('_')[0] + ''.join(x.title() for x in s.split('_')[1:])
    return sc


def _parse_user_dt(dt, exchange_tz):
    if isinstance(dt, int):
        dt = _pd.Timestamp(dt, unit="s", tz=exchange_tz)
    else:
        # Convert str/date -> datetime, set tzinfo=exchange, get timestamp:
        if isinstance(dt, str):
            dt = _datetime.datetime.strptime(str(dt), '%Y-%m-%d')
        if isinstance(dt, _datetime.date) and not isinstance(dt, _datetime.datetime):
            dt = _datetime.datetime.combine(dt, _datetime.time(0))
        if isinstance(dt, _datetime.datetime):
            if dt.tzinfo is None:
                # Assume user is referring to exchange's timezone
                dt = _pd.Timestamp(dt).tz_localize(exchange_tz)
            else:
                dt = _pd.Timestamp(dt).tz_convert(exchange_tz)
        else: # if we reached here, then it hasn't been any known type
            raise ValueError(f"Unable to parse input dt {dt} of type {type(dt)}")
    return dt


def _interval_to_timedelta(interval):
    if interval[-1] == "d":
        return relativedelta(days=int(interval[:-1]))
    elif interval[-2:] == "wk":
        return relativedelta(weeks=int(interval[:-2]))
    elif interval[-2:] == "mo":
        return relativedelta(months=int(interval[:-2]))
    elif interval[-1] == "y":
        return relativedelta(years=int(interval[:-1]))
    else:
        return _pd.Timedelta(interval)


def is_valid_period_format(period):
    """Check if the provided period has a valid format."""
    if period is None:
        return False

    # Regex pattern to match valid period formats like '1d', '2wk', '3mo', '1y'
    valid_pattern = r"^[1-9]\d*(d|wk|mo|y)$"
    return bool(re.match(valid_pattern, period))


def auto_adjust(data):
    col_order = data.columns
    df = data.copy()
    ratio = (df["Adj Close"] / df["Close"]).to_numpy()
    df["Adj Open"] = df["Open"] * ratio
    df["Adj High"] = df["High"] * ratio
    df["Adj Low"] = df["Low"] * ratio

    df.drop(
        ["Open", "High", "Low", "Close"],
        axis=1, inplace=True)

    df.rename(columns={
        "Adj Open": "Open", "Adj High": "High",
        "Adj Low": "Low", "Adj Close": "Close"
    }, inplace=True)

    return df[[c for c in col_order if c in df.columns]]


def back_adjust(data):
    """ back-adjusted data to mimic true historical prices """

    col_order = data.columns
    df = data.copy()
    ratio = df["Adj Close"] / df["Close"]
    df["Adj Open"] = df["Open"] * ratio
    df["Adj High"] = df["High"] * ratio
    df["Adj Low"] = df["Low"] * ratio

    df.drop(
        ["Open", "High", "Low", "Adj Close"],
        axis=1, inplace=True)

    df.rename(columns={
        "Adj Open": "Open", "Adj High": "High",
        "Adj Low": "Low"
    }, inplace=True)

    return df[[c for c in col_order if c in df.columns]]


def parse_quotes(data):
    timestamps = data["timestamp"]
    ohlc = data["indicators"]["quote"][0]
    volumes = ohlc["volume"]
    opens = ohlc["open"]
    closes = ohlc["close"]
    lows = ohlc["low"]
    highs = ohlc["high"]

    adjclose = closes
    if "adjclose" in data["indicators"]:
        adjclose = data["indicators"]["adjclose"][0]["adjclose"]

    quotes = _pd.DataFrame({"Open": opens,
                            "High": highs,
                            "Low": lows,
                            "Close": closes,
                            "Adj Close": adjclose,
                            "Volume": volumes})

    quotes.index = _pd.to_datetime(timestamps, unit="s")
    quotes.sort_index(inplace=True)

    return quotes


def parse_actions(data):
    dividends = None
    capital_gains = None
    splits = None

    if "events" in data:
        if "dividends" in data["events"] and len(data["events"]['dividends']) > 0:
            dividends = _pd.DataFrame(
                data=list(data["events"]["dividends"].values()))
            dividends.set_index("date", inplace=True)
            dividends.index = _pd.to_datetime(dividends.index, unit="s")
            dividends.sort_index(inplace=True)
            if 'currency' in dividends.columns and (dividends['currency'] == '').all():
                # Currency column useless, drop it.
                dividends = dividends.drop('currency', axis=1)
            dividends = dividends.rename(columns={'amount': 'Dividends'})

        if "capitalGains" in data["events"] and len(data["events"]['capitalGains']) > 0:
            capital_gains = _pd.DataFrame(
                data=list(data["events"]["capitalGains"].values()))
            capital_gains.set_index("date", inplace=True)
            capital_gains.index = _pd.to_datetime(capital_gains.index, unit="s")
            capital_gains.sort_index(inplace=True)
            capital_gains.columns = ["Capital Gains"]

        if "splits" in data["events"] and len(data["events"]['splits']) > 0:
            splits = _pd.DataFrame(
                data=list(data["events"]["splits"].values()))
            splits.set_index("date", inplace=True)
            splits.index = _pd.to_datetime(splits.index, unit="s")
            splits.sort_index(inplace=True)
            splits["Stock Splits"] = splits["numerator"] / splits["denominator"]
            splits = splits[["Stock Splits"]]

    if dividends is None:
        dividends = _pd.DataFrame(
            columns=["Dividends"], index=_pd.DatetimeIndex([]))
    if capital_gains is None:
        capital_gains = _pd.DataFrame(
            columns=["Capital Gains"], index=_pd.DatetimeIndex([]))
    if splits is None:
        splits = _pd.DataFrame(
            columns=["Stock Splits"], index=_pd.DatetimeIndex([]))

    return dividends, splits, capital_gains


def set_df_tz(df, interval, tz):
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(tz)
    return df


def fix_Yahoo_returning_prepost_unrequested(quotes, interval, tradingPeriods):
    # Sometimes Yahoo returns post-market data despite not requesting it.
    # Normally happens on half-day early closes.
    #
    # And sometimes returns pre-market data despite not requesting it.
    # E.g. some London tickers.
    tps_df = tradingPeriods.copy()
    tps_df["_date"] = tps_df.index.date
    quotes["_date"] = quotes.index.date
    idx = quotes.index.copy()
    quotes = quotes.merge(tps_df, how="left")
    quotes.index = idx
    # "end" = end of regular trading hours (including any auction)
    f_drop = quotes.index >= quotes["end"]
    f_drop = f_drop | (quotes.index < quotes["start"])
    if f_drop.any():
        # When printing report, ignore rows that were already NaNs:
        # f_na = quotes[["Open","Close"]].isna().all(axis=1)
        # n_nna = quotes.shape[0] - _np.sum(f_na)
        # n_drop_nna = _np.sum(f_drop & ~f_na)
        # quotes_dropped = quotes[f_drop]
        # if debug and n_drop_nna > 0:
        #     print(f"Dropping {n_drop_nna}/{n_nna} intervals for falling outside regular trading hours")
        quotes = quotes[~f_drop]
    quotes = quotes.drop(["_date", "start", "end"], axis=1)
    return quotes


def _dts_in_same_interval(dt1, dt2, interval):
    # Check if second date dt2 in interval starting at dt1

    if interval == '1d':
        last_rows_same_interval = dt1.date() == dt2.date()
    elif interval == "1wk":
        last_rows_same_interval = (dt2 - dt1).days < 7
    elif interval == "1mo":
        last_rows_same_interval = dt1.month == dt2.month
    elif interval == "3mo":
        shift = (dt1.month % 3) - 1
        q1 = (dt1.month - shift - 1) // 3 + 1
        q2 = (dt2.month - shift - 1) // 3 + 1
        year_diff = dt2.year - dt1.year
        quarter_diff = q2 - q1 + 4*year_diff
        last_rows_same_interval = quarter_diff == 0
    else:
        last_rows_same_interval = (dt2 - dt1) < _pd.Timedelta(interval)
    return last_rows_same_interval


def fix_Yahoo_returning_live_separate(quotes, interval, tz_exchange, prepost, repair=False, currency=None):
    # Yahoo bug fix. If market is open today then Yahoo normally returns
    # todays data as a separate row from rest-of week/month interval in above row.
    # Seems to depend on what exchange e.g. crypto OK.
    # Fix = merge them together

    if interval[-1] not in ['m', 'h']:
        prepost = False

    dropped_row = None
    if len(quotes) > 1:
        dt1 = quotes.index[-1]
        dt2 = quotes.index[-2]
        if quotes.index.tz is None:
            dt1 = dt1.tz_localize("UTC")
            dt2 = dt2.tz_localize("UTC")
        dt1 = dt1.tz_convert(tz_exchange)
        dt2 = dt2.tz_convert(tz_exchange)
        if interval == "1d":
            # Similar bug in daily data except most data is simply duplicated
            # - exception is volume, *slightly* greater on final row (and matches website)
            if dt1.date() == dt2.date():
                # Last two rows are on same day. Drop second-to-last row
                dropped_row = quotes.iloc[-2]
                quotes = _pd.concat([quotes.iloc[:-2], quotes.iloc[-1:]])
        else:
            if _dts_in_same_interval(dt2, dt1, interval):
                # Last two rows are within same interval
                idx1 = quotes.index[-1]
                idx2 = quotes.index[-2]
                if idx1 == idx2:
                    # Yahoo returning last interval duplicated, which means
                    # Yahoo is not returning live data (phew!)
                    return quotes, None

                if prepost:
                    # Possibly dt1 is just start of post-market
                    if dt1.second == 0:
                        # assume post-market interval
                        return quotes, None

                ss = quotes['Stock Splits'].iloc[-2:].replace(0,1).prod()
                if repair:
                    # First, check if one row is ~100x the other. A £/pence mixup on LSE.
                    # Avoid if a stock split near 100
                    if currency == 'KWF':
                        # Kuwaiti Dinar divided into 1000 not 100
                        currency_divide = 1000
                    else:
                        currency_divide = 100
                    # if ss < 75 or ss > 125:
                    if abs(ss/currency_divide-1) > 0.25:
                        ratio = quotes.loc[idx1, const._PRICE_COLNAMES_] / quotes.loc[idx2, const._PRICE_COLNAMES_]
                        if ((ratio/currency_divide-1).abs() < 0.05).all():
                            # newer prices are 100x
                            for c in const._PRICE_COLNAMES_:
                                quotes.loc[idx2, c] *= 100
                        elif((ratio*currency_divide-1).abs() < 0.05).all():
                            # newer prices are 0.01x
                            for c in const._PRICE_COLNAMES_:
                                quotes.loc[idx2, c] *= 0.01

                if _np.isnan(quotes.loc[idx2, "Open"]):
                    quotes.loc[idx2, "Open"] = quotes["Open"].iloc[-1]
                # Note: nanmax() & nanmin() ignores NaNs, but still need to check not all are NaN to avoid warnings
                if not _np.isnan(quotes["High"].iloc[-1]):
                    quotes.loc[idx2, "High"] = _np.nanmax([quotes["High"].iloc[-1], quotes["High"].iloc[-2]])
                    if "Adj High" in quotes.columns:
                        quotes.loc[idx2, "Adj High"] = _np.nanmax([quotes["Adj High"].iloc[-1], quotes["Adj High"].iloc[-2]])

                if not _np.isnan(quotes["Low"].iloc[-1]):
                    quotes.loc[idx2, "Low"] = _np.nanmin([quotes["Low"].iloc[-1], quotes["Low"].iloc[-2]])
                    if "Adj Low" in quotes.columns:
                        quotes.loc[idx2, "Adj Low"] = _np.nanmin([quotes["Adj Low"].iloc[-1], quotes["Adj Low"].iloc[-2]])

                quotes.loc[idx2, "Close"] = quotes["Close"].iloc[-1]
                if "Adj Close" in quotes.columns:
                    quotes.loc[idx2, "Adj Close"] = quotes["Adj Close"].iloc[-1]
                quotes.loc[idx2, "Volume"] += quotes["Volume"].iloc[-1]
                quotes.loc[idx2, "Dividends"] += quotes["Dividends"].iloc[-1]
                if ss != 1.0:
                    quotes.loc[idx2, "Stock Splits"] = ss
                dropped_row = quotes.iloc[-1]
                quotes = quotes.drop(quotes.index[-1])

    return quotes, dropped_row


def safe_merge_dfs(df_main, df_sub, interval):
    if df_sub.empty:
        raise Exception("No data to merge")
    if df_main.empty:
        return df_main

    data_cols = [c for c in df_sub.columns if c not in df_main]
    if len(data_cols) > 1:
        raise Exception("Expected 1 data col")
    data_col = data_cols[0]

    df_main = df_main.sort_index()
    intraday = interval.endswith('m') or interval.endswith('s')

    td = _interval_to_timedelta(interval)
    if intraday:
        # On some exchanges the event can occur before market open.
        # Problem when combining with intraday data.
        # Solution = use dates, not datetimes, to map/merge.
        df_main['_date'] = df_main.index.date
        df_sub['_date'] = df_sub.index.date
        indices = _np.searchsorted(_np.append(df_main['_date'], [df_main['_date'].iloc[-1]+td]), df_sub['_date'], side='left')
        df_main = df_main.drop('_date', axis=1)
        df_sub = df_sub.drop('_date', axis=1)
    else:
        indices = _np.searchsorted(_np.append(df_main.index, df_main.index[-1] + td), df_sub.index, side='right')
        indices -= 1  # Convert from [[i-1], [i]) to [[i], [i+1])
    # Numpy.searchsorted does not handle out-of-range well, so handle manually:
    if intraday:
        for i in range(len(df_sub.index)):
            dt = df_sub.index[i].date()
            if dt < df_main.index[0].date() or dt >= df_main.index[-1].date() + _datetime.timedelta(days=1):
                # Out-of-range
                indices[i] = -1
    else:
        for i in range(len(df_sub.index)):
            dt = df_sub.index[i]
            if dt < df_main.index[0] or dt >= df_main.index[-1] + td:
                # Out-of-range
                indices[i] = -1

    f_outOfRange = indices == -1
    if f_outOfRange.any():
        if intraday:
            # Discard out-of-range dividends in intraday data, assume user not interested
            df_sub = df_sub[~f_outOfRange]
            if df_sub.empty:
                df_main['Dividends'] = 0.0
                return df_main

            # df_sub changed so recalc indices:
            df_main['_date'] = df_main.index.date
            df_sub['_date'] = df_sub.index.date
            indices = _np.searchsorted(_np.append(df_main['_date'], [df_main['_date'].iloc[-1]+td]), df_sub['_date'], side='left')
            df_main = df_main.drop('_date', axis=1)
            df_sub = df_sub.drop('_date', axis=1)
        else:
            empty_row_data = {**{c:[_np.nan] for c in const._PRICE_COLNAMES_}, 'Volume':[0]}
            if interval == '1d':
                # For 1d, add all out-of-range event dates
                for i in _np.where(f_outOfRange)[0]:
                    dt = df_sub.index[i]
                    get_yf_logger().debug(f"Adding out-of-range {data_col} @ {dt.date()} in new prices row of NaNs")
                    empty_row = _pd.DataFrame(data=empty_row_data, index=[dt])
                    df_main = _pd.concat([df_main, empty_row], sort=True)
            else:
                # Else, only add out-of-range event dates if occurring in interval
                # immediately after last price row
                last_dt = df_main.index[-1]
                next_interval_start_dt = last_dt + td
                next_interval_end_dt = next_interval_start_dt + td
                for i in _np.where(f_outOfRange)[0]:
                    dt = df_sub.index[i]
                    if next_interval_start_dt <= dt < next_interval_end_dt:
                        get_yf_logger().debug(f"Adding out-of-range {data_col} @ {dt.date()} in new prices row of NaNs")
                        empty_row = _pd.DataFrame(data=empty_row_data, index=[dt])
                        df_main = _pd.concat([df_main, empty_row], sort=True)
            df_main = df_main.sort_index()

            # Re-calculate indices
            indices = _np.searchsorted(_np.append(df_main.index, df_main.index[-1] + td), df_sub.index, side='right')
            indices -= 1  # Convert from [[i-1], [i]) to [[i], [i+1])
            # Numpy.searchsorted does not handle out-of-range well, so handle manually:
            for i in range(len(df_sub.index)):
                dt = df_sub.index[i]
                if dt < df_main.index[0] or dt >= df_main.index[-1] + td:
                    # Out-of-range
                    indices[i] = -1

    f_outOfRange = indices == -1
    if f_outOfRange.any():
        if intraday or interval in ['1d', '1wk']:
            raise Exception(f"The following '{data_col}' events are out-of-range, did not expect with interval {interval}: {df_sub.index[f_outOfRange]}")
        get_yf_logger().debug(f'Discarding these {data_col} events:' + '\n' + str(df_sub[f_outOfRange]))
        df_sub = df_sub[~f_outOfRange].copy()
        indices = indices[~f_outOfRange]

    def _reindex_events(df, new_index, data_col_name):
        if len(new_index) == len(set(new_index)):
            # No duplicates, easy
            df.index = new_index
            return df

        df["_NewIndex"] = new_index
        # Duplicates present within periods but can aggregate
        if data_col_name in ["Dividends", "Capital Gains"]:
            # Add
            df = df.groupby("_NewIndex").sum()
            df.index.name = None
        elif data_col_name == "Stock Splits":
            # Product
            df = df.groupby("_NewIndex").prod()
            df.index.name = None
        else:
            raise Exception(f"New index contains duplicates but unsure how to aggregate for '{data_col_name}'")
        if "_NewIndex" in df.columns:
            df = df.drop("_NewIndex", axis=1)
        return df

    new_index = df_main.index[indices]
    df_sub = _reindex_events(df_sub, new_index, data_col)

    df = df_main.join(df_sub)
    f_na = df[data_col].isna()
    data_lost = sum(~f_na) < df_sub.shape[0]
    if data_lost:
        raise Exception('Data was lost in merge, investigate')

    return df


def fix_Yahoo_dst_issue(df, interval):
    if interval in ["1d", "1w", "1wk"]:
        # These intervals should start at time 00:00. But for some combinations of date and timezone,
        # Yahoo has time off by few hours (e.g. Brazil 23:00 around Jan-2022). Suspect DST problem.
        # The clue is (a) minutes=0 and (b) hour near 0.
        # Obviously Yahoo meant 00:00, so ensure this doesn't affect date conversion:
        f_pre_midnight = (df.index.minute == 0) & (df.index.hour.isin([22, 23]))
        dst_error_hours = _np.array([0] * df.shape[0])
        dst_error_hours[f_pre_midnight] = 24 - df.index[f_pre_midnight].hour
        df.index += _pd.to_timedelta(dst_error_hours, 'h')
    return df


def is_valid_timezone(tz: str) -> bool:
    try:
        _tz.timezone(tz)
    except UnknownTimeZoneError:
        return False
    return True


def format_history_metadata(md, tradingPeriodsOnly=True):
    if not isinstance(md, dict):
        return md
    if len(md) == 0:
        return md

    tz = md["exchangeTimezoneName"]

    if not tradingPeriodsOnly:
        for k in ["firstTradeDate", "regularMarketTime"]:
            if k in md and md[k] is not None:
                if isinstance(md[k], int):
                    md[k] = _pd.to_datetime(md[k], unit='s', utc=True).tz_convert(tz)

        if "currentTradingPeriod" in md:
            for m in ["regular", "pre", "post"]:
                if m in md["currentTradingPeriod"] and isinstance(md["currentTradingPeriod"][m]["start"], int):
                    for t in ["start", "end"]:
                        md["currentTradingPeriod"][m][t] = \
                            _pd.to_datetime(md["currentTradingPeriod"][m][t], unit='s', utc=True).tz_convert(tz)
                    del md["currentTradingPeriod"][m]["gmtoffset"]
                    del md["currentTradingPeriod"][m]["timezone"]

    if "tradingPeriods" in md:
        tps = md["tradingPeriods"]
        if tps == {"pre": [], "post": []}:
            # Ignore
            pass
        elif isinstance(tps, (list, dict)):
            if isinstance(tps, list):
                # Only regular times
                df = _pd.DataFrame.from_records(_np.hstack(tps))
                df = df.drop(["timezone", "gmtoffset"], axis=1)
                df["start"] = _pd.to_datetime(df["start"], unit='s', utc=True).dt.tz_convert(tz)
                df["end"] = _pd.to_datetime(df["end"], unit='s', utc=True).dt.tz_convert(tz)
            elif isinstance(tps, dict):
                # Includes pre- and post-market
                pre_df = _pd.DataFrame.from_records(_np.hstack(tps["pre"]))
                post_df = _pd.DataFrame.from_records(_np.hstack(tps["post"]))
                regular_df = _pd.DataFrame.from_records(_np.hstack(tps["regular"]))

                pre_df = pre_df.rename(columns={"start": "pre_start", "end": "pre_end"}).drop(["timezone", "gmtoffset"], axis=1)
                post_df = post_df.rename(columns={"start": "post_start", "end": "post_end"}).drop(["timezone", "gmtoffset"], axis=1)
                regular_df = regular_df.drop(["timezone", "gmtoffset"], axis=1)

                cols = ["pre_start", "pre_end", "start", "end", "post_start", "post_end"]
                df = regular_df.join(pre_df).join(post_df)
                for c in cols:
                    df[c] = _pd.to_datetime(df[c], unit='s', utc=True).dt.tz_convert(tz)
                df = df[cols]

            df.index = _pd.to_datetime(df["start"].dt.date)
            df.index = df.index.tz_localize(tz)
            df.index.name = "Date"

            md["tradingPeriods"] = df

    return md


class ProgressBar:
    def __init__(self, iterations, text='completed'):
        self.text = text
        self.iterations = iterations
        self.prog_bar = '[]'
        self.fill_char = '*'
        self.width = 50
        self.__update_amount(0)
        self.elapsed = 1

    def completed(self):
        if self.elapsed > self.iterations:
            self.elapsed = self.iterations
        self.update_iteration(1)
        print('\r' + str(self), end='', file=_sys.stderr)
        _sys.stderr.flush()
        print("", file=_sys.stderr)

    def animate(self, iteration=None):
        if iteration is None:
            self.elapsed += 1
            iteration = self.elapsed
        else:
            self.elapsed += iteration

        print('\r' + str(self), end='', file=_sys.stderr)
        _sys.stderr.flush()
        self.update_iteration()

    def update_iteration(self, val=None):
        val = val if val is not None else self.elapsed / float(self.iterations)
        self.__update_amount(val * 100.0)
        self.prog_bar += f"  {self.elapsed} of {self.iterations} {self.text}"

    def __update_amount(self, new_amount):
        percent_done = int(round((new_amount / 100.0) * 100.0))
        all_full = self.width - 2
        num_hashes = int(round((percent_done / 100.0) * all_full))
        self.prog_bar = '[' + self.fill_char * num_hashes + ' ' * (all_full - num_hashes) + ']'
        pct_place = (len(self.prog_bar) // 2) - len(str(percent_done))
        pct_string = f'{percent_done}%'
        self.prog_bar = self.prog_bar[0:pct_place] + (pct_string + self.prog_bar[pct_place + len(pct_string):])

    def __str__(self):
        return str(self.prog_bar)

def dynamic_docstring(placeholders: dict):
    """
    A decorator to dynamically update the docstring of a function or method.
    
    Args:
        placeholders (dict): A dictionary where keys are placeholder names and values are the strings to insert.
    """
    def decorator(func):
        if func.__doc__:
            docstring = func.__doc__
            # Replace each placeholder with its corresponding value
            for key, value in placeholders.items():
                docstring = docstring.replace(f"{{{key}}}", value)
            func.__doc__ = docstring
        return func
    return decorator

def _generate_table_configurations(title = None) -> str:
    import textwrap
    if title is None:
        title = "Permitted Keys/Values"
    table = textwrap.dedent(f"""
    .. list-table:: {title}
       :widths: 25 75
       :header-rows: 1

       * - Key
         - Values
    """)

    return table

def generate_list_table_from_dict(data: dict, bullets: bool=True, title: str=None) -> str:
    """
    Generate a list-table for the docstring showing permitted keys/values.
    """
    table = _generate_table_configurations(title)
    for k in sorted(data.keys()):
        values = data[k]
        table += ' '*3 + f"* - {k}\n"
        lengths = [len(str(v)) for v in values]
        if bullets and max(lengths) > 5:
            table += ' '*5 + "-\n"
            for value in sorted(values):
                table += ' '*7 + f"- {value}\n"
        else:
            value_str = ', '.join(sorted(values))
            table += ' '*5 + f"- {value_str}\n"
    return table

# def generate_list_table_from_dict_of_dict(data: dict, bullets: bool=True, title: str=None) -> str:
#     """
#     Generate a list-table for the docstring showing permitted keys/values.
#     """
#     table = _generate_table_configurations(title)
#     for k in sorted(data.keys()):
#         values = data[k]
#         table += ' '*3 + f"* - {k}\n"
#         if bullets:
#             table += ' '*5 + "-\n"
#             for value in sorted(values):
#                 table += ' '*7 + f"- {value}\n"
#         else:
#             table += ' '*5 + f"- {values}\n"
#     return table


def generate_list_table_from_dict_universal(data: dict, bullets: bool=True, title: str=None, concat_keys=[]) -> str:
    """
    Generate a list-table for the docstring showing permitted keys/values.
    """
    table = _generate_table_configurations(title)
    for k in data.keys():
        values = data[k]

        table += ' '*3 + f"* - {k}\n"
        if isinstance(values, dict):
            table_add = ''

            concat_short_lines = k in concat_keys

            if bullets:
                k_keys = sorted(list(values.keys()))
                current_line = ''
                block_format = 'query' in k_keys
                for i in range(len(k_keys)):
                    k2 = k_keys[i]
                    k2_values = values[k2]
                    k2_values_str = None
                    if isinstance(k2_values, set):
                        k2_values = list(k2_values)
                    elif isinstance(k2_values, dict) and len(k2_values) == 0:
                        k2_values = []
                    if isinstance(k2_values, list):
                        k2_values = sorted(k2_values)
                        all_scalar = all(isinstance(k2v, (int, float, str)) for k2v in k2_values)
                        if all_scalar:
                            k2_values_str = _re.sub(r"[{}\[\]']", "", str(k2_values))

                    if k2_values_str is None:
                        k2_values_str = str(k2_values)

                    if len(current_line) > 0 and (len(current_line) + len(k2_values_str) > 40):
                        # new line
                        table_add += current_line + '\n'
                        current_line = ''

                    if concat_short_lines:
                        if current_line == '':
                            current_line += ' '*5
                            if i == 0:
                                # Only add dash to first
                                current_line += "- "
                            else:
                                current_line += "  "
                            # Don't draw bullet points:
                            current_line += '| '
                        else:
                            current_line += '.  '
                        current_line += f"{k2}: " + k2_values_str
                    else:
                        table_add += ' '*5
                        if i == 0:
                            # Only add dash to first
                            table_add += "- "
                        else:
                            table_add += "  "

                        if '\n' in k2_values_str:
                            # Block format multiple lines
                            table_add += '| ' + f"{k2}: " + "\n"
                            k2_values_str_lines = k2_values_str.split('\n')
                            for j in range(len(k2_values_str_lines)):
                                line = k2_values_str_lines[j]
                                table_add += ' '*7 + '|' + ' '*5 + line
                                if j < len(k2_values_str_lines)-1:
                                    table_add += "\n"
                        else:
                            if block_format:
                                table_add += '| '
                            else:
                                table_add += '* '
                            table_add += f"{k2}: " + k2_values_str

                        table_add += "\n"
                if current_line != '':
                    table_add += current_line + '\n'
            else:
                table_add += ' '*5 + f"- {values}\n"

            table += table_add

        else:
            lengths = [len(str(v)) for v in values]
            if bullets and max(lengths) > 5:
                table += ' '*5 + "-\n"
                for value in sorted(values):
                    table += ' '*7 + f"- {value}\n"
            else:
                value_str = ', '.join(sorted(values))
                table += ' '*5 + f"- {value_str}\n"

    return table
