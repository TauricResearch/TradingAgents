from curl_cffi import requests
from math import isclose
import bisect
import datetime as _datetime
import dateutil as _dateutil
import logging
import numpy as np
import pandas as pd
import time as _time
import warnings

from yfinance import shared, utils
from yfinance.const import _BASE_URL_, _PRICE_COLNAMES_, _SENTINEL_
from yfinance.exceptions import YFInvalidPeriodError, YFPricesMissingError, YFTzMissingError, YFRateLimitError

class PriceHistory:
    def __init__(self, data, ticker, tz, session=None, proxy=_SENTINEL_):
        self._data = data
        self.ticker = ticker.upper()
        self.tz = tz
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=5)
            self._data._set_proxy(proxy)
        self.session = session or requests.Session(impersonate="chrome")

        self._history_cache = {}
        self._history_metadata = None
        self._history_metadata_formatted = False

        # Limit recursion depth when repairing prices
        self._reconstruct_start_interval = None

    @utils.log_indent_decorator
    def history(self, period=None, interval="1d",
                start=None, end=None, prepost=False, actions=True,
                auto_adjust=True, back_adjust=False, repair=False, keepna=False,
                proxy=_SENTINEL_, rounding=False, timeout=10,
                raise_errors=False) -> pd.DataFrame:
        """
        :Parameters:
            period : str
              | Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
              | Default: 1mo
              | Can combine with start/end e.g. end = start + period
            interval : str
              | Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
              | Intraday data cannot extend last 60 days
            start : str
              | Download start date string (YYYY-MM-DD) or _datetime, inclusive.
              | Default: 99 years ago
              | E.g. for start="2020-01-01", first data point = "2020-01-01"
            end : str
              | Download end date string (YYYY-MM-DD) or _datetime, exclusive.
              | Default: now
              | E.g. for end="2023-01-01", last data point = "2022-12-31"
            prepost : bool
              | Include Pre and Post market data in results?
              | Default: False
            auto_adjust : bool
              | Adjust all OHLC automatically?
              | Default: True
            back_adjust : bool
              | Back-adjusted data to mimic true historical prices
            repair : bool
              | Fixes price errors in Yahoo data: 100x, missing, bad dividend adjust.
              | Default: False
              | Full details at: :doc:`../advanced/price_repair`.
            keepna : bool
              | Keep NaN rows returned by Yahoo?
              | Default: False
            rounding : bool
              | Optional: Round values to 2 decimal places?
              | Default: False = use precision suggested by Yahoo!
            timeout : None or float
              | Optional: timeout fetches after N seconds
              | Default: 10 seconds
            raise_errors : bool
                If True, then raise errors as Exceptions instead of logging.
        """
        logger = utils.get_yf_logger()

        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=5)
            self._data._set_proxy(proxy)

        interval_user = interval
        period_user = period
        if repair and interval in ["5d", "1wk", "1mo", "3mo"]:
            # Yahoo's way of adjusting mutiday intervals is fundamentally broken.
            # Have to fetch 1d, adjust, then resample.
            if interval == '5d':
                raise Exception("Yahoo's interval '5d' is nonsense, not supported with repair")
            if start is None and end is None and period is not None:
                tz = self.tz
                if tz is None:
                    # Every valid ticker has a timezone. A missing timezone is a problem.
                    _exception = YFTzMissingError(self.ticker)
                    err_msg = str(_exception)
                    shared._DFS[self.ticker] = utils.empty_df()
                    shared._ERRORS[self.ticker] = err_msg.split(': ', 1)[1]
                    if raise_errors:
                        raise _exception
                    else:
                        logger.error(err_msg)
                    return utils.empty_df()
                if period == 'ytd':
                    start = _datetime.date(pd.Timestamp.utcnow().tz_convert(tz).year, 1, 1)
                else:
                    start = pd.Timestamp.utcnow().tz_convert(tz).date()
                    start -= utils._interval_to_timedelta(period)
                    start -= _datetime.timedelta(days=4)
                period_user = period
                period = None
            interval = '1d'

        start_user = start
        end_user = end
        if start or end or (period and period.lower() == "max"):
            # Check can get TZ. Fail => probably delisted
            tz = self.tz
            if tz is None:
                # Every valid ticker has a timezone. A missing timezone is a problem.
                _exception = YFTzMissingError(self.ticker)
                err_msg = str(_exception)
                shared._DFS[self.ticker] = utils.empty_df()
                shared._ERRORS[self.ticker] = err_msg.split(': ', 1)[1]
                if raise_errors:
                    raise _exception
                else:
                    logger.error(err_msg)
                return utils.empty_df()

        if start:
            start_dt = utils._parse_user_dt(start, tz)
            start = int(start_dt.timestamp())
        if end:
            end_dt = utils._parse_user_dt(end, tz)
            end = int(end_dt.timestamp())

        if period is None:
            if not (start or end):
                period = '1mo'  # default
            elif not start:
                start_dt = end_dt - utils._interval_to_timedelta('1mo')
                start = int(start_dt.timestamp())
            elif not end:
                end_dt = pd.Timestamp.utcnow().tz_convert(tz)
                end = int(end_dt.timestamp())
        else:
            if period.lower() == "max":
                if end is None:
                    end = int(_time.time())
                if start is None:
                    if interval == "1m":
                        start = end - 691200  # 8 days
                    elif interval in ("2m", "5m", "15m", "30m", "90m"):
                        start = end - 5184000  # 60 days
                    elif interval in ("1h", "60m"):
                        start = end - 63072000  # 730 days
                    else:
                        start = end - 3122064000  # 99 years
                    start += 5 # allow for processing time
            elif start and end:
                raise ValueError("Setting period, start and end is nonsense. Set maximum 2 of them.")
            elif start or end:
                period_td = utils._interval_to_timedelta(period)
                if end is None:
                    end_dt = start_dt + period_td
                    end = int(end_dt.timestamp())
                if start is None:
                    start_dt = end_dt - period_td
                    start = int(start_dt.timestamp())
                period = None

        if start or end:
            params = {"period1": start, "period2": end}
        else:
            period = period.lower()
            params = {"range": period}

        params["interval"] = interval.lower()
        params["includePrePost"] = prepost

        # 1) fix weird bug with Yahoo! - returning 60m for 30m bars
        if params["interval"] == "30m":
            params["interval"] = "15m"

        # if the ticker is MUTUALFUND or ETF, then get capitalGains events
        params["events"] = "div,splits,capitalGains"

        params_pretty = dict(params)
        tz = self.tz
        for k in ["period1", "period2"]:
            if k in params_pretty:
                params_pretty[k] = str(pd.Timestamp(params[k], unit='s').tz_localize("UTC").tz_convert(tz))
        logger.debug(f'{self.ticker}: Yahoo GET parameters: {str(params_pretty)}')

        # Getting data from json
        url = f"{_BASE_URL_}/v8/finance/chart/{self.ticker}"
        data = None
        get_fn = self._data.get
        if end is not None:
            end_dt = pd.Timestamp(end, unit='s').tz_localize("UTC")
            dt_now = pd.Timestamp.utcnow()
            data_delay = _datetime.timedelta(minutes=30)
            if end_dt + data_delay <= dt_now:
                # Date range in past so safe to fetch through cache:
                get_fn = self._data.cache_get
        try:
            data = get_fn(
                url=url,
                params=params,
                timeout=timeout
            )
            if "Will be right back" in data.text or data is None:
                raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***\n"
                                   "Our engineers are working quickly to resolve "
                                   "the issue. Thank you for your patience.")

            data = data.json()
        # Special case for rate limits
        except YFRateLimitError:
            raise
        except Exception:
            if raise_errors:
                raise

        # Store the meta data that gets retrieved simultaneously
        try:
            self._history_metadata = data["chart"]["result"][0]["meta"]
        except Exception:
            self._history_metadata = {}

        intraday = params["interval"][-1] in ("m", 'h')
        _price_data_debug = ''
        if start or period is None or period.lower() == "max":
            _price_data_debug += f' ({params["interval"]} '
            if start_user is not None:
                _price_data_debug += f'{start_user}'
            elif not intraday:
                _price_data_debug += f'{pd.Timestamp(start, unit="s").tz_localize("UTC").tz_convert(tz).date()}'
            else:
                _price_data_debug += f'{pd.Timestamp(start, unit="s").tz_localize("UTC").tz_convert(tz)}'
            _price_data_debug += ' -> '
            if end_user is not None:
                _price_data_debug += f'{end_user})'
            elif not intraday:
                _price_data_debug += f'{pd.Timestamp(end, unit="s").tz_localize("UTC").tz_convert(tz).date()})'
            else:
                _price_data_debug += f'{pd.Timestamp(end, unit="s").tz_localize("UTC").tz_convert(tz)})'
        else:
            _price_data_debug += f' (period={period})'

        fail = False
        if data is None or not isinstance(data, dict):
            _exception = YFPricesMissingError(self.ticker, _price_data_debug)
            fail = True
        elif isinstance(data, dict) and 'status_code' in data:
            _price_data_debug += f"(Yahoo status_code = {data['status_code']})"
            _exception = YFPricesMissingError(self.ticker, _price_data_debug)
            fail = True
        elif "chart" in data and data["chart"]["error"]:
            _price_data_debug += ' (Yahoo error = "' + data["chart"]["error"]["description"] + '")'
            _exception = YFPricesMissingError(self.ticker, _price_data_debug)
            fail = True
        elif "chart" not in data or data["chart"]["result"] is None or not data["chart"]["result"] or not data["chart"]["result"][0]["indicators"]["quote"][0]:
            _exception = YFPricesMissingError(self.ticker, _price_data_debug)
            fail = True
        elif period and period not in self._history_metadata['validRanges'] and not utils.is_valid_period_format(period):
            # User provided a bad period
            _exception = YFInvalidPeriodError(self.ticker, period, ", ".join(self._history_metadata['validRanges']))
            fail = True

        if fail:
            err_msg = str(_exception)
            shared._DFS[self.ticker] = utils.empty_df()
            shared._ERRORS[self.ticker] = err_msg.split(': ', 1)[1]
            if raise_errors:
                raise _exception
            else:
                logger.error(err_msg)
            if self._reconstruct_start_interval is not None and self._reconstruct_start_interval == interval:
                self._reconstruct_start_interval = None
            return utils.empty_df()

        # Select useful info from metadata
        quote_type = self._history_metadata["instrumentType"]
        expect_capital_gains = quote_type in ('MUTUALFUND', 'ETF')
        tz_exchange = self._history_metadata["exchangeTimezoneName"]
        currency = self._history_metadata["currency"]

        # Process custom periods
        if period and period not in self._history_metadata.get("validRanges", []):
            end = int(_time.time())
            end_dt = pd.Timestamp(end, unit='s').tz_localize("UTC")
            start = _datetime.date.fromtimestamp(end)
            start -= utils._interval_to_timedelta(period)
            start -= _datetime.timedelta(days=4)

        # parse quotes
        quotes = utils.parse_quotes(data["chart"]["result"][0])
        # Yahoo bug fix - it often appends latest price even if after end date
        if end and not quotes.empty:
            if quotes.index[-1] >= end_dt.tz_convert('UTC').tz_localize(None):
                quotes = quotes.drop(quotes.index[-1])
        if quotes.empty:
            msg = f'{self.ticker}: yfinance received OHLC data: EMPTY'
        elif len(quotes) == 1:
            msg = f'{self.ticker}: yfinance received OHLC data: {quotes.index[0]} only'
        else:
            msg = f'{self.ticker}: yfinance received OHLC data: {quotes.index[0]} -> {quotes.index[-1]}'
        logger.debug(msg)

        # 2) fix weird bug with Yahoo! - returning 60m for 30m bars
        if interval.lower() == "30m":
            logger.debug(f'{self.ticker}: resampling 30m OHLC from 15m')
            quotes2 = quotes.resample('30min')
            quotes = pd.DataFrame(index=quotes2.last().index, data={
                'Open': quotes2['Open'].first(),
                'High': quotes2['High'].max(),
                'Low': quotes2['Low'].min(),
                'Close': quotes2['Close'].last(),
                'Adj Close': quotes2['Adj Close'].last(),
                'Volume': quotes2['Volume'].sum()
            })
            try:
                quotes['Dividends'] = quotes2['Dividends'].max()
                quotes['Stock Splits'] = quotes2['Stock Splits'].max()
            except Exception:
                pass

        # Note: ordering is important. If you change order, run the tests!
        quotes = utils.set_df_tz(quotes, params["interval"], tz_exchange)
        quotes = utils.fix_Yahoo_dst_issue(quotes, params["interval"])
        intraday = params["interval"][-1] in ("m", 'h')
        if not prepost and intraday and "tradingPeriods" in self._history_metadata:
            tps = self._history_metadata["tradingPeriods"]
            if not isinstance(tps, pd.DataFrame):
                self._history_metadata = utils.format_history_metadata(self._history_metadata, tradingPeriodsOnly=True)
                self._history_metadata_formatted = True
                tps = self._history_metadata["tradingPeriods"]
            quotes = utils.fix_Yahoo_returning_prepost_unrequested(quotes, params["interval"], tps)
        if quotes.empty:
            msg = f'{self.ticker}: OHLC after cleaning: EMPTY'
        elif len(quotes) == 1:
            msg = f'{self.ticker}: OHLC after cleaning: {quotes.index[0]} only'
        else:
            msg = f'{self.ticker}: OHLC after cleaning: {quotes.index[0]} -> {quotes.index[-1]}'
        logger.debug(msg)

        # actions
        dividends, splits, capital_gains = utils.parse_actions(data["chart"]["result"][0])
        if not expect_capital_gains:
            capital_gains = None

        if splits is not None:
            splits = utils.set_df_tz(splits, interval, tz_exchange)
        if dividends is not None:
            dividends = utils.set_df_tz(dividends, interval, tz_exchange)
            if 'currency' in dividends.columns:
                # Rare, only seen with Vietnam market
                price_currency = self._history_metadata['currency']
                if price_currency is None:
                    price_currency = ''
                f_currency_mismatch = dividends['currency'] != price_currency
                if f_currency_mismatch.any():
                    if not repair or price_currency == '':
                        # Append currencies to values, let user decide action.
                        dividends['Dividends'] = dividends['Dividends'].astype(str) + ' ' + dividends['currency']
                    else:
                        # Attempt repair = currency conversion
                        dividends = self._dividends_convert_fx(dividends, price_currency, repair)
                        if (dividends['currency'] != price_currency).any():
                            # FX conversion failed
                            dividends['Dividends'] = dividends['Dividends'].astype(str) + ' ' + dividends['currency']
                dividends = dividends.drop('currency', axis=1)

        if capital_gains is not None:
            capital_gains = utils.set_df_tz(capital_gains, interval, tz_exchange)
        if start is not None:
            if not quotes.empty:
                start_d = quotes.index[0].floor('D')
                if dividends is not None:
                    dividends = dividends.loc[start_d:]
                if capital_gains is not None:
                    capital_gains = capital_gains.loc[start_d:]
                if splits is not None:
                    splits = splits.loc[start_d:]
        if end is not None:
            # -1 because date-slice end is inclusive
            end_dt_sub1 = end_dt - pd.Timedelta(1)
            if dividends is not None:
                dividends = dividends[:end_dt_sub1]
            if capital_gains is not None:
                capital_gains = capital_gains[:end_dt_sub1]
            if splits is not None:
                splits = splits[:end_dt_sub1]

        # Prepare for combine
        intraday = params["interval"][-1] in ("m", 'h')
        if not intraday:
            # If localizing a midnight during DST transition hour when clocks roll back,
            # meaning clock hits midnight twice, then use the 2nd (ambiguous=True)
            quotes.index = pd.to_datetime(quotes.index.date).tz_localize(tz_exchange, ambiguous=True, nonexistent='shift_forward')
            if dividends.shape[0] > 0:
                dividends.index = pd.to_datetime(dividends.index.date).tz_localize(tz_exchange, ambiguous=True, nonexistent='shift_forward')
            if splits.shape[0] > 0:
                splits.index = pd.to_datetime(splits.index.date).tz_localize(tz_exchange, ambiguous=True, nonexistent='shift_forward')

        # Combine
        df = quotes.sort_index()
        if dividends.shape[0] > 0:
            df = utils.safe_merge_dfs(df, dividends, interval)
        if "Dividends" in df.columns:
            df.loc[df["Dividends"].isna(), "Dividends"] = 0
        else:
            df["Dividends"] = 0.0
        if splits.shape[0] > 0:
            df = utils.safe_merge_dfs(df, splits, interval)
        if "Stock Splits" in df.columns:
            df.loc[df["Stock Splits"].isna(), "Stock Splits"] = 0
        else:
            df["Stock Splits"] = 0.0
        if expect_capital_gains:
            if capital_gains.shape[0] > 0:
                df = utils.safe_merge_dfs(df, capital_gains, interval)
            if "Capital Gains" in df.columns:
                df.loc[df["Capital Gains"].isna(), "Capital Gains"] = 0
            else:
                df["Capital Gains"] = 0.0
        if df.empty:
            msg = f'{self.ticker}: OHLC after combining events: EMPTY'
        elif len(df) == 1:
            msg = f'{self.ticker}: OHLC after combining events: {df.index[0]} only'
        else:
            msg = f'{self.ticker}: OHLC after combining events: {df.index[0]} -> {df.index[-1]}'
        logger.debug(msg)

        df, last_trade = utils.fix_Yahoo_returning_live_separate(df, params["interval"], tz_exchange, prepost, repair=repair, currency=currency)
        if last_trade is not None:
            self._history_metadata['lastTrade'] = {'Price':last_trade['Close'], "Time":last_trade.name}

        df = df[~df.index.duplicated(keep='first')]  # must do before repair

        if repair:
            # Do this before auto/back adjust
            logger.debug(f'{self.ticker}: checking OHLC for repairs ...')

            df = df.sort_index()

            # Must fix bad 'Adj Close' & dividends before 100x/split errors.
            # First make currency consistent. On some exchanges, dividends often in different currency
            # to prices, e.g. £ vs pence.
            df, currency = self._standardise_currency(df, currency)
            self._history_metadata['currency'] = currency

            df = self._fix_bad_div_adjust(df, interval, currency)

            # Need the latest/last row to be repaired before 100x/split repair:
            if not df.empty:
                df_last = self._fix_zeroes(df.iloc[-1:], interval, tz_exchange, prepost)
                if 'Repaired?' not in df.columns:
                    df['Repaired?'] = False
                df = pd.concat([df.drop(df.index[-1]), df_last])

            df = self._fix_unit_mixups(df, interval, tz_exchange, prepost)
            df = self._fix_bad_stock_splits(df, interval, tz_exchange)
            # Must repair 100x and split errors before price reconstruction
            df = self._fix_zeroes(df, interval, tz_exchange, prepost)
            df = df.sort_index()

        # Auto/back adjust
        try:
            if auto_adjust:
                df = utils.auto_adjust(df)
            elif back_adjust:
                df = utils.back_adjust(df)
        except Exception as e:
            if auto_adjust:
                err_msg = "auto_adjust failed with %s" % e
            else:
                err_msg = "back_adjust failed with %s" % e
            shared._DFS[self.ticker] = utils.empty_df()
            shared._ERRORS[self.ticker] = err_msg
            if raise_errors:
                raise Exception('%s: %s' % (self.ticker, err_msg))
            else:
                logger.error('%s: %s' % (self.ticker, err_msg))

        if rounding:
            df = np.round(df, data["chart"]["result"][0]["meta"]["priceHint"])
        df['Volume'] = df['Volume'].fillna(0).astype(np.int64)

        if intraday:
            df.index.name = "Datetime"
        else:
            df.index.name = "Date"

        # missing rows cleanup
        if not actions:
            df = df.drop(columns=["Dividends", "Stock Splits", "Capital Gains"], errors='ignore')
        if not keepna:
            data_colnames = _PRICE_COLNAMES_ + ['Volume'] + ['Dividends', 'Stock Splits', 'Capital Gains']
            data_colnames = [c for c in data_colnames if c in df.columns]
            mask_nan_or_zero = (df[data_colnames].isna() | (df[data_colnames] == 0)).all(axis=1)
            df = df.drop(mask_nan_or_zero.index[mask_nan_or_zero])

        if interval != interval_user:
            df = self._resample(df, interval, interval_user, period_user)

        if df.empty:
            msg = f'{self.ticker}: yfinance returning OHLC: EMPTY'
        elif len(df) == 1:
            msg = f'{self.ticker}: yfinance returning OHLC: {df.index[0]} only'
        else:
            msg = f'{self.ticker}: yfinance returning OHLC: {df.index[0]} -> {df.index[-1]}'
        logger.debug(msg)

        if self._reconstruct_start_interval is not None and self._reconstruct_start_interval == interval:
            self._reconstruct_start_interval = None
        return df

    def _get_history_cache(self, period="max", interval="1d") -> pd.DataFrame:
        cache_key = (interval, period)
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        df = self.history(period=period, interval=interval, prepost=True)
        self._history_cache[cache_key] = df
        return df

    def get_history_metadata(self, proxy=_SENTINEL_) -> dict:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=3)
            self._data._set_proxy(proxy)

        if self._history_metadata is None or 'tradingPeriods' not in self._history_metadata:
            # Request intraday data, because then Yahoo returns exchange schedule (tradingPeriods).
            self._get_history_cache(period="5d", interval="1h")

        if self._history_metadata_formatted is False:
            self._history_metadata = utils.format_history_metadata(self._history_metadata)
            self._history_metadata_formatted = True

        return self._history_metadata

    def get_dividends(self, period="max", proxy=_SENTINEL_) -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=3)
            self._data._set_proxy(proxy)

        df = self._get_history_cache(period=period)
        if "Dividends" in df.columns:
            dividends = df["Dividends"]
            return dividends[dividends != 0]
        return pd.Series()

    def get_capital_gains(self, period="max", proxy=_SENTINEL_) -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=3)
            self._data._set_proxy(proxy)

        df = self._get_history_cache(period=period)
        if "Capital Gains" in df.columns:
            capital_gains = df["Capital Gains"]
            return capital_gains[capital_gains != 0]
        return pd.Series()

    def get_splits(self, period="max", proxy=_SENTINEL_) -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=3)
            self._data._set_proxy(proxy)

        df = self._get_history_cache(period=period)
        if "Stock Splits" in df.columns:
            splits = df["Stock Splits"]
            return splits[splits != 0]
        return pd.Series()

    def get_actions(self, period="max", proxy=_SENTINEL_) -> pd.Series:
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=3)
            self._data._set_proxy(proxy)

        df = self._get_history_cache(period=period)

        action_columns = []
        if "Dividends" in df.columns:
            action_columns.append("Dividends")
        if "Stock Splits" in df.columns:
            action_columns.append("Stock Splits")
        if "Capital Gains" in df.columns:
            action_columns.append("Capital Gains")

        if action_columns:
            actions = df[action_columns]
            return actions[actions != 0].dropna(how='all').fillna(0)
        return pd.Series()

    def _resample(self, df, df_interval, target_interval, period=None) -> pd.DataFrame:
        # resample
        if df_interval == target_interval:
            return df
        offset = None
        if target_interval == '1wk':
            resample_period = 'W-MON'
        elif target_interval == '5d':
            resample_period = '5D'
        elif target_interval == '1mo':
            resample_period = 'MS'
        elif target_interval == '3mo':
            resample_period = 'QS'
            if period == 'ytd':
                align_month = 'JAN'
            else:
                align_month = _datetime.datetime.now().strftime('%b').upper()
            resample_period = f"QS-{align_month}"
        else:
            raise Exception(f"Not implemented resampling to interval '{target_interval}'")
        resample_map = {
            'Open': 'first', 'Low': 'min', 'High': 'max', 'Close': 'last',
            'Volume': 'sum', 'Dividends': 'sum', 'Stock Splits': 'prod'
            }
        if 'Repaired?' in df.columns:
            resample_map['Repaired?'] = 'any'
        if 'Adj Close' in df.columns:
            resample_map['Adj Close'] = resample_map['Close']
        if 'Capital Gains' in df.columns:
            resample_map['Capital Gains'] = 'sum'
        df.loc[df['Stock Splits']==0.0, 'Stock Splits'] = 1.0
        df2 = df.resample(resample_period, label='left', closed='left', offset=offset).agg(resample_map)
        df2.loc[df2['Stock Splits']==1.0, 'Stock Splits'] = 0.0
        return df2

    @utils.log_indent_decorator
    def _reconstruct_intervals_batch(self, df, interval, prepost, tag=-1):
        # Reconstruct values in df using finer-grained price data. Delimiter marks what to reconstruct
        logger = utils.get_yf_logger()
        log_extras = {'yf_cat': 'price-reconstruct', 'yf_interval': interval, 'yf_symbol': self.ticker}

        if not isinstance(df, pd.DataFrame):
            raise Exception("'df' must be a Pandas DataFrame not", type(df))
        if interval == "1m":
            # Can't go smaller than 1m so can't reconstruct
            return df

        if interval[1:] in ['d', 'wk', 'mo']:
            # Interday data always includes pre & post
            prepost = True
            intraday = False
        else:
            intraday = True

        price_cols = [c for c in _PRICE_COLNAMES_ if c in df]
        data_cols = price_cols + ["Volume"]

        # If interval is weekly then can construct with daily. But if smaller intervals then
        # restricted to recent times:
        intervals = ["1wk", "1d", "1h", "30m", "15m", "5m", "2m", "1m"]
        itds = {i: utils._interval_to_timedelta(interval) for i in intervals}
        nexts = {intervals[i]: intervals[i + 1] for i in range(len(intervals) - 1)}
        min_lookbacks = {"1wk": None, "1d": None, "1h": _datetime.timedelta(days=730)}
        for i in ["30m", "15m", "5m", "2m"]:
            min_lookbacks[i] = _datetime.timedelta(days=60)
        min_lookbacks["1m"] = _datetime.timedelta(days=30)
        if interval in nexts:
            sub_interval = nexts[interval]
            td_range = itds[interval]
        else:
            logger.warning(f"Have not implemented price reconstruct for '{interval}' interval. Contact developers")
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df

        # Limit max reconstruction depth to 2:
        if self._reconstruct_start_interval is None:
            self._reconstruct_start_interval = interval
        if interval != self._reconstruct_start_interval and interval != nexts[self._reconstruct_start_interval]:
            msg = "Hit max depth of 2 ('{}'->'{}'->'{}')".format(self._reconstruct_start_interval, nexts[self._reconstruct_start_interval], interval)
            logger.info(msg, extra=log_extras)
            return df

        df = df.sort_index()

        f_repair = df[data_cols].to_numpy() == tag
        f_repair_rows = f_repair.any(axis=1)

        # Ignore old intervals for which Yahoo won't return finer data:
        m = min_lookbacks[sub_interval]
        if m is None:
            min_dt = None
        else:
            m -= _datetime.timedelta(days=1)  # allow space for 1-day padding
            min_dt = pd.Timestamp.utcnow() - m
            min_dt = min_dt.tz_convert(df.index.tz).ceil("D")
        logger.debug(f"min_dt={min_dt} interval={interval} sub_interval={sub_interval}", extra=log_extras)
        if min_dt is not None:
            f_recent = df.index >= min_dt
            f_repair_rows = f_repair_rows & f_recent
            if not f_repair_rows.any():
                msg = f"Too old ({np.sum(f_repair.any(axis=1))} rows tagged)"
                logger.info(msg, extra=log_extras)
                if "Repaired?" not in df.columns:
                    df["Repaired?"] = False
                return df

        dts_to_repair = df.index[f_repair_rows]

        if len(dts_to_repair) == 0:
            logger.debug("Nothing needs repairing (dts_to_repair[] empty)", extra=log_extras)
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df

        df_v2 = df.copy()
        if "Repaired?" not in df_v2.columns:
            df_v2["Repaired?"] = False
        f_good = ~(df[price_cols].isna().any(axis=1))
        f_good = f_good & (df[price_cols].to_numpy() != tag).all(axis=1)
        df_good = df[f_good]

        # Group nearby NaN-intervals together to reduce number of Yahoo fetches
        dts_groups = [[dts_to_repair[0]]]
        # Note on setting max size: have to allow space for adding good data
        if sub_interval == "1mo":
            grp_max_size = _dateutil.relativedelta.relativedelta(years=2)
        elif sub_interval == "1wk":
            grp_max_size = _dateutil.relativedelta.relativedelta(years=2)
        elif sub_interval == "1d":
            grp_max_size = _dateutil.relativedelta.relativedelta(years=2)
        elif sub_interval == "1h":
            grp_max_size = _dateutil.relativedelta.relativedelta(years=1)
        elif sub_interval == "1m":
            grp_max_size = _datetime.timedelta(days=5)  # allow 2 days for buffer below
        else:
            grp_max_size = _datetime.timedelta(days=30)
        logger.debug(f"grp_max_size = {grp_max_size}", extra=log_extras)
        for i in range(1, len(dts_to_repair)):
            dt = dts_to_repair[i]
            if dt.date() < dts_groups[-1][0].date() + grp_max_size:
                dts_groups[-1].append(dt)
            else:
                dts_groups.append([dt])

        logger.debug("Repair groups:", extra=log_extras)
        for g in dts_groups:
            logger.debug(f"- {g[0]} -> {g[-1]}")

        # Add some good data to each group, so can calibrate prices later:
        for i in range(len(dts_groups)):
            g = dts_groups[i]
            g0 = g[0]
            i0 = df_good.index.get_indexer([g0], method="nearest")[0]
            if i0 > 0:
                if (min_dt is None or df_good.index[i0 - 1] >= min_dt) and \
                        ((not intraday) or df_good.index[i0 - 1].date() == g0.date()):
                    i0 -= 1
            gl = g[-1]
            il = df_good.index.get_indexer([gl], method="nearest")[0]
            if il < len(df_good) - 1:
                if (not intraday) or df_good.index[il + 1].date() == gl.date():
                    il += 1
            good_dts = df_good.index[i0:il + 1]
            dts_groups[i] += good_dts.to_list()
            dts_groups[i].sort()

        n_fixed = 0
        for g in dts_groups:
            df_block = df[df.index.isin(g)]
            logger.debug("df_block:\n" + str(df_block))

            start_dt = g[0]
            start_d = start_dt.date()
            reject = False
            if sub_interval == "1h" and (_datetime.date.today() - start_d) > _datetime.timedelta(days=729):
                reject = True
            elif sub_interval in ["30m", "15m"] and (_datetime.date.today() - start_d) > _datetime.timedelta(days=59):
                reject = True
            if reject:
                # Don't bother requesting more price data, Yahoo will reject
                msg = f"Cannot reconstruct block starting {start_dt if intraday else start_d}, too old, Yahoo will reject request for finer-grain data"
                logger.info(msg, extra=log_extras)
                continue

            td_1d = _datetime.timedelta(days=1)
            if interval in "1wk":
                fetch_start = start_d - td_range  # need previous week too
                fetch_end = g[-1].date() + td_range
            elif interval == "1d":
                fetch_start = start_d
                fetch_end = g[-1].date() + td_range
            else:
                fetch_start = g[0]
                fetch_end = g[-1] + td_range

            # The first and last day returned by Yahoo can be slightly wrong, so add buffer:
            fetch_start -= td_1d
            fetch_end += td_1d
            if intraday:
                fetch_start = fetch_start.date()
                fetch_end = fetch_end.date() + td_1d
            if min_dt is not None:
                fetch_start = max(min_dt.date(), fetch_start)
            logger.debug(f"Fetching {sub_interval} prepost={prepost} {fetch_start}->{fetch_end}", extra=log_extras)
            # Temp disable errors printing
            logger = utils.get_yf_logger()
            if hasattr(logger, 'level'):
                # YF's custom indented logger doesn't expose level
                log_level = logger.level
                logger.setLevel(logging.CRITICAL)
            df_fine = self.history(start=fetch_start, end=fetch_end, interval=sub_interval, auto_adjust=False, actions=True, prepost=prepost, repair=True, keepna=True)
            if hasattr(logger, 'level'):
                logger.setLevel(log_level)
            if df_fine is None or df_fine.empty:
                msg = f"Cannot reconstruct block starting {start_dt if intraday else start_d}, too old, Yahoo will reject request for finer-grain data"
                logger.info(msg, extra=log_extras)
                continue
            # Discard the buffer
            df_fine = df_fine.loc[g[0]: g[-1] + itds[sub_interval] - _datetime.timedelta(milliseconds=1)].copy()
            if df_fine.empty:
                msg = f"Cannot reconstruct {interval} block range {start_dt if intraday else start_d}, Yahoo not returning finer-grain data within range"
                logger.info(msg, extra=log_extras)
                continue

            df_fine["ctr"] = 0
            if interval == "1wk":
                weekdays = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
                week_end_day = weekdays[(df_block.index[0].weekday() + 7 - 1) % 7]
                df_fine["Week Start"] = df_fine.index.tz_localize(None).to_period("W-" + week_end_day).start_time
                grp_col = "Week Start"
            elif interval == "1d":
                df_fine["Day Start"] = pd.to_datetime(df_fine.index.date)
                grp_col = "Day Start"
            else:
                df_fine.loc[df_fine.index.isin(df_block.index), "ctr"] = 1
                df_fine["intervalID"] = df_fine["ctr"].cumsum()
                df_fine = df_fine.drop("ctr", axis=1)
                grp_col = "intervalID"
            df_fine = df_fine[~df_fine[price_cols + ['Dividends']].isna().all(axis=1)]

            df_fine_grp = df_fine.groupby(grp_col)
            df_new = df_fine_grp.agg(
                Open=("Open", "first"),
                Close=("Close", "last"),
                AdjClose=("Adj Close", "last"),
                Low=("Low", "min"),
                High=("High", "max"),
                Dividends=("Dividends", "sum"),
                Volume=("Volume", "sum")).rename(columns={"AdjClose": "Adj Close"})
            if grp_col in ["Week Start", "Day Start"]:
                df_new.index = df_new.index.tz_localize(df_fine.index.tz)
            else:
                df_fine["diff"] = df_fine["intervalID"].diff()
                new_index = np.append([df_fine.index[0]], df_fine.index[df_fine["intervalID"].diff() > 0])
                df_new.index = new_index
            logger.debug('df_new:' + '\n' + str(df_new))

            # Calibrate!
            common_index = np.intersect1d(df_block.index, df_new.index)
            if len(common_index) == 0:
                # Can't calibrate so don't attempt repair
                msg = f"Can't calibrate {interval} block starting {start_d} so aborting repair"
                logger.info(msg, extra=log_extras)
                continue
            # First, attempt to calibrate the 'Adj Close' column. OK if cannot.
            # Only necessary for 1d interval, because the 1h data is not div-adjusted.
            if interval == '1d':
                df_new_calib = df_new[df_new.index.isin(common_index)]
                df_block_calib = df_block[df_block.index.isin(common_index)]
                f_tag = df_block_calib['Adj Close'] == tag
                if f_tag.any():
                    div_adjusts = df_block_calib['Adj Close'] / df_block_calib['Close']
                    # The loop below assumes each 1d repair is isolated, i.e. surrounded by
                    # good data. Which is case most of time.
                    # But in case are repairing a chunk of bad 1d data, back/forward-fill the
                    # good div-adjustments - not perfect, but a good backup.
                    div_adjusts[f_tag] = np.nan
                    if not div_adjusts.isna().all():
                        # Need some real values to calibrate
                        div_adjusts = div_adjusts.ffill().bfill()
                        for idx in np.where(f_tag)[0]:
                            dt = df_new_calib.index[idx]
                            n = len(div_adjusts)
                            if df_new.loc[dt, "Dividends"] != 0:
                                if idx < n - 1:
                                    # Easy, take div-adjustment from next-day
                                    div_adjusts.iloc[idx] = div_adjusts.iloc[idx + 1]
                                else:
                                    # Take previous-day div-adjustment and reverse todays adjustment
                                    div_adj = 1.0 - df_new_calib["Dividends"].iloc[idx] / df_new_calib['Close'].iloc[
                                        idx - 1]
                                    div_adjusts.iloc[idx] = div_adjusts.iloc[idx - 1] / div_adj
                            else:
                                if idx > 0:
                                    # Easy, take div-adjustment from previous-day
                                    div_adjusts.iloc[idx] = div_adjusts.iloc[idx - 1]
                                else:
                                    # Must take next-day div-adjustment
                                    div_adjusts.iloc[idx] = div_adjusts.iloc[idx + 1]
                                    if df_new_calib["Dividends"].iloc[idx + 1] != 0:
                                        div_adjusts.iloc[idx] *= 1.0 - df_new_calib["Dividends"].iloc[idx + 1] / \
                                                            df_new_calib['Close'].iloc[idx]
                        f_close_bad = df_block_calib['Close'] == tag
                        div_adjusts = div_adjusts.reindex(df_block.index, fill_value=np.nan).ffill().bfill()
                        df_new['Adj Close'] = df_block['Close'] * div_adjusts
                        if f_close_bad.any():
                            f_close_bad_new = f_close_bad.reindex(df_new.index, fill_value=False)
                            div_adjusts_new = div_adjusts.reindex(df_new.index, fill_value=np.nan).ffill().bfill()
                            div_adjusts_new_np = f_close_bad_new.to_numpy()
                            df_new.loc[div_adjusts_new_np, 'Adj Close'] = df_new['Close'][div_adjusts_new_np] * div_adjusts_new[div_adjusts_new_np]

            # Check whether 'df_fine' has different split-adjustment.
            # If different, then adjust to match 'df'
            calib_cols = ['Open', 'Close']
            df_new_calib = df_new[df_new.index.isin(common_index)][calib_cols].to_numpy()
            df_block_calib = df_block[df_block.index.isin(common_index)][calib_cols].to_numpy()
            calib_filter = (df_block_calib != tag)
            calib_filter = calib_filter & (~np.isnan(df_new_calib))
            if not calib_filter.any():
                # Can't calibrate so don't attempt repair
                logger.info(f"Can't calibrate block starting {start_d} so aborting repair", extra=log_extras)
                continue
            # Avoid divide-by-zero warnings:
            for j in range(len(calib_cols)):
                f = ~calib_filter[:, j]
                if f.any():
                    df_block_calib[f, j] = 1
                    df_new_calib[f, j] = 1
            ratios = df_block_calib[calib_filter] / df_new_calib[calib_filter]
            weights = df_fine_grp.size()
            weights.index = df_new.index
            weights = weights[weights.index.isin(common_index)].to_numpy().astype(float)
            weights = weights[:, None]  # transpose
            weights = np.tile(weights, len(calib_cols))  # 1D -> 2D
            weights = weights[calib_filter]  # flatten
            not1 = ~np.isclose(ratios, 1.0, rtol=0.00001)
            if np.sum(not1) == len(calib_cols):
                # Only 1 calibration row in df_new is different to df_block so ignore
                ratio = 1.0
            else:
                ratio = np.average(ratios, weights=weights)
            if abs(ratio/0.0001 -1) < 0.01:
                # ratio almost-equal 0.0001, so looks like Yahoo messed up currency unit.
                # E.g. £ with pence. Can correct it.
                df_block = df_block.copy()
                for c in _PRICE_COLNAMES_:
                    df_v2.loc[df_v2[c]!=tag, c] *= 100
                ratio *= 100
            logger.debug(f"Price calibration ratio (raw) = {ratio:6f}", extra=log_extras)
            ratio_rcp = round(1.0 / ratio, 1)
            ratio = round(ratio, 1)
            if ratio == 1 and ratio_rcp == 1:
                # Good!
                pass
            else:
                if ratio > 1:
                    # data has different split-adjustment than fine-grained data
                    # Adjust fine-grained to match
                    df_new[price_cols] *= ratio
                    df_new["Volume"] /= ratio
                elif ratio_rcp > 1:
                    # data has different split-adjustment than fine-grained data
                    # Adjust fine-grained to match
                    df_new[price_cols] *= 1.0 / ratio_rcp
                    df_new["Volume"] *= ratio_rcp

            # Repair!
            bad_dts = df_block.index[(df_block[price_cols + ["Volume"]] == tag).to_numpy().any(axis=1)]

            no_fine_data_dts = []
            for idx in bad_dts:
                if idx not in df_new.index:
                    # Yahoo didn't return finer-grain data for this interval,
                    # so probably no trading happened.
                    no_fine_data_dts.append(idx)
            if len(no_fine_data_dts) > 0:
                logger.debug("Yahoo didn't return finer-grain data for these intervals: " + str(no_fine_data_dts), extra=log_extras)
            for idx in bad_dts:
                if idx not in df_new.index:
                    # Yahoo didn't return finer-grain data for this interval,
                    # so probably no trading happened.
                    continue
                df_new_row = df_new.loc[idx]

                if interval == "1wk":
                    df_last_week = df_new.iloc[df_new.index.get_loc(idx) - 1]
                    df_fine = df_fine.loc[idx:]

                df_bad_row = df.loc[idx]
                bad_fields = df_bad_row.index[df_bad_row == tag].to_numpy()
                if "High" in bad_fields:
                    df_v2.loc[idx, "High"] = df_new_row["High"]
                if "Low" in bad_fields:
                    df_v2.loc[idx, "Low"] = df_new_row["Low"]
                if "Open" in bad_fields:
                    if interval == "1wk" and idx != df_fine.index[0]:
                        # Exchange closed Monday. In this case, Yahoo sets Open to last week close
                        df_v2.loc[idx, "Open"] = df_last_week["Close"]
                        df_v2.loc[idx, "Low"] = min(df_v2.loc[idx, "Open"], df_v2.loc[idx, "Low"])
                    else:
                        df_v2.loc[idx, "Open"] = df_new_row["Open"]
                if "Close" in bad_fields:
                    df_v2.loc[idx, "Close"] = df_new_row["Close"]
                    # Assume 'Adj Close' also corrupted, easier than detecting whether true
                    df_v2.loc[idx, "Adj Close"] = df_new_row["Adj Close"]
                elif "Adj Close" in bad_fields:
                    df_v2.loc[idx, "Adj Close"] = df_new_row["Adj Close"]
                if "Volume" in bad_fields:
                    df_v2.loc[idx, "Volume"] = df_new_row["Volume"].round().astype('int')
                df_v2.loc[idx, "Repaired?"] = True
                n_fixed += 1

            # Not logging these reconstructions - that's job of calling function as it has context.

        return df_v2

    def _standardise_currency(self, df, currency):
        if currency not in ["GBp", "ZAc", "ILA"]:
            return df, currency
        currency2 = currency
        if currency == 'GBp':
            # UK £/pence
            currency2 = 'GBP'
            m = 0.01
        elif currency == 'ZAc':
            # South Africa Rand/cents
            currency2 = 'ZAR'
            m = 0.01
        elif currency == 'ILA':
            # Israel Shekels/Agora
            currency2 = 'ILS'
            m = 0.01

        # Use latest row with actual volume, because volume=0 rows can be 0.01x the other rows.
        # _fix_unit_switch() will ensure all rows are on same scale.
        f_volume = df['Volume']>0
        if not f_volume.any():
            return df, currency
        last_row = df.iloc[np.where(f_volume)[0][-1]]
        prices_in_subunits = True  # usually is true
        if last_row.name > (pd.Timestamp.utcnow() - _datetime.timedelta(days=30)):
            try:
                ratio = self._history_metadata['regularMarketPrice'] / last_row['Close']
                if abs((ratio*m)-1) < 0.1:
                    # within 10% of 100x
                    prices_in_subunits = False
            except Exception:
                # Should never happen but just-in-case
                pass
        if prices_in_subunits:
            for c in _PRICE_COLNAMES_:
                df[c] *= m
        self._history_metadata["currency"] = currency2

        f_div = df['Dividends']!=0.0
        if f_div.any():
            # But sometimes the dividend was in pence.
            # Heuristic is: if dividend yield is ridiculous high vs converted prices, then
            # assume dividend was also in pence and convert to GBP.
            # Threshold for "ridiculous" based on largest yield I've seen anywhere - 63.4%
            # If this simple heuristic generates a false positive, then _fix_bad_div_adjust()
            # will detect and repair.
            divs = df[['Close','Dividends']].copy()
            divs['Close'] = divs['Close'].ffill().shift(1, fill_value=divs['Close'].iloc[0])
            divs = divs[f_div]
            div_pcts = (divs['Dividends'] / divs['Close']).to_numpy()
            if len(div_pcts) > 0 and np.average(div_pcts) > 1:
                df['Dividends'] *= m

        return df, currency2

    def _dividends_convert_fx(self, dividends, fx, repair=False):
        bad_div_currencies = [c for c in dividends['currency'].unique() if c != fx]
        major_currencies = ['USD', 'JPY', 'EUR', 'CNY', 'GBP', 'CAD']
        for c in bad_div_currencies:
            fx2_tkr = None
            if c == 'USD':
                # Simple convert from USD to target FX
                fx_tkr = f'{fx}=X'
                reverse = False
            elif fx == 'USD':
                # Use same USD FX but reversed
                fx_tkr = f'{fx}=X'
                reverse = True
            elif c in major_currencies and fx in major_currencies:
                # Simple convert
                fx_tkr = f'{c}{fx}=X'
                reverse = False
            else:
                # No guarantee that Yahoo has direct FX conversion, so
                # convert via USD
                # - step 1: -> USD
                fx_tkr = f'{c}=X'
                reverse = True
                # - step 2: USD -> FX
                fx2_tkr = f'{fx}=X'

            fx_dat = PriceHistory(self._data, fx_tkr, self.session)
            fx_rate = fx_dat.history(period='1mo', repair=repair)['Close'].iloc[-1]
            if reverse:
                fx_rate = 1/fx_rate
            dividends.loc[dividends['currency']==c, 'Dividends'] *= fx_rate
            if fx2_tkr is not None:
                fx2_dat = PriceHistory(self._data, fx2_tkr, self.session)
                fx2_rate = fx2_dat.history(period='1mo', repair=repair)['Close'].iloc[-1]
                dividends.loc[dividends['currency']==c, 'Dividends'] *= fx2_rate

        dividends['currency'] = fx
        return dividends

    @utils.log_indent_decorator
    def _fix_unit_mixups(self, df, interval, tz_exchange, prepost):
        if df.empty:
            return df
        df2 = self._fix_unit_switch(df, interval, tz_exchange)
        df3 = self._fix_unit_random_mixups(df2, interval, tz_exchange, prepost)
        return df3

    @utils.log_indent_decorator
    def _fix_unit_random_mixups(self, df, interval, tz_exchange, prepost):
        # Sometimes Yahoo returns few prices in cents/pence instead of $/£
        # I.e. 100x bigger
        # 2 ways this manifests:
        # - random 100x errors spread throughout table
        # - a sudden switch between $<->cents at some date
        # This function fixes the first.

        if df.empty:
            return df

        # Easy to detect and fix, just look for outliers = ~100x local median
        logger = utils.get_yf_logger()
        log_extras = {'yf_cat': 'price-repair-100x', 'yf_interval': interval, 'yf_symbol': self.ticker}

        if df.shape[0] == 0:
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df
        if df.shape[0] == 1:
            # Need multiple rows to confidently identify outliers
            logger.debug("Cannot check single-row table for 100x price errors", extra=log_extras)
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df

        df2 = df.copy()

        if df2.index.tz is None:
            df2.index = df2.index.tz_localize(tz_exchange)
        elif df2.index.tz != tz_exchange:
            df2.index = df2.index.tz_convert(tz_exchange)

        # Only import scipy if users actually want function. To avoid
        # adding it to dependencies.
        from scipy import ndimage as _ndimage

        data_cols = ["High", "Open", "Low", "Close", "Adj Close"]  # Order important, separate High from Low
        data_cols = [c for c in data_cols if c in df2.columns]
        f_zeroes = (df2[data_cols] == 0).any(axis=1).to_numpy()
        if f_zeroes.any():
            df2_zeroes = df2[f_zeroes]
            df2 = df2[~f_zeroes]
            df_orig = df[~f_zeroes]  # all row slicing must be applied to both df and df2
        else:
            df2_zeroes = None
            df_orig = df
        if df2.shape[0] <= 1:
            logger.info("Insufficient good data for detecting 100x price errors", extra=log_extras)
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df
        df2_data = df2[data_cols].to_numpy()
        median = _ndimage.median_filter(df2_data, size=(3, 3), mode="wrap")
        ratio = df2_data / median
        ratio_rounded = (ratio / 20).round() * 20  # round ratio to nearest 20
        f = ratio_rounded == 100
        ratio_rcp = 1.0/ratio
        ratio_rcp_rounded = (ratio_rcp / 20).round() * 20  # round ratio to nearest 20
        f_rcp = (ratio_rounded == 100) | (ratio_rcp_rounded == 100)
        f_either = f | f_rcp
        if not f_either.any():
            logger.debug("No sporadic 100x errors", extra=log_extras)
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df

        # Mark values to send for repair
        tag = -1.0
        for i in range(len(data_cols)):
            fi = f_either[:, i]
            c = data_cols[i]
            df2.loc[fi, c] = tag

        n_before = (df2_data == tag).sum()
        df2 = self._reconstruct_intervals_batch(df2, interval, prepost, tag)
        df2_tagged = df2[data_cols].to_numpy() == tag
        n_after = (df2[data_cols].to_numpy() == tag).sum()

        if n_after > 0:
            # This second pass will *crudely* "fix" any remaining errors in High/Low
            # simply by ensuring they don't contradict e.g. Low = 100x High.
            f = (df2[data_cols].to_numpy() == tag) & f
            for i in range(f.shape[0]):
                fi = f[i, :]
                if not fi.any():
                    continue
                idx = df2.index[i]

                for c in ['Open', 'Close']:
                    j = data_cols.index(c)
                    if fi[j]:
                        df2.loc[idx, c] = df.loc[idx, c] * 0.01

                c = "High"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df2.loc[idx, ["Open", "Close"]].max()

                c = "Low"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df2.loc[idx, ["Open", "Close"]].min()

            f_rcp = (df2[data_cols].to_numpy() == tag) & f_rcp
            for i in range(f_rcp.shape[0]):
                fi = f_rcp[i, :]
                if not fi.any():
                    continue
                idx = df2.index[i]

                for c in ['Open', 'Close']:
                    j = data_cols.index(c)
                    if fi[j]:
                        df2.loc[idx, c] = df.loc[idx, c] * 100.0

                c = "High"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df2.loc[idx, ["Open", "Close"]].max()

                c = "Low"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df2.loc[idx, ["Open", "Close"]].min()

            df2_tagged = df2[data_cols].to_numpy() == tag
            n_after_crude = df2_tagged.sum()
        else:
            n_after_crude = n_after

        n_fixed = n_before - n_after_crude
        n_fixed_crudely = n_after - n_after_crude
        if n_fixed > 0:
            report_msg = f"fixed {n_fixed}/{n_before} currency unit mixups "
            if n_fixed_crudely > 0:
                report_msg += f"({n_fixed_crudely} crudely)"
            logger.info(report_msg, extra=log_extras)

        # Restore original values where repair failed
        f_either = df2[data_cols].to_numpy() == tag
        for j in range(len(data_cols)):
            fj = f_either[:, j]
            if fj.any():
                c = data_cols[j]
                df2.loc[fj, c] = df_orig.loc[fj, c]
        if df2_zeroes is not None:
            if "Repaired?" not in df2_zeroes.columns:
                df2_zeroes["Repaired?"] = False
            df2 = pd.concat([df2, df2_zeroes]).sort_index()
            df2.index = pd.to_datetime(df2.index)

        return df2

    @utils.log_indent_decorator
    def _fix_unit_switch(self, df, interval, tz_exchange):
        # Sometimes Yahoo returns few prices in cents/pence instead of $/£
        # I.e. 100x bigger
        # 2 ways this manifests:
        # - random 100x errors spread throughout table
        # - a sudden switch between $<->cents at some date
        # This function fixes the second.
        # Eventually Yahoo fixes but could take them 2 weeks.

        if self._history_metadata['currency'] == 'KWF':
            # Kuwaiti Dinar divided into 1000 not 100
            n = 1000
        else:
            n = 100
        return self._fix_prices_sudden_change(df, interval, tz_exchange, n, correct_dividend=True)

    @utils.log_indent_decorator
    def _fix_zeroes(self, df, interval, tz_exchange, prepost):
        # Sometimes Yahoo returns prices=0 or NaN when trades occurred.
        # But most times when prices=0 or NaN returned is because no trades.
        # Impossible to distinguish, so only attempt repair if few or rare.

        if df.empty:
            return df

        logger = utils.get_yf_logger()
        log_extras = {'yf_cat': 'price-repair-zeroes', 'yf_interval': interval, 'yf_symbol': self.ticker}

        intraday = interval[-1] in ("m", 'h')

        df = df.sort_index()  # important!
        df2 = df.copy()

        if df2.index.tz is None:
            df2.index = df2.index.tz_localize(tz_exchange)
        elif df2.index.tz != tz_exchange:
            df2.index = df2.index.tz_convert(tz_exchange)

        price_cols = [c for c in _PRICE_COLNAMES_ if c in df2.columns]
        f_prices_bad = (df2[price_cols] == 0.0) | df2[price_cols].isna()
        df2_reserve = None
        if intraday:
            # Ignore days with >50% intervals containing NaNs
            grp = pd.Series(f_prices_bad.any(axis=1), name="nan").groupby(f_prices_bad.index.date)
            nan_pct = grp.sum() / grp.count()
            dts = nan_pct.index[nan_pct > 0.5]
            f_zero_or_nan_ignore = np.isin(f_prices_bad.index.date, dts)
            df2_reserve = df2[f_zero_or_nan_ignore]
            df2 = df2[~f_zero_or_nan_ignore]
            if df2.empty:
                # No good data
                if 'Repaired?' not in df.columns:
                    df['Repaired?'] = False
                return df
            df2 = df2.copy()
            f_prices_bad = (df2[price_cols] == 0.0) | df2[price_cols].isna()

        f_change = df2["High"].to_numpy() != df2["Low"].to_numpy()
        if self.ticker.endswith("=X"):
            # FX, volume always 0
            f_vol_bad = None
        else:
            f_high_low_good = (~df2["High"].isna().to_numpy()) & (~df2["Low"].isna().to_numpy())
            f_vol_zero = (df2["Volume"] == 0).to_numpy()
            f_vol_bad = f_vol_zero & f_high_low_good & f_change
            # ^ intra-interval price changed without volume, bad

            if not intraday:
                # Interday data: if close changes between intervals with volume=0 then volume is wrong.
                # Possible can repair with intraday, but usually Yahoo does not have the volume.
                close_diff = df2['Close'].diff()
                close_diff.iloc[0] = 0
                close_chg_pct_abs = np.abs(close_diff / df2['Close'])
                f_bad_price_chg = (close_chg_pct_abs > 0.05).to_numpy() & f_vol_zero
                f_vol_bad = f_vol_bad | f_bad_price_chg

        # If stock split occurred, then trading must have happened.
        # I should probably rename the function, because prices aren't zero ...
        if 'Stock Splits' in df2.columns:
            f_split = (df2['Stock Splits'] != 0.0).to_numpy()
            if f_split.any():
                f_change_expected_but_missing = f_split & ~f_change
                if f_change_expected_but_missing.any():
                    f_prices_bad[f_change_expected_but_missing] = True

        # Check whether worth attempting repair
        f_prices_bad = f_prices_bad.to_numpy()
        f_bad_rows = f_prices_bad.any(axis=1)
        if f_vol_bad is not None:
            f_bad_rows = f_bad_rows | f_vol_bad
        if not f_bad_rows.any():
            logger.debug("No price=0 errors to repair", extra=log_extras)
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df
        if f_prices_bad.sum() == len(price_cols) * len(df2):
            # Need some good data to calibrate
            logger.debug("No good data for calibration so cannot fix price=0 bad data", extra=log_extras)
            if "Repaired?" not in df.columns:
                df["Repaired?"] = False
            return df

        data_cols = price_cols + ["Volume"]

        # Mark values to send for repair
        tag = -1.0
        for i in range(len(price_cols)):
            c = price_cols[i]
            df2.loc[f_prices_bad[:, i], c] = tag
        if f_vol_bad is not None:
            df2.loc[f_vol_bad, "Volume"] = tag
        # If volume=0 or NaN for bad prices, then tag volume for repair
        f_vol_zero_or_nan = (df2["Volume"].to_numpy() == 0) | (df2["Volume"].isna().to_numpy())
        df2.loc[f_prices_bad.any(axis=1) & f_vol_zero_or_nan, "Volume"] = tag
        # If volume=0 or NaN but price moved in interval, then tag volume for repair
        df2.loc[f_change & f_vol_zero_or_nan, "Volume"] = tag

        df2_tagged = df2[data_cols].to_numpy() == tag
        n_before = df2_tagged.sum()
        dts_tagged = df2.index[df2_tagged.any(axis=1)]
        df2 = self._reconstruct_intervals_batch(df2, interval, prepost, tag)
        df2_tagged = df2[data_cols].to_numpy() == tag
        n_after = df2_tagged.sum()
        dts_not_repaired = df2.index[df2_tagged.any(axis=1)]
        n_fixed = n_before - n_after
        if n_fixed > 0:
            msg = f"{self.ticker}: fixed {n_fixed}/{n_before} value=0 errors in {interval} price data"
            if n_fixed < 4:
                dts_repaired = sorted(list(set(dts_tagged).difference(dts_not_repaired)))
                msg += f": {dts_repaired}"
            logger.debug(msg, extra=log_extras)

        if df2_reserve is not None:
            if "Repaired?" not in df2_reserve.columns:
                df2_reserve["Repaired?"] = False
            df2 = pd.concat([df2, df2_reserve]).sort_index()

        # Restore original values where repair failed (i.e. remove tag values)
        f = df2[data_cols].to_numpy() == tag
        for j in range(len(data_cols)):
            fj = f[:, j]
            if fj.any():
                c = data_cols[j]
                df2.loc[fj, c] = df.loc[fj, c]

        return df2

    @utils.log_indent_decorator
    def _fix_bad_div_adjust(self, df, interval, currency):
        # Look for dividend issues:
        # - dividend ~100x the Close change (a currency unit mixup)
        # - dividend missing from Adj Close
        # - dividend is in Adj Close but adjustment is too much, or too small

        # Experimental: also detect dividend in wrong currency e.g. $ not Israel Shekels.
        # But only for big FX rates, otherwise false positives from price volatility.

        if df is None or df.empty:
            return df
        if interval in ['1wk', '1mo', '3mo', '1y']:
            return df

        logger = utils.get_yf_logger()
        log_extras = {'yf_cat': 'div-adjust-repair-bad', 'yf_interval': interval, 'yf_symbol': self.ticker}

        f_div = (df["Dividends"] != 0.0).to_numpy()
        if not f_div.any():
            logger.debug('No dividends to check', extra=log_extras)
            return df

        if self._history_metadata['currency'] == 'KWF':
            # Kuwaiti Dinar divided into 1000 not 100
            currency_divide = 1000
        else:
            currency_divide = 100
        div_status_df = None
        too_big_check_threshold = 0.035

        df = df.sort_index()
        df2 = df.copy()
        if 'Repaired?' not in df2.columns:
            df2['Repaired?'] = False
        df_modified = False

        # Split df2 into: nan data, and non-nan data
        f_nan = df2['Close'].isna().to_numpy()
        df2_nan = df2[f_nan].copy()
        df2 = df2[~f_nan].copy()

        f_div = (df2["Dividends"] != 0.0).to_numpy()
        if not f_div.any():
            logger.debug('No dividends to check', extra=log_extras)
            return df
        div_indices = np.where(f_div)[0]

        # Very rarely, the Close (not Adj Close) is already adjusted!
        # Clue is it's often lower than Low. 
        # E.g. ticker MPCC.OL - Oslo exchange data contradicts Yahoo.
        # But sometimes the original data is bad, e.g. LSE sometimes close < low
        # Can attempt to fix:
        fixed_dates = []
        for i in range(len(div_indices)-1, -1, -1):
            div_idx = div_indices[i]
            if div_idx == 0:
                continue
            prices_before = df2.iloc[div_idx-1]
            diff = prices_before['Low'] - prices_before['Close']
            div = df2['Dividends'].iloc[div_idx]
            if diff > 0 and (diff/div-1)<0.01:
                # Close<Low and the difference not bigger than the dividend, 
                # because if diff > dividend then something else caused problem.
                dt_before = df2.index[div_idx-1]
                new_close = prices_before['Close'] + div
                if new_close >= prices_before['Low'] and new_close <= prices_before['High']:
                    df2.loc[dt_before, 'Close'] = new_close
                    adj_after = df2['Adj Close'].iloc[div_idx] / df2['Close'].iloc[div_idx]
                    adj = adj_after * (1.0 - div/df2['Close'].iloc[div_idx-1])
                    df2.loc[dt_before, 'Adj Close'] = df2['Close'].iloc[div_idx-1] * adj
                    df2.loc[dt_before, 'Repaired?'] = True
                    df_modified = True
                    fixed_dates.append(df2.index[div_idx].date())
        if len(fixed_dates) > 0:
            msg = f"Repaired double-adjustment on div days {[str(d) for d in fixed_dates]}"
            logger.info(msg, extra=log_extras)

        # Check dividends if too big/small for the price action
        for i in range(len(div_indices)-1, -1, -1):
            div_idx = div_indices[i]
            dt = df2.index[div_idx]
            div = df2['Dividends'].iloc[div_idx]

            if div_idx == 0:
                continue

            div_pct = div / df2['Close'].iloc[div_idx-1]

            # Check if dividend is 100x market movement.
            div_too_small_improvement_threshold = 1
            # div_too_big_improvement_threshold = 1
            div_too_big_improvement_threshold = 2

            if isclose(df2['Low'].iloc[div_idx], df2['Close'].iloc[div_idx-1]*100, rel_tol = 0.025):
                # Price has jumped ~100x on ex-div day, need to fix immediately.
                drop_c2l = df2['Close'].iloc[div_idx-1]*100 - df2['Low'].iloc[div_idx]
                div_pct = div / (df2['Close'].iloc[div_idx-1]*100)
                true_adjust = 1.0 - div / (df2['Close'].iloc[div_idx-1]*100)
                present_adj = df2['Adj Close'].iloc[div_idx-1] / df2['Close'].iloc[div_idx-1]
                if not isclose(present_adj, true_adjust, rel_tol = 0.025):
                    df2.loc[:dt-_datetime.timedelta(seconds=1), 'Adj Close'] = true_adjust * df2['Close'].loc[:dt-_datetime.timedelta(seconds=1)]
                    df2.loc[:dt-_datetime.timedelta(seconds=1), 'Repaired?'] = True
            elif isclose(df2['Low'].iloc[div_idx], df2['Close'].iloc[div_idx-1]*0.01, rel_tol = 0.025):
                # Price has dropped ~100x on ex-div day, need to fix immediately.
                drop_c2l = df2['Close'].iloc[div_idx-1]*0.01 - df2['Low'].iloc[div_idx]
                div_pct = div / (df2['Close'].iloc[div_idx-1]*0.01)
                true_adjust = 1.0 - div / (df2['Close'].iloc[div_idx-1]*100)
                present_adj = df2['Adj Close'].iloc[div_idx-1] / df2['Close'].iloc[div_idx-1]
                if not isclose(present_adj, true_adjust, rel_tol = 0.025):
                    df2.loc[:dt-_datetime.timedelta(seconds=1), 'Adj Close'] = true_adjust * df2['Close'].loc[:dt-_datetime.timedelta(seconds=1)]
                    df2.loc[:dt-_datetime.timedelta(seconds=1), 'Repaired?'] = True
            else:
                drop_c2l = df2['Close'].iloc[div_idx-1] - df2['Low'].iloc[div_idx]
            drop = drop_c2l
            if div_idx < len(df2)-1:
                # # In low-volume scenarios, the price drop is day after not today.
                # if df2['Close'].iloc[div_idx-1] == df2['Close'].iloc[div_idx] or \
                #    df2['Low'].iloc[div_idx] == df2['High'].iloc[div_idx]:
                #     drop = np.max(df2['Close'].iloc[div_idx-1:div_idx+1].to_numpy() - df2['Low'].iloc[div_idx:div_idx+2].to_numpy())
                # elif df2['Volume'].iloc[div_idx]==0:
                #     if drop == 0.0:
                #         drop = np.max(df2['Close'].iloc[div_idx-1:div_idx+1].to_numpy() - df2['Low'].iloc[div_idx:div_idx+2].to_numpy())
                #
                # Hmm, can I always look ahead 1 day? Catch: increases FP rate of div-too-small for tiny divs.
                # drops = df2['Close'].iloc[div_idx-1:div_idx+1].to_numpy() - df2['Low'].iloc[div_idx:div_idx+2].to_numpy()
                drops = np.array([drop, df2['Close'].iloc[div_idx] - df2['Low'].iloc[div_idx+1]])
                drop_2Dmax = np.max(drops)
            else:
                drops = np.array([drop])
                drop_2Dmax = drop

            if (len(df2)-div_idx) < 4:
                end = min(len(df2), div_idx+4)
                start = max(0, end-8)
            else:
                start = max(0, div_idx-4)
                end = min(len(df2), start+8)
            if end-start < 4:
                # Not enough data to estimate volatility
                typical_volatility = np.nan
            else:
                diffs = df2['Close'].iloc[start:end-1].to_numpy() - df2['Low'].iloc[start+1:end].to_numpy()
                typical_volatility = np.mean(np.abs(diffs))

            possibilities = []
            if (drops==0.0).all() and df2['Volume'].iloc[div_idx]==0:
                # Can't analyse price action so use crude heuristics
                pct_zero_vol = np.sum(df2['Volume']==0.0)/len(df2)
                if div_pct*100 < 0.1:
                    # Could be a 0.01x error
                    possibilities.append({'state':'div-too-small', 'diff':0.0})
                # elif div_pct > 1.0:
                # Update: lower threshold for illiquid stocks, because why paying mega dividends?
                elif (pct_zero_vol > 0.75 and div_pct > 0.25) or (div_pct > 1.0):
                    # Could be a 100x error
                    possibilities.append({'state':'div-too-big', 'diff':0.0})
            else:
                split = df2['Stock Splits'].loc[dt]
                if split == 0.0:
                    div_postSplit = None
                else:
                    # Maybe Yahoo has not applied coincident split to dividend
                    div_postSplit = div / split

                    if div_postSplit > div:
                        # Use volatility-adjusted drop
                        _drop = drop - typical_volatility
                    else:
                        _drop = drop_2Dmax
                    if _drop > 0:
                        diff = abs(div-_drop)
                        diff_postSplit = abs(div_postSplit-_drop)
                        if (diff_postSplit * div_too_big_improvement_threshold) <= diff:
                            possibilities.append({'state':'div-pre-split', 'diff':diff_postSplit})

                # Check for div-too-big
                if div_pct > too_big_check_threshold:
                    if drop_2Dmax <= 0.0:
                        possibilities.append({'state':'div-too-big', 'diff':0.0})
                    else:
                        diff = abs(div-drop_2Dmax)
                        diff_fx = abs((div/currency_divide)-drop_2Dmax)
                        if div_postSplit is None:
                            if (diff_fx * div_too_big_improvement_threshold) <= diff:
                                possibilities.append({'state':'div-too-big', 'diff':diff_fx})
                        else:
                            diff_fxPostSplit = abs((div_postSplit/currency_divide)-drop_2Dmax)
                            if diff_fx < diff_fxPostSplit:
                                if (diff_fx * div_too_big_improvement_threshold) <= diff:
                                    possibilities.append({'state':'div-too-big', 'diff':diff_fx})
                            else:
                                if (diff_fxPostSplit * div_too_big_improvement_threshold) <= diff:
                                    possibilities.append({'state':'div-too-big-and-pre-split', 'diff':diff_fxPostSplit})

                # Check for div-too-small - can be tricked by normal price volatility
                if not np.isnan(typical_volatility):
                    # drop_wo_vol = drop_2Dmax - typical_volatility
                    # Update: only use same-day change for too-small, to reduce false-positives
                    drop_wo_vol = drop - typical_volatility
                    if drop_wo_vol > 0:
                        diff = abs(div-drop_wo_vol)
                        diff_fx = abs((div*currency_divide)-drop_wo_vol)
                        if div_postSplit is None:
                            if (diff_fx * div_too_small_improvement_threshold) <= diff:
                                possibilities.append({'state':'div-too-small', 'diff':diff_fx})
                        else:
                            diff_fxPostSplit = abs((div_postSplit*currency_divide)-drop_wo_vol)
                            if diff_fx < diff_fxPostSplit:
                                if (diff_fx * div_too_big_improvement_threshold) <= diff:
                                    possibilities.append({'state':'div-too-small', 'diff':diff_fx})
                            else:
                                if (diff_fxPostSplit * div_too_big_improvement_threshold) <= diff:
                                    possibilities.append({'state':'div-too-small-and-pre-split', 'diff':diff_fxPostSplit})

            div_status = {'date': dt, 'idx':div_idx, 'div': div, '%': div_pct}
            div_status['drop'] = drop
            div_status['drop_2Dmax'] = drop_2Dmax
            div_status['volume'] = df2['Volume'].iloc[div_idx]
            div_status['vol'] = typical_volatility

            div_status['div_too_big'] = False
            div_status['div_too_small'] = False
            div_status['div_pre_split'] = False
            div_status['div_too_big_and_pre_split'] = False
            div_status['div_too_small_and_pre_split'] = False
            if len(possibilities) > 0:
                # Something is wrong with dividend - pick the best correction
                possibilities = sorted(possibilities, key=lambda k: k['diff'])
                p = possibilities[0]
                div_status[p['state'].replace('-', '_')] = True

            row = pd.DataFrame([div_status]).set_index('date')
            if div_status_df is None:
                div_status_df = row
            else:
                div_status_df = pd.concat([div_status_df, row])

        if div_status_df is None and not df_modified:
            return df
        checks = [c for c in div_status_df.columns if c.startswith('div_')]
        div_status_df = div_status_df.sort_index()

        def cluster_dividends(df, column='div', threshold=7):
            n = len(df)
            sorted_df = df.sort_values(column)
            clusters = []
            current_dts = [sorted_df.index[0]]
            currents_vals = [sorted_df[column].iloc[0]]
            for i in range(1, n):
                dt = sorted_df.index[i]
                div = sorted_df[column].iloc[i]
                if (div / np.mean(currents_vals)) < threshold:
                    # Add
                    current_dts.append(dt)
                    currents_vals.append(div)
                else:
                    # New cluster
                    clusters.append(current_dts)
                    current_dts = [dt]
                    currents_vals = [div]
            clusters.append(current_dts)

            cluster_labels = np.array([-1]*n)
            ctr = 0
            for i, cluster in enumerate(clusters):
                nc = len(cluster)
                cluster_labels[ctr:ctr+nc] = i
                ctr += nc
            return cluster_labels

        # Check if the present div-adjustment is too big/small, or missing
        # - too-big determined from Adj Close movement vs Close
        # - too-small compares Adj Close vs dividends
        for i in range(len(div_status_df)):
            div_idx = div_status_df['idx'].iloc[i]
            dt = div_status_df.index[i]
            div = div_status_df['div'].iloc[i]

            if div_idx == 0:
                continue

            div_pct = div / df2['Close'].iloc[div_idx-1]

            # First, check if Yahoo failed to apply dividend to Adj Close
            pre_adj = df2['Adj Close'].iloc[div_idx-1] / df2['Close'].iloc[div_idx-1]
            post_adj = df2['Adj Close'].iloc[div_idx] / df2['Close'].iloc[div_idx]
            div_missing_from_adjclose = post_adj == pre_adj

            # Check if adjustment too small
            present_adj = pre_adj / post_adj
            implied_div_yield = 1.0 - present_adj
            div_adj_is_too_small = implied_div_yield < (0.1*div_pct)

            # ... and use same method for adjustment too big:
            div_adj_exceeds_div = implied_div_yield > (10*div_pct)

            # Can prune the space:
            if div_missing_from_adjclose:
                div_adj_is_too_small = False  # redundant information

            div_status = {'present adj': present_adj}
            div_status['adj_missing'] = div_missing_from_adjclose
            div_status['adj_exceeds_div'] = div_adj_exceeds_div
            div_status['div_exceeds_adj'] = div_adj_is_too_small

            for k,v in div_status.items():
                if k not in div_status_df:
                    if isinstance(v, (bool, np.bool_)):
                        div_status_df[k] = False
                    elif isinstance(v, int):
                        div_status_df[k] = 0
                    elif isinstance(v, float):
                        div_status_df[k] = 0.0
                    # elif k == 'div_true_date':
                    #     div_status_df[k] = pd.Series(dtype='datetime64[ns, UTC]')
                    else:
                        raise Exception(k,v,type(v))
                div_status_df.loc[dt, k] = v
        checks += ['adj_missing', 'adj_exceeds_div', 'div_exceeds_adj']

        div_status_df['phantom'] = False
        phantom_proximity_threshold = _datetime.timedelta(days=17)
        f = div_status_df[['div_too_big', 'div_exceeds_adj']].any(axis=1)
        if f.any() and len(div_status_df) > 1:
            # One/some of these may be phantom dividends. Clue is if another correct dividend is very close
            indices = np.where(f)[0]
            dts_to_check = div_status_df.index[f]
            for i in indices:
                div = div_status_df.iloc[i]
                div_dt = div.name
                phantom_dt = None
                if i > 0:
                    other_div = div_status_df.iloc[i-1]
                else:
                    other_div = div_status_df.iloc[i+1]
                ratio1 = (div['div']/currency_divide) / other_div['div']
                ratio2 = div['div'] / other_div['div']
                divergence = min(abs(ratio1-1.0), abs(ratio2-1.0))
                if abs(div_dt-other_div.name) <= phantom_proximity_threshold and not other_div['phantom'] and divergence < 0.01:
                    if other_div.name in dts_to_check:
                        # Both this and previous are anomalous, so mark smallest drop as phantom
                        drop = div['drop']
                        drop_next = other_div['drop']
                        if drop > 1.5*drop_next:
                            phantom_dt = other_div.name
                        else:
                            phantom_dt = div_dt
                    else:
                        phantom_dt = div_dt

                if phantom_dt:
                    div_status_df.loc[phantom_dt, 'phantom'] = True
                    for c in checks:
                        if c in div_status_df.columns:
                            div_status_df.loc[phantom_dt, c] = False

        # There might be other phantom dividends - in close proximity and almost-equal to another div.
        # But harder to decide which is the phantom and which is real.
        # Assume phantom has much smaller price drop, otherwise assume is newer.
        # ratio_threshold = 0.01
        ratio_threshold =  0.08  # increased for KAP.IL 2022-July
        div_status_df = div_status_df.sort_index()
        for i in range(1, len(div_status_df)):
            div = div_status_df.iloc[i]
            div_dt = div.name
            this_is_phantom = False
            last_is_phantom = False
            drop = div['drop']
            last_div = div_status_df.iloc[i-1]
            ratio = div['div'] / last_div['div']
            if abs(div_dt-last_div.name) <= phantom_proximity_threshold and not last_div['phantom'] and not div['phantom'] and abs(ratio-1.0) < ratio_threshold:
                last_drop = div_status_df['drop'].iloc[i-1]
                if drop > 1.5*last_drop:
                    last_is_phantom = True
                else:
                    this_is_phantom = True
            if last_is_phantom or this_is_phantom:
                phantom_div_dt = div_dt if this_is_phantom else div_status_df.index[i-1]
                div_status_df.loc[phantom_div_dt, 'phantom'] = True
                for c in checks:
                    if c in div_status_df.columns:
                        div_status_df.loc[phantom_div_dt, c] = False
        checks.append('phantom')

        # Remove phantoms early
        if 'phantom' in div_status_df.columns:
            f_phantom = div_status_df['phantom']
            # ... but only if no other problems
            f_phantom = f_phantom & (~div_status_df[[c for c in checks if c != 'phantom']].any(axis=1))
            if f_phantom.any():
                div_dts = div_status_df.index[f_phantom]
                msg = f'Removing phantom div(s): {[str(dt.date()) for dt in div_dts]}'
                logger.info(msg, extra=log_extras)
                phantom_div_dts = div_status_df.index[f_phantom]
                for dt in phantom_div_dts:
                    enddt = dt-_datetime.timedelta(seconds=1)
                    df2.loc[    :enddt, 'Adj Close'] /= div_status_df['present adj'].loc[dt]
                    df2.loc[    :enddt, 'Repaired?'] = True
                    df2_nan.loc[:enddt, 'Adj Close'] /= div_status_df['present adj'].loc[dt]
                    df2_nan.loc[:enddt, 'Repaired?'] = True
                    df2.loc[dt, 'Dividends'] = 0
                    df_modified = True
                    div_status_df = div_status_df.drop(dt)
                div_status_df.loc[f_phantom, 'phantom'] = False
            div_status_df = div_status_df.drop('phantom', axis=1)
            if 'phantom' in checks:
                checks.remove('phantom')

        if not div_status_df[checks].any().any():
            # Maybe failed to detect a too-small div. If div is ~0.01x of previous and next, then
            # treat as a 0.01x error
            if len(div_status_df) > 1:
                for i in range(0, len(div_status_df)):
                    r_pre, r_post = None, None
                    if i > 0:
                        r_pre = div_status_df['%'].iloc[i-1] / div_status_df['%'].iloc[i]
                    if i < (len(div_status_df)-1):
                        r_post = div_status_df['%'].iloc[i+1] / div_status_df['%'].iloc[i]
                    r_pre = r_pre or r_post
                    r_post = r_post or r_pre
                    if abs(r_pre-currency_divide)<20 and abs(r_post-currency_divide)<20:
                        div_dt = div_status_df.index[i]
                        div_status_df.loc[div_dt, 'div_too_small'] = True

        if not div_status_df[checks].any().any():
            # Perfect
            if df_modified:
                return df2
            else:
                return df

        # Check if the present div-adjustment contradicts price action
        for i in range(len(div_status_df)):
            div_idx = div_status_df['idx'].iloc[i]
            dt = div_status_df.index[i]
            div = div_status_df['div'].iloc[i]
            if div_idx == 0:
                continue
            div_pct = div / df2['Close'].iloc[div_idx-1]

            # Adj Close should drop by LESS than Close on ex-div, at least for big dividends.
            # Update: Yahoo might be reporting dividend slightly early, meaning
            # Mr Market's price drop happens tomorrow e.g. UNTC in december 2023.
            # Or worse, Yahoo is 1 month early e.g. GWI.L ex-div was mid-April not mid-March
            lookahead_date = dt+_datetime.timedelta(days=35)
            lookahead_idx = bisect.bisect_left(df2.index, lookahead_date)
            lookahead_idx = min(lookahead_idx, len(df2)-1)
            # In rare cases, the price dropped 1 day before dividend (DVD.OL @ 2024-05-15)
            lookback_idx = max(0, div_idx-14)
            # Check for bad stock splits in the lookahead period - 
            # if present, reduce lookahead to before.
            future_changes = df2['Close'].iloc[div_idx:lookahead_idx+1].pct_change()
            f_big_change = (future_changes > 2).to_numpy() | (future_changes < -0.9).to_numpy()
            if f_big_change.any():
                lookahead_idx = div_idx + np.where(f_big_change)[0][0]-1
                lookahead_date = df2.index[lookahead_idx]
            
            div_adj_exceeds_prices = False
            div_date_wrong = False
            div_true_date = pd.NaT
            if lookahead_idx > lookback_idx:
                x = df2.iloc[lookback_idx:lookahead_idx+1].copy()
                x['Adj'] = x['Adj Close'] / x['Close']
                x['Adj Low'] = x['Adj'] * x['Low']
                deltas = x['Low'].iloc[1:].to_numpy() - x['Close'].iloc[:-1].to_numpy()
                deltas = np.append([0.0], deltas)
                x['delta'] = deltas
                adjDeltas = x['Adj Low'].iloc[1:].to_numpy() - x['Adj Close'].iloc[:-1].to_numpy()
                adjDeltas = np.append([0.0], adjDeltas)
                x['adjDelta'] = adjDeltas
                deltas = x[['delta', 'adjDelta']]
                if div_pct > 0.05 and div_pct < 1.0:
                    adjDiv = div * x['Adj'].iloc[0]
                    f = deltas['adjDelta'] > (adjDiv*0.6)
                    if f.any():
                        indices = np.where(f)[0]
                        for idx in indices:
                            adjDelta_drop = deltas['adjDelta'].iloc[idx]
                            if adjDelta_drop > 1.001*deltas['delta'].iloc[idx]:
                                # Adjusted price has risen by more than unadjusted, should not happen.
                                # See if Adjusted price later falls by a similar amount. This would mean
                                # dividend has been applied too early.
                                ratios = (-1*deltas['adjDelta'])/adjDelta_drop
                                f_near1_or_above = ratios>=0.8
                                # Update: only check for wrong date if no coincident split.
                                # Because if a split, more likely the div is missing split
                                split = df2['Stock Splits'].loc[dt]
                                pre_split = div_status_df['div_pre_split'].loc[dt]
                                if (split==0.0 or (not pre_split)) and f_near1_or_above.any():
                                    near_indices = np.where(f_near1_or_above)[0]
                                    if len(near_indices) > 1:
                                        penalties = np.zeros(len(near_indices))
                                        for i in range(len(near_indices)):
                                            idx = near_indices[i]
                                            dti = ratios.index[idx]
                                            if dti < dt:
                                                penalties[i] += (dt-dti).days
                                            else:
                                                penalties[i] += 0.1*(dti-dt).days
                                        i = np.argmin(penalties)
                                        reversal_idx = near_indices[i]
                                    else:
                                        reversal_idx = near_indices[0]
                                    div_date_wrong = True
                                    div_true_date = ratios.index[reversal_idx]
                                    break
                                elif adjDelta_drop > 0.39*adjDiv:
                                    # Still true that applied adjustment exceeds price action, 
                                    # just not clear what solution is (if any).
                                    if (x['Adj']<1.0).any():
                                        div_adj_exceeds_prices = True
                                    break

            # Can prune the space:
            div_adj_is_too_small = div_status_df.loc[dt, 'div_exceeds_adj']
            if div_adj_exceeds_prices and div_adj_is_too_small:
                # Contradiction. Assume former tricked by low-liquidity price action
                div_adj_exceeds_prices = False

            div_status = {}
            div_status['adj_exceeds_prices'] = div_adj_exceeds_prices
            div_status['div_date_wrong'] = div_date_wrong
            div_status['div_true_date'] = div_true_date

            if div_adj_exceeds_prices:
                split = df2['Stock Splits'].loc[dt]
                if split != 0.0:
                    # Check again if div missing split. Use looser tolerance
                    # as we know the adjustment seems wrong.
                    div_postSplit = div / split
                    if div_postSplit > div:
                        # Use volatility-adjusted drop
                        typical_volatility = div_status_df['vol'].loc[dt]
                        drop = div_status_df['drop'].loc[dt]
                        _drop = drop - typical_volatility
                    else:
                        drop_2Dmax = div_status_df['drop_2Dmax'].loc[dt]
                        _drop = drop_2Dmax
                    if _drop > 0:
                        diff = abs(div-_drop)
                        diff_postSplit = abs(div_postSplit-_drop)
                        if diff_postSplit <= (diff*1.1):
                            # possibilities.append({'state':'div-pre-split', 'diff':diff_postSplit})
                            div_status_df.loc[dt, 'div_pre_split'] = True

            for k,v in div_status.items():
                if k not in div_status_df:
                    if isinstance(v, (bool, np.bool_)):
                        div_status_df[k] = False
                    elif isinstance(v, int):
                        div_status_df[k] = 0
                    elif isinstance(v, float):
                        div_status_df[k] = 0.0
                    elif k == 'div_true_date':
                        div_status_df[k] = pd.Series(dtype='datetime64[ns, UTC]')
                    else:
                        raise Exception(k,v,type(v))
                div_status_df.loc[dt, k] = v
            if 'div_too_big' in div_status_df.columns and 'div_date_wrong' in div_status_df.columns:
                # Where div_date_wrong = True, discard div_too_big. Helps with false-positive handling later.
                div_status_df.loc[div_status_df['div_date_wrong'].to_numpy(), 'div_too_big'] = False

        checks += ['adj_exceeds_prices', 'div_date_wrong']

        for c in checks:
            if not div_status_df[c].any():
                div_status_df = div_status_df.drop(c, axis=1)
        c = 'div_true_date'
        if c in div_status_df.columns and div_status_df[c].isna().all():
            div_status_df = div_status_df.drop(c, axis=1)
        checks = [c for c in checks if c in div_status_df.columns]

        # With small dividends e.g. < 10%, my error detecting logic can be tricked by price volatility.
        # But by looking at all the dividends, can find errors that previous logic missed.

        div_status_df = div_status_df.sort_values('%')
        div_status_df['cluster'] = cluster_dividends(div_status_df, column='%')

        # Check for inconsistencies
        cluster_ids = div_status_df['cluster'].unique()
        for cid in cluster_ids:
            fc = div_status_df['cluster'] == cid
            cluster = div_status_df[fc].sort_index()
            n = len(cluster)
            div_pcts = cluster[['%']].copy()
            if len(div_pcts) > 1:
                time_diffs = div_pcts['%'].index.to_series().diff().dt.total_seconds() / (365.25 * 24 * 60 * 60)
                time_diffs.loc[time_diffs.index[0]] = time_diffs.iloc[1]
                div_pcts['period'] = time_diffs
                div_pcts['avg yr yield'] = div_pcts['%'] / div_pcts['period']

            for c in checks:
                if not cluster[c].to_numpy().any():
                    cluster = cluster.drop(c, axis=1)
            cluster_checks = [c for c in checks if c in cluster.columns]

            for c in cluster_checks:
                f_fail = cluster[c].to_numpy()
                n_fail = np.sum(f_fail)
                if n_fail in [0, n]:
                    continue
                pct_fail = n_fail / n
                if c == 'div_too_big':
                    true_threshold = 1.0
                    fals_threshold = 0.25

                    if 'div_date_wrong' in cluster.columns and (cluster[c] == cluster['div_date_wrong']).all():
                        continue

                    if 'adj_exceeds_prices' in cluster.columns and (cluster[c] == (cluster[c] & cluster['adj_exceeds_prices'])).all():
                        # Treat div_too_big=False as false positives IFF adj_exceeds_prices=true AND 
                        # true ratio above (lowered) threshold.
                        true_threshold = 0.5
                        f_adj_exceeds_prices = cluster['adj_exceeds_prices'].to_numpy()
                        n = np.sum(f_adj_exceeds_prices)
                        n_fail = np.sum(f_fail[f_adj_exceeds_prices])
                        pct_fail = n_fail / n
                        if pct_fail > true_threshold:
                            f = fc & div_status_df['adj_exceeds_prices'].to_numpy()
                            div_status_df.loc[f, c] = True
                        continue

                    if 'div_exceeds_adj' in cluster.columns and cluster['div_exceeds_adj'].all():
                        # Dividend too big for prices AND the present adjustment,
                        # more likely the dividends are too big.
                        if (cluster['vol'][fc][f_fail]==0).all():
                            # No trading volume to cross-check, so higher thresholds
                            fals_threshold = 2/3
                        else:
                            # Relax thresholds
                            true_threshold = 0.25

                    elif 'adj_exceeds_prices' in cluster.columns and (cluster[c]==cluster['adj_exceeds_prices']).all():
                        # Both dividend and present adjust too big for prices,
                        # more likely the dividends are too big.
                        true_threshold = 1/2

                    else:
                        fals_threshold = 1/2

                    if pct_fail >= true_threshold:
                        div_status_df.loc[fc, c] = True
                        if 'div_date_wrong' in div_status_df.columns:
                            # reset this as well
                            div_status_df.loc[fc, 'div_date_wrong'] = False
                            div_status_df.loc[fc, 'div_true_date'] = pd.NaT
                            cluster = div_status_df[fc].sort_index()
                        continue
                    elif pct_fail <= fals_threshold:
                        div_status_df.loc[fc, c] = False
                        continue

                if c == 'div_too_small':
                    true_threshold = 1.0
                    fals_threshold = 0.1
                    if 'adj_exceeds_div' not in cluster.columns:
                        # Adjustment confirms dividends => more likely that 'div_too_small' are false positives: NOT too small
                        true_threshold = 6/11
                        fals_threshold = 1/2
                    if pct_fail >= true_threshold:
                        div_status_df.loc[fc, c] = True
                        continue
                    elif pct_fail <= fals_threshold:
                        div_status_df.loc[fc, c] = False
                        continue

                if c == 'adj_missing':
                    if cluster[c].iloc[-1] and n_fail == 1:
                        # Only the latest/last row is missing, genuine error
                        continue
                if c == 'div_exceeds_adj':
                    continue

                if c == 'adj_exceeds_prices':
                    continue

                if c == 'phantom' and self.ticker in ['KAP.IL', 'SAND']:
                    # Manually approve, but these are probably safe to assume ok
                    continue

                if c == 'div_date_wrong':
                    # Fine, these should be rare
                    continue
                if c in ['div_pre_split', 'div_too_big_and_pre_split']:
                    # Fine, these should be rare
                    continue

        if 'div_too_big' in checks and 'div_exceeds_adj' in checks:
            c = "adj_too_small"
            div_status_df[c] = False
            for i in range(len(div_status_df)):
                dt = div_status_df.index[i]
                row = div_status_df.iloc[i]
                if row['div_too_big'] and row['div_exceeds_adj']:
                    # Check if div_too_big AND adj-too-small-for-prices
                    div_yield = row['div']
                    pct = row['%']
                    close = div_yield/pct
                    adj_present = row['present adj']
                    implied_div_yield = (1-adj_present)*close
                    ratio = div_yield/implied_div_yield
                    also_correct_adj = abs(ratio-(currency_divide*currency_divide)) < currency_divide
                    if also_correct_adj:
                        div_status_df.loc[dt, c] = True
            if not div_status_df[c].any():
                div_status_df = div_status_df.drop(c, axis=1)
            else:
                checks.append(c)

        if 'div_too_big_and_pre_split' in div_status_df.columns:
            for c in ['div_too_big', 'div_pre_split']:
                if c in div_status_df:
                    div_status_df[c] = div_status_df[c] | div_status_df['div_too_big_and_pre_split']
                else:
                    div_status_df[c] = div_status_df['div_too_big_and_pre_split']
                    checks.append(c)
            div_status_df = div_status_df.drop('div_too_big_and_pre_split', axis=1)
            checks.remove('div_too_big_and_pre_split')

        div_status_df = div_status_df.sort_index()

        # Discard dividends with no problems
        div_status_df = div_status_df[div_status_df[checks].any(axis=1)]
        if div_status_df.empty:
            if not df2_nan.empty:
                df2 = pd.concat([df2, df2_nan]).sort_index()
            return df2

        # These arrays track changes for constructing compact log messages
        div_repairs = {}
        for cid in list(div_status_df['cluster'].unique()):
            cluster = div_status_df[div_status_df['cluster']==cid]
            cluster = cluster.sort_index(ascending=False)
            cluster['Fixed?'] = False
            # Reverse order because may delete false-positives
            for i in range(len(cluster)-1, -1, -1):
                row = cluster.iloc[i]
                dt = row.name
                enddt = dt-_datetime.timedelta(seconds=1)

                adj_missing = 'adj_missing' in row and row['adj_missing']
                div_exceeds_adj = 'div_exceeds_adj' in row and row['div_exceeds_adj']
                adj_exceeds_div = 'adj_exceeds_div' in row and row['adj_exceeds_div']
                adj_exceeds_prices = 'adj_exceeds_prices' in row and row['adj_exceeds_prices']
                div_too_small = 'div_too_small' in row and row['div_too_small']
                div_too_big = 'div_too_big' in row and row['div_too_big']
                div_pre_split = 'div_pre_split' in row and row['div_pre_split']
                # div_too_small_and_pre_split = 'div_too_small_and_pre_split' in row and row['div_too_small_and_pre_split']  # not happened yet
                # div_too_big_and_pre_split = 'div_too_big_and_pre_split' in row and row['div_too_big_and_pre_split']  # not happened yet
                div_date_wrong = 'div_date_wrong' in row and row['div_date_wrong']
                adj_too_small = 'adj_too_small' in row and row['adj_too_small']
                n_failed_checks = np.sum([row[c] for c in checks if c in row])

                if div_too_big and adj_exceeds_prices and n_failed_checks == 2:
                    # adj_exceeds_prices is redundant information, fixing div-too-big
                    # will fix adjustment
                    adj_exceeds_prices = False
                    n_failed_checks -= 1

                if div_date_wrong:
                    if div_too_big:
                        # redundant information
                        div_too_big = False
                        cluster.loc[dt, 'div_too_big'] = False
                        n_failed_checks -= 1
                    if div_exceeds_adj:
                        # false-positive
                        div_exceeds_adj = False
                        cluster.loc[dt, 'div_exceeds_adj'] = False
                        n_failed_checks -= 1

                if div_pre_split:
                    if adj_exceeds_prices:
                        # redundant information
                        adj_exceeds_prices = False
                        cluster.loc[dt, 'adj_exceeds_prices'] = False
                        n_failed_checks -= 1

                if n_failed_checks == 1:
                    if div_exceeds_adj or adj_exceeds_div:
                        # Simply recalculate Adj Close
                        k = 'too-small div-adjust' if div_exceeds_adj else 'too-big div-adjust'
                        div_repairs.setdefault(k, []).append(dt)
                        adj_correction = (1.0 - row['%']) / row['present adj']
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True

                    elif div_too_small:
                        # Fix both dividend and adjustment
                        # - div_too_small looks fine, the adj also needs repair because compared against div
                        k = 'too-small div'
                        correction = currency_divide
                        correct_div = row['div'] * correction
                        df2.loc[dt, 'Dividends'] = correct_div
                        # adj is correct *compared to the present div*, so needs rescaling
                        # to match corrected dividend
                        k += ' & div-adjust'
                        target_adj = 1.0 - ((1.0 - row['present adj']) * correction)
                        adj_correction = target_adj / row['present adj']
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True
                        div_repairs.setdefault(k, []).append(dt)

                    elif div_too_big:
                        k = 'too-big div'
                        correction = 1.0/currency_divide

                        correct_div = row['div'] * correction
                        df2.loc[dt, 'Dividends'] = correct_div

                        target_div_pct = row['%'] * correction
                        target_adj = 1.0 - target_div_pct
                        present_adj = row['present adj']
                        k += ' & div-adjust'
                        adj_correction = target_adj / present_adj
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True

                        cluster.loc[dt, 'Fixed?'] = True
                        div_repairs.setdefault(k, []).append(dt)

                    elif adj_missing:
                        k = 'missing div-adjust'
                        div_repairs.setdefault(k, []).append(dt)
                        adj_correction = 1.0-row['%']
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True

                    elif div_date_wrong:
                        k = 'wrong ex-div date'
                        div_repairs.setdefault(k, []).append(dt)

                        # First rollback the present adj
                        adj_correction = 1.0/row['present adj']
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction

                        # Apply correct adj from correct date
                        div_true_date = row['div_true_date']
                        close_before = df2['Close'].iloc[row['idx']]
                        div = row['div']
                        true_adj = 1.0 - div/close_before
                        enddt2 = div_true_date-_datetime.timedelta(seconds=1)
                        df2.loc[    :enddt2, 'Adj Close'] *= true_adj
                        df2_nan.loc[:enddt2, 'Adj Close'] *= true_adj

                        # Move div to correct date
                        df2.loc[div_true_date, 'Dividends'] += div
                        df2.loc[dt, 'Dividends'] = 0

                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True

                    elif adj_exceeds_prices:
                        # Nothing else wrong => probably false positive, 
                        # but no harm checking the adjustment
                        target_adj = 1.0 - row['%']
                        present_adj = row['present adj']
                        if abs((target_adj/present_adj)-1) > 0.05:
                            # Also correct adjustment to match corrected dividend
                            k += ' & div-adjust'
                            adj_correction = target_adj / present_adj
                            df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                            df2.loc[    :enddt, 'Repaired?'] = True
                            df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                            df2_nan.loc[:enddt, 'Repaired?'] = True
                            cluster.loc[dt, 'Fixed?'] = True
                        else:
                            div_status_df = div_status_df.drop(dt)
                            cluster = cluster.drop(dt)

                    elif div_pre_split:
                        k = 'pre-split div'
                        correction = 1.0/df2['Stock Splits'].loc[dt]
                        correct_div = row['div'] * correction
                        df2.loc[dt, 'Dividends'] = correct_div

                        target_div_pct = row['%'] * correction
                        target_adj = 1.0 - target_div_pct
                        present_adj = row['present adj']
                        # Also correct adjustment to match corrected dividend
                        k += ' & div-adjust'
                        adj_correction = target_adj / present_adj
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True
                        div_repairs.setdefault(k, []).append(dt)

                elif n_failed_checks == 2:
                    if div_too_big and adj_missing:
                        # A currency unit mixup AND adjustment missing
                        k = 'too-big div and missing div-adjust'
                        div_repairs.setdefault(k, []).append(dt)
                        adj_correction = 1.0 - row['%']/currency_divide
                        df2.loc[dt, 'Dividends'] /= currency_divide
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True

                    elif div_too_big and div_exceeds_adj:
                        div = row['div']
                        close = div/row['%']
                        adj_present = row['present adj']
                        # Adj Close is correct, just need to fix Dividend.
                        # Probably just a currency unit mixup.
                        df2.loc[dt, 'Dividends'] /= currency_divide
                        k = 'div-too-big'
                        div_repairs.setdefault(k, []).append(dt)
                        cluster.loc[dt, 'Fixed?'] = True

                    elif div_too_big and adj_exceeds_prices:
                        # Assume div 100x error, and that Yahoo used this wrong dividend.
                        # 'adj_too_big=True' is probably redundant information, knowing div too big
                        # is enough to require also fixing adjustment
                        k = 'too-big div & div-adjust'
                        div_repairs.setdefault(k, []).append(dt)
                        target_div_pct = row['%']/currency_divide
                        target_adj = 1.0 - target_div_pct
                        adj_correction = target_adj / row['present adj']
                        df2.loc[dt, 'Dividends'] /= currency_divide
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True

                    elif div_too_small and adj_exceeds_div:
                        # Adj Close is correct, just need to fix Dividend.
                        # Probably just a currency unit mixup.
                        df2.loc[dt, 'Dividends'] *= currency_divide
                        k = 'too-small div'
                        if 'FX was repaired' in row and row['FX was repaired']:
                            # Complication: not just a currency unit mixup, but
                            # mixed up the local currency with $. So need to 
                            # recalculate adjustment.
                            msg = None
                            div_adj = 1.0 - (row['%']*currency_divide)
                            adj_correction = div_adj / row['present adj']
                            df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                            df2.loc[    :enddt, 'Repaired?'] = True
                            df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                            df2_nan.loc[:enddt, 'Repaired?'] = True
                            # Currently not logging this FX-fix event, since I refactored fixing.
                            k += " and FX mixup"
                        div_repairs.setdefault(k, []).append(dt)
                        cluster.loc[dt, 'Fixed?'] = True

                elif n_failed_checks == 3:
                    if div_too_big and div_exceeds_adj and div_pre_split:
                        k = 'too-big div & pre-split'
                        correction = (1.0/currency_divide) * (1.0/df2['Stock Splits'].loc[dt])
                        correct_div = row['div'] * correction
                        df2.loc[dt, 'Dividends'] = correct_div

                        target_div_pct = row['%'] * correction
                        target_adj = 1.0 - target_div_pct
                        present_adj = row['present adj']
                        # Also correct adjustment to match corrected dividend
                        k += ' & div-adjust'
                        adj_correction = target_adj / present_adj
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        cluster.loc[dt, 'Fixed?'] = True
                        div_repairs.setdefault(k, []).append(dt)

                    elif div_too_big and div_exceeds_adj and adj_too_small:
                        # Need to fix dividend AND adj close.
                        # Probably just a currency unit mixup.
                        div = row['div']
                        close = div/row['%']
                        adj_present = row['present adj']
                        k = 'div-too-big and adj-too-small'
                        #
                        div_true = div/currency_divide
                        pct_true = div_true / close
                        df2.loc[dt, 'Dividends'] = div_true
                        #
                        adj_correct = 1.0 - pct_true
                        adj_correction = adj_correct / adj_present
                        df2.loc[    :enddt, 'Adj Close'] *= adj_correction
                        df2.loc[    :enddt, 'Repaired?'] = True
                        df2_nan.loc[:enddt, 'Adj Close'] *= adj_correction
                        df2_nan.loc[:enddt, 'Repaired?'] = True
                        div_repairs.setdefault(k, []).append(dt)
                        cluster.loc[dt, 'Fixed?'] = True

            if cluster.empty:
                continue

        for k in div_repairs:
            msg = f"Repaired {k}: {[str(dt.date()) for dt in sorted(div_repairs[k])]}"
            logger.info(msg, extra=log_extras)

        if 'Adj' in df2.columns:
            raise Exception('"Adj" has snuck in df2')

        if not df2_nan.empty:
            df2 = pd.concat([df2, df2_nan]).sort_index()

        return df2

    @utils.log_indent_decorator
    def _fix_bad_stock_splits(self, df, interval, tz_exchange):
        # Original logic only considered latest split adjustment could be missing, but 
        # actually **any** split adjustment can be missing. So check all splits in df.
        #
        # Improved logic looks for BIG daily price changes that closely match the
        # **nearest future** stock split ratio. This indicates Yahoo failed to apply a new
        # stock split to old price data.
        #
        # There is a slight complication, because Yahoo does another stupid thing.
        # Sometimes the old data is adjusted twice. So cannot simply assume
        # which direction to reverse adjustment - have to analyse prices and detect.
        # Not difficult.

        if df.empty:
            return df

        logger = utils.get_yf_logger()
        log_extras = {'yf_cat': 'split-repair', 'yf_interval': interval, 'yf_symbol': self.ticker}

        interday = interval in ['1d', '1wk', '1mo', '3mo']
        if not interday:
            return df

        df = df.sort_index()   # scan splits oldest -> newest
        split_f = df['Stock Splits'].to_numpy() != 0
        if not split_f.any():
            logger.debug('price-repair-split: No splits in data')
            return df

        logger.debug(f'Splits: {str(df["Stock Splits"][split_f].to_dict())}', extra=log_extras)

        if 'Repaired?' not in df.columns:
            df['Repaired?'] = False
        for split_idx in np.where(split_f)[0]:
            split_dt = df.index[split_idx]
            split = df.loc[split_dt, 'Stock Splits']
            if split_dt == df.index[0]:
                continue

            # Add on a week:
            if interval in ['1wk', '1mo', '3mo']:
                split_idx += 1
            else:
                split_idx += 5
            cutoff_idx = min(df.shape[0], split_idx)  # add one row after to detect big change
            df_pre_split = df.iloc[0:cutoff_idx+1]
            logger.debug(f'split_idx={split_idx} split_dt={split_dt.date()} split={split:.4f}', extra=log_extras)
            logger.debug(f'df dt range: {df_pre_split.index[0].date()} -> {df_pre_split.index[-1].date()}', extra=log_extras)
            df_pre_split_repaired = self._fix_prices_sudden_change(df_pre_split, interval, tz_exchange, split, correct_volume=True, correct_dividend=True)
            # Merge back in:
            if cutoff_idx == df.shape[0]-1:
                df = df_pre_split_repaired
            else:
                df_post_cutoff = df.iloc[cutoff_idx+1:]
                if df_post_cutoff.empty:
                    df = df_pre_split_repaired.sort_index()
                else:
                    df = pd.concat([df_pre_split_repaired.sort_index(), df_post_cutoff])
        return df

    @utils.log_indent_decorator
    def _fix_prices_sudden_change(self, df, interval, tz_exchange, change, correct_volume=False, correct_dividend=False):
        if df.empty:
            return df

        logger = utils.get_yf_logger()
        log_extras = {'yf_cat': 'price-change-repair', 'yf_interval': interval, 'yf_symbol': self.ticker}

        split = change
        split_rcp = 1.0 / split
        interday = interval in ['1d', '1wk', '1mo', '3mo']
        multiday = interval in ['1wk', '1mo', '3mo']

        if change in [100.0, 0.01]:
            fix_type = '100x error'
            log_extras['yf_cat'] = 'price-repair-100x'
            start_min = None
        else:
            fix_type = 'bad split'
            log_extras['yf_cat'] = 'price-repair-split'
            # start_min = 1 year before oldest split
            f = df['Stock Splits'].to_numpy() != 0.0
            start_min = (df.index[f].min() - _dateutil.relativedelta.relativedelta(years=1)).date()
        logger.debug(f'start_min={start_min} change={change:.4f} (rcp={1.0/change:.4f})', extra=log_extras)

        OHLC = ['Open', 'High', 'Low', 'Close']

        # Do not attempt repair of the split is small,
        # could be mistaken for normal price variance
        if 0.8 < split < 1.25:
            logger.debug("Split ratio too close to 1. Won't repair", extra=log_extras)
            return df

        df2 = df.copy().sort_index(ascending=False)
        if df2.index.tz is None:
            df2.index = df2.index.tz_localize(tz_exchange)
        elif df2.index.tz != tz_exchange:
            df2.index = df2.index.tz_convert(tz_exchange)
        n = df2.shape[0]

        # If stock is currently suspended and not in USA, then usually Yahoo introduces
        # 100x errors into suspended intervals. Clue is no price change and 0 volume.
        # Better to use last active trading interval as baseline.
        # f_no_activity = (df2['Low'] == df2['High']) & (df2['Volume']==0)
        # Update: intra-interval 100x/0.01x errors can trick Low==High
        f_no_activity = df2['Volume']==0
        f_no_activity = f_no_activity | df2[OHLC].isna().all(axis=1)
        appears_suspended = f_no_activity.any() and np.where(f_no_activity)[0][0]==0
        f_active = ~f_no_activity
        idx_latest_active = np.where(f_active & np.roll(f_active, 1))[0]
        if len(idx_latest_active) == 0:
            # In rare cases, not enough trading activity for 2+ consecutive days e.g. CLC.L
            idx_latest_active = np.where(f_active)[0]
        if len(idx_latest_active) == 0:
            idx_latest_active = None
        else:
            idx_latest_active = int(idx_latest_active[0])
        log_msg = f'appears_suspended={appears_suspended}, idx_latest_active={idx_latest_active}'
        if idx_latest_active is not None:
            log_msg += f' ({df2.index[idx_latest_active].date()})'
        logger.debug(log_msg, extra=log_extras)

        if logger.isEnabledFor(logging.DEBUG):
            df_debug = df2.copy()
            df_debug = df_debug.drop(['Adj Close', 'Volume', 'Dividends', 'Stock Splits', 'Repaired?'], axis=1, errors='ignore')
            debug_cols = ['Close']
            df_debug = df_debug.drop([c for c in OHLC if c not in debug_cols], axis=1, errors='ignore')
        else:
            debug_cols = []

        # Calculate daily price % change. To reduce effect of price volatility,
        # calculate change for each OHLC column.
        if interday and interval != '1d' and split not in [100.0, 100, 0.001]:
            # Avoid using 'Low' and 'High'. For multiday intervals, these can be
            # very volatile so reduce ability to detect genuine stock split errors
            _1d_change_x = np.full((n, 2), 1.0)
            price_data = df2[['Open','Close']].to_numpy()
            f_zero = price_data == 0.0
        else:
            _1d_change_x = np.full((n, 4), 1.0)
            price_data = df2[OHLC].to_numpy()
            f_zero = price_data == 0.0
        if f_zero.any():
            price_data[f_zero] = 1.0

        # Update: if a VERY large dividend is paid out, then can be mistaken for a 1:2 stock split.
        # Fix = use adjusted prices
        f_zero = df2['Close'] == 0
        if f_zero.any():
            adj = np.ones(len(df2))
            adj[~f_zero] = df2['Adj Close'].to_numpy()[~f_zero] / df2['Close'].to_numpy()[~f_zero]
        else:
            adj = df2['Adj Close'].to_numpy() / df2['Close'].to_numpy()
        df_dtype = price_data.dtype
        if df_dtype == np.int64:
            price_data = price_data.astype('float')
        for j in range(price_data.shape[1]):
            price_data[:,j] *= adj
            if logger.isEnabledFor(logging.DEBUG):
                if OHLC[j] in df_debug.columns:
                    df_debug[OHLC[j]] *= adj
        if df_dtype == np.int64:
            price_data = price_data.astype('int')

        _1d_change_x[1:] = price_data[1:, ] / price_data[:-1, ]
        f_zero_num_denom = f_zero | np.roll(f_zero, 1, axis=0)
        if f_zero_num_denom.any():
            _1d_change_x[f_zero_num_denom] = 1.0
        if interday and interval != '1d':
            # average change
            _1d_change_minx = np.average(_1d_change_x, axis=1)
        else:
            # # change nearest to 1.0
            # diff = np.abs(_1d_change_x - 1.0)
            # j_indices = np.argmin(diff, axis=1)
            # _1d_change_minx = _1d_change_x[np.arange(n), j_indices]
            # Still sensitive to extreme-low low. Try median:
            _1d_change_minx = np.median(_1d_change_x, axis=1)
        f_na = np.isnan(_1d_change_minx)
        if f_na.any():
            # Possible if data was too old for reconstruction.
            _1d_change_minx[f_na] = 1.0
        if logger.isEnabledFor(logging.DEBUG):
            df_debug['1D %'] = _1d_change_minx
            df_debug['1D %'] = df_debug['1D %'].round(2).astype('str')

        # If all 1D changes are closer to 1.0 than split, exit
        split_max = max(split, split_rcp)
        if np.max(_1d_change_minx) < (split_max - 1) * 0.5 + 1 and np.min(_1d_change_minx) > 1.0 / ((split_max - 1) * 0.5 + 1):
            logger.debug(f'No {fix_type}s detected', extra=log_extras)
            return df

        # Calculate the true price variance, i.e. remove effect of bad split-adjustments.
        # Key = ignore 1D changes outside of interquartile range
        q1, q3 = np.percentile(_1d_change_minx, [25, 75])
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        f = (_1d_change_minx >= lower_bound) & (_1d_change_minx <= upper_bound)
        avg = np.mean(_1d_change_minx[f])
        sd = np.std(_1d_change_minx[f])
        # Now can calculate SD as % of mean
        sd_pct = sd / avg
        logger.debug(f"Estimation of true 1D change stats: mean = {avg:.2f}, StdDev = {sd:.4f} ({sd_pct*100.0:.1f}% of mean)", extra=log_extras)

        # Only proceed if split adjustment far exceeds normal 1D changes
        largest_change_pct = 5 * sd_pct
        if interday and interval != '1d':
            largest_change_pct *= 3
            if interval in ['1mo', '3mo']:
                largest_change_pct *= 2
        if max(split, split_rcp) < 1.0 + largest_change_pct:
            logger.debug("Split ratio too close to normal price volatility. Won't repair", extra=log_extras)
            logger.debug(f"sd_pct = {sd_pct:.4f}  largest_change_pct = {largest_change_pct:.4f}", extra=log_extras)
            return df

        # Now can detect bad split adjustments
        # Set threshold to halfway between split ratio and largest expected normal price change
        r = _1d_change_minx / split_rcp
        split_max = max(split, split_rcp)
        logger.debug(f"split_max={split_max:.3f} largest_change_pct={largest_change_pct:.4f}", extra=log_extras)
        threshold = (split_max + 1.0 + largest_change_pct) * 0.5
        logger.debug(f"threshold={threshold:.3f}", extra=log_extras)

        if 'Repaired?' not in df2.columns:
            df2['Repaired?'] = False

        if interday and interval != '1d':
            # Yahoo creates multi-day intervals using potentiall corrupt data, e.g.
            # the Close could be 100x Open. This means have to correct each OHLC column
            # individually
            correct_columns_individually = True
        else:
            correct_columns_individually = False

        if correct_columns_individually:
            _1d_change_x = np.full((n, 4), 1.0)
            price_data = df2[OHLC].replace(0.0, 1.0).to_numpy()
            _1d_change_x[1:] = price_data[1:, ] / price_data[:-1, ]
        else:
            _1d_change_x = _1d_change_minx

        r = _1d_change_x / split_rcp
        f_down = _1d_change_x < 1.0 / threshold
        # if f_down.any():
        #     # Discard where triggered by negative Adj Close after dividend
        #     f_neg = _1d_change_x < 0.0
        #     f_div = (df2['Dividends']>0).to_numpy()
        #     f_div_before = np.roll(f_div, 1)
        #     if f_down.ndim == 2:
        #         f_div_before = f_div_before[:, np.newaxis].repeat(f_down.shape[1], axis=1)
        #     f_down = f_down & ~(f_neg + f_div_before)
        f_up = _1d_change_x > threshold
        f_up_ndims = len(f_up.shape)
        f_up_shifts = f_up if f_up_ndims==1 else f_up.any(axis=1)
        # In rare cases e.g. real disasters, the price actually drops massively on huge volume
        if f_up_shifts.any():
            for i in np.where(f_up_shifts)[0]:
                v = df2['Volume'].iloc[i]
                vol_change_pct = 0 if v == 0 else df2['Volume'].iloc[i-1] / v
                if multiday and (i+1 < len(df2)):
                    next_v = df2['Volume'].iloc[i+1]
                    if next_v > 0:
                        vol_change_pct = max(vol_change_pct, df2['Volume'].iloc[i] / next_v)
                if vol_change_pct > 5:
                    # big volume change +500%
                    # Could be false-positive, but need some more checks
                    lookback = max(0, i-10)
                    lookahead = min(len(df2), i+10)
                    if (df2['Stock Splits'].iloc[lookback:lookahead]!=0.0).any():
                        # There's a stock split near the volume spike, so 
                        # assume false positive
                        continue
                    avg_vol_after = df2['Volume'].iloc[lookback:i-1].mean()
                    if not np.isnan(avg_vol_after) and avg_vol_after > 0 and v/avg_vol_after < 2.0:
                        # volume spike is actually a step-change, so 
                        # probably missing stock split
                        continue
                    if f_up_ndims == 1:
                        f_up[i] = False
                    else:
                        f_up[i,:] = False
        f = f_down | f_up
        if logger.isEnabledFor(logging.DEBUG):
            if not correct_columns_individually:
                df_debug['r'] = r
                df_debug['down'] = f_down
                df_debug['up'] = f_up
                df_debug['r'] = df_debug['r'].round(2).astype('str')
            else:
                for j in range(len(OHLC)):
                    c = OHLC[j]
                    if c in debug_cols:
                        df_debug[c + '_r'] = r[:, j]
                        df_debug[c + '_r'] = df_debug[c + '_r'].round(2).astype('str')
                        df_debug[c + '_down'] = f_down[:, j]
                        df_debug[c + '_up'] = f_up[:, j]

        if not f.any():
            logger.debug(f'No {fix_type}s detected', extra=log_extras)
            return df

        # Update: if any 100x changes are soon after a stock split, so could be confused with split error, then abort
        threshold_days = 30
        f_splits = df2['Stock Splits'].to_numpy() != 0.0
        if change in [100.0, 0.01] and f_splits.any():
            indices_A = np.where(f_splits)[0]
            indices_B = np.where(f)[0]
            if not len(indices_A) or not len(indices_B):
                return None
            gaps = indices_B[:, None] - indices_A
            # Because data is sorted in DEscending order, need to flip gaps
            gaps *= -1
            f_pos = gaps > 0
            if f_pos.any():
                gap_min = gaps[f_pos].min()
                gap_td = utils._interval_to_timedelta(interval) * gap_min
                if isinstance(gap_td, _dateutil.relativedelta.relativedelta):
                    threshold = _dateutil.relativedelta.relativedelta(days=threshold_days)
                else:
                    threshold = _datetime.timedelta(days=threshold_days)
                if isinstance(threshold, _dateutil.relativedelta.relativedelta) and isinstance(gap_td, _dateutil.relativedelta.relativedelta):
                    idx = np.where(gaps==gap_min)[0][0]
                    dt = df2.index[idx]
                    within_threshold = (dt + gap_td) < (dt + threshold)
                else:
                    within_threshold = gap_td < threshold
                if within_threshold:
                    logger.info('100x changes are too soon after stock split events, aborting', extra=log_extras)
                    return df

        if logger.isEnabledFor(logging.DEBUG):
            df_debug['i'] = list(range(0, df_debug.shape[0]))
            df_debug['i_rev'] = df_debug.shape[0]-1 - df_debug['i']
            if correct_columns_individually:
                f_change = df_debug[[c+'_down' for c in debug_cols]].any(axis=1) | df_debug[[c+'_up' for c in debug_cols]].any(axis=1)
            else:
                f_change = df_debug['down'] | df_debug['up']
            f_change = f_change | np.roll(f_change, -1) | np.roll(f_change, 1) | np.roll(f_change, -2) | np.roll(f_change, 2)
            with pd.option_context('display.max_rows', None, 'display.max_columns', 10, 'display.width', 1000):  # more options can be specified also
                logger.debug("price-repair-split: my workings:" + '\n' + str(df_debug[f_change]))

        def map_signals_to_ranges(f, f_up, f_down):
            # Ensure 0th element is False, because True is nonsense
            if f[0]:
                f = np.copy(f)
                f[0] = False
                f_up = np.copy(f_up)
                f_up[0] = False
                f_down = np.copy(f_down)
                f_down[0] = False

            if not f.any():
                return []

            true_indices = np.where(f)[0]
            ranges = []

            for i in range(len(true_indices) - 1):
                if i % 2 == 0:
                    if split > 1.0:
                        adj = 'split' if f_down[true_indices[i]] else '1.0/split'
                    else:
                        adj = '1.0/split' if f_down[true_indices[i]] else 'split'
                    ranges.append((true_indices[i], true_indices[i + 1], adj))

            if len(true_indices) % 2 != 0:
                if split > 1.0:
                    adj = 'split' if f_down[true_indices[-1]] else '1.0/split'
                else:
                    adj = '1.0/split' if f_down[true_indices[-1]] else 'split'
                ranges.append((true_indices[-1], len(f), adj))

            return ranges

        if idx_latest_active is not None:
            idx_rev_latest_active = df.shape[0] - 1 - idx_latest_active
            logger.debug(f'idx_latest_active={idx_latest_active}, idx_rev_latest_active={idx_rev_latest_active}', extra=log_extras)
        if correct_columns_individually:
            f_corrected = np.full(n, False)
            if correct_volume:
                # If Open or Close is repaired but not both,
                # then this means the interval has a mix of correct
                # and errors. A problem for correcting Volume,
                # so use a heuristic:
                # - if both Open & Close were Nx bad => Volume is Nx bad
                # - if only one of Open & Close are Nx bad => Volume is 0.5*Nx bad
                f_open_fixed = np.full(n, False)
                f_close_fixed = np.full(n, False)

            OHLC_correct_ranges = [None, None, None, None]
            for j in range(len(OHLC)):
                c = OHLC[j]
                idx_first_f = np.where(f)[0][0]
                if appears_suspended and (idx_latest_active is not None and idx_latest_active >= idx_first_f):
                    # Suspended midway during data date range.
                    # 1: process data before suspension in index-ascending (date-descending) order.
                    # 2: process data after suspension in index-descending order. Requires signals to be reversed,
                    #    then returned ranges to also be reversed, because this logic was originally written for
                    #    index-ascending (date-descending) order.
                    fj = f[:, j]
                    f_upj = f_up[:, j]
                    f_downj = f_down[:, j]
                    ranges_before = map_signals_to_ranges(fj[idx_latest_active:], f_upj[idx_latest_active:], f_downj[idx_latest_active:])
                    if len(ranges_before) > 0:
                        # Shift each range back to global indexing
                        for i in range(len(ranges_before)):
                            r = ranges_before[i]
                            ranges_before[i] = (r[0] + idx_latest_active, r[1] + idx_latest_active, r[2])
                    f_rev_downj = np.flip(np.roll(f_upj, -1))  # correct
                    f_rev_upj = np.flip(np.roll(f_downj, -1))  # correct
                    f_revj = f_rev_upj | f_rev_downj
                    ranges_after = map_signals_to_ranges(f_revj[idx_rev_latest_active:], f_rev_upj[idx_rev_latest_active:], f_rev_downj[idx_rev_latest_active:])
                    if len(ranges_after) > 0:
                        # Shift each range back to global indexing:
                        for i in range(len(ranges_after)):
                            r = ranges_after[i]
                            ranges_after[i] = (r[0] + idx_rev_latest_active, r[1] + idx_rev_latest_active, r[2])
                        # Flip range to normal ordering
                        for i in range(len(ranges_after)):
                            r = ranges_after[i]
                            ranges_after[i] = (n-r[1], n-r[0], r[2])
                    ranges = ranges_before
                    ranges.extend(ranges_after)
                else:
                    ranges = map_signals_to_ranges(f[:, j], f_up[:, j], f_down[:, j])
                logger.debug(f"column '{c}' ranges: {ranges}", extra=log_extras)
                if start_min is not None:
                    # Prune ranges that are older than start_min
                    for i in range(len(ranges)-1, -1, -1):
                        r = ranges[i]
                        if df2.index[r[0]].date() < start_min:
                            logger.debug(f'Pruning {c} range {df2.index[r[0]]}->{df2.index[r[1]-1]} because too old.', extra=log_extras)
                            del ranges[i]

                if len(ranges) > 0:
                    OHLC_correct_ranges[j] = ranges

            count = sum([1 if x is not None else 0 for x in OHLC_correct_ranges])
            if count == 0:
                pass
            elif count == 1:
                # If only 1 column then assume false positive
                idxs = [i if OHLC_correct_ranges[i] else -1 for i in range(len(OHLC))]
                idx = np.where(np.array(idxs) != -1)[0][0]
                col = OHLC[idx]
                logger.debug(f'Potential {fix_type} detected only in column {col}, so treating as false positive (ignore)', extra=log_extras)
            else:
                # Only correct if at least 2 columns require correction.
                n_corrected = [0,0,0,0]
                for j in range(len(OHLC)):
                    c = OHLC[j]
                    ranges = OHLC_correct_ranges[j]
                    if ranges is None:
                        ranges = []
                    for r in ranges:
                        if r[2] == 'split':
                            m = split
                            m_rcp = split_rcp
                        else:
                            m = split_rcp
                            m_rcp = split
                        if interday:
                            msg = f"Corrected {fix_type} on col={c} range=[{df2.index[r[1]-1].date()}:{df2.index[r[0]].date()}] m={m:.4f}"
                        else:
                            msg = f"Corrected {fix_type} on col={c} range=[{df2.index[r[1]-1]}:{df2.index[r[0]]}] m={m:.4f}"
                        logger.debug(msg, extra=log_extras)
                        # Instead of logging here, just count
                        n_corrected[j] += r[1]-r[0]
                        df2.iloc[r[0]:r[1], df2.columns.get_loc(c)] *= m
                        if c == 'Close':
                            df2.iloc[r[0]:r[1], df2.columns.get_loc('Adj Close')] *= m
                        if correct_volume:
                            if c == 'Open':
                                f_open_fixed[r[0]:r[1]] = True
                            elif c == 'Close':
                                f_close_fixed[r[0]:r[1]] = True
                        f_corrected[r[0]:r[1]] = True
                if sum(n_corrected) > 0:
                    counts_pretty = ''
                    for j in range(len(OHLC)):
                        if n_corrected[j] != 0:
                            if counts_pretty != '':
                                counts_pretty += ', '
                            counts_pretty += f'{OHLC[j]}={n_corrected[j]}x'
                    msg = f"Corrected: {counts_pretty}"
                    logger.info(msg, extra=log_extras)

            if correct_volume:
                f_open_and_closed_fixed = f_open_fixed & f_close_fixed
                f_open_xor_closed_fixed = np.logical_xor(f_open_fixed, f_close_fixed)
                if f_open_and_closed_fixed.any():
                    df2.loc[f_open_and_closed_fixed, "Volume"] = (df2.loc[f_open_and_closed_fixed, "Volume"] * m_rcp).round().astype('int')
                if f_open_xor_closed_fixed.any():
                    df2.loc[f_open_xor_closed_fixed, "Volume"] = (df2.loc[f_open_xor_closed_fixed, "Volume"] * 0.5 * m_rcp).round().astype('int')

            df2.loc[f_corrected, 'Repaired?'] = True

        else:
            n_corrected = 0
            idx_first_f = np.where(f)[0][0]
            if appears_suspended and (idx_latest_active is not None and idx_latest_active >= idx_first_f):
                # Suspended midway during data date range.
                # 1: process data before suspension in index-ascending (date-descending) order.
                # 2: process data after suspension in index-descending order. Requires signals to be reversed,
                #    then returned ranges to also be reversed, because this logic was originally written for
                #    index-ascending (date-descending) order.
                ranges_before = map_signals_to_ranges(f[idx_latest_active:], f_up[idx_latest_active:], f_down[idx_latest_active:])
                if len(ranges_before) > 0:
                    # Shift each range back to global indexing
                    for i in range(len(ranges_before)):
                        r = ranges_before[i]
                        ranges_before[i] = (r[0] + idx_latest_active, r[1] + idx_latest_active, r[2])
                f_rev_down = np.flip(np.roll(f_up, -1))
                f_rev_up = np.flip(np.roll(f_down, -1))
                f_rev = f_rev_up | f_rev_down
                ranges_after = map_signals_to_ranges(f_rev[idx_rev_latest_active:], f_rev_up[idx_rev_latest_active:], f_rev_down[idx_rev_latest_active:])
                if len(ranges_after) > 0:
                    # Shift each range back to global indexing:
                    for i in range(len(ranges_after)):
                        r = ranges_after[i]
                        ranges_after[i] = (r[0] + idx_rev_latest_active, r[1] + idx_rev_latest_active, r[2])
                    # Flip range to normal ordering
                    for i in range(len(ranges_after)):
                        r = ranges_after[i]
                        ranges_after[i] = (n-r[1], n-r[0], r[2])
                ranges = ranges_before
                ranges.extend(ranges_after)
            else:
                ranges = map_signals_to_ranges(f, f_up, f_down)
            if start_min is not None:
                # Prune ranges that are older than start_min
                for i in range(len(ranges)-1, -1, -1):
                    r = ranges[i]
                    if df2.index[r[0]].date() < start_min:
                        logger.debug(f'Pruning range {df2.index[r[0]]}->{df2.index[r[1]-1]} because too old.', extra=log_extras)
                        del ranges[i]
            for r in ranges:
                if r[2] == 'split':
                    m = split
                    m_rcp = split_rcp
                else:
                    m = split_rcp
                    m_rcp = split
                logger.debug(f"range={r} m={m}", extra=log_extras)
                for c in ['Open', 'High', 'Low', 'Close', 'Adj Close']:
                    df2.iloc[r[0]:r[1], df2.columns.get_loc(c)] *= m
                if correct_dividend:
                    df2.iloc[r[0]:r[1], df2.columns.get_loc('Dividends')] *= m
                if correct_volume:
                    col_loc = df2.columns.get_loc("Volume")
                    df2.iloc[r[0]:r[1], col_loc] = (df2.iloc[r[0]:r[1], col_loc] * m_rcp).round().astype('int')
                df2.iloc[r[0]:r[1], df2.columns.get_loc('Repaired?')] = True
                if r[0] == r[1] - 1:
                    if interday:
                        msg = f"Corrected {fix_type} on interval {df2.index[r[0]].date()}"
                    else:
                        msg = f"Corrected {fix_type} on interval {df2.index[r[0]]}"
                else:
                    # Note: df2 sorted with index descending
                    start = df2.index[r[1] - 1]
                    end = df2.index[r[0]]
                    if interday:
                        msg = f"Corrected {fix_type} across intervals {start.date()} -> {end.date()} (inclusive)"
                    else:
                        msg = f"Corrected {fix_type} across intervals {start} -> {end} (inclusive)"
                logger.debug(msg, extra=log_extras)
                n_corrected += r[1] - r[0]

            if len(ranges) <= 2:
                msg = "Corrected:"
                for r in ranges:
                    msg += f" {df2.index[r[1]-1].date()} -> {df2.index[r[0]].date()}"
            else:
                msg = f"Corrected: {n_corrected}x"
            logger.info(msg, extra=log_extras)

        if correct_volume:
            f_na = df2['Volume'].isna()
            if f_na.any():
                df2.loc[~f_na,'Volume'] = df2['Volume'][~f_na].round(0).astype('int')
            else:
                df2['Volume'] = df2['Volume'].round(0).astype('int')

        return df2.sort_index()
