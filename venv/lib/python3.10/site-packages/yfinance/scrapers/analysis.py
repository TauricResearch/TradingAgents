import curl_cffi
import pandas as pd
import warnings

from yfinance import utils
from yfinance.const import quote_summary_valid_modules, _SENTINEL_
from yfinance.data import YfData
from yfinance.exceptions import YFException
from yfinance.scrapers.quote import _QUOTE_SUMMARY_URL_

class Analysis:

    def __init__(self, data: YfData, symbol: str, proxy=_SENTINEL_):
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            data._set_proxy(proxy)

        self._data = data
        self._symbol = symbol

        # In quoteSummary the 'earningsTrend' module contains most of the data below.
        # The format of data is not optimal so each function will process it's part of the data.
        # This variable works as a cache.
        self._earnings_trend = None

        self._analyst_price_targets = None
        self._earnings_estimate = None
        self._revenue_estimate = None
        self._earnings_history = None
        self._eps_trend = None
        self._eps_revisions = None
        self._growth_estimates = None

    def _get_periodic_df(self, key) -> pd.DataFrame:
        if self._earnings_trend is None:
            self._fetch_earnings_trend()

        data = []
        for item in self._earnings_trend[:4]:
            row = {'period': item['period']}
            for k, v in item[key].items():
                if not isinstance(v, dict) or len(v) == 0:
                    continue
                row[k] = v['raw']
            data.append(row)
        if len(data) == 0:
            return pd.DataFrame()
        return pd.DataFrame(data).set_index('period')

    @property
    def earnings_estimate(self) -> pd.DataFrame:
        if self._earnings_estimate is not None:
            return self._earnings_estimate
        self._earnings_estimate = self._get_periodic_df('earningsEstimate')
        return self._earnings_estimate

    @property
    def revenue_estimate(self) -> pd.DataFrame:
        if self._revenue_estimate is not None:
            return self._revenue_estimate
        self._revenue_estimate = self._get_periodic_df('revenueEstimate')
        return self._revenue_estimate

    @property
    def eps_trend(self) -> pd.DataFrame:
        if self._eps_trend is not None:
            return self._eps_trend
        self._eps_trend = self._get_periodic_df('epsTrend')
        return self._eps_trend

    @property
    def eps_revisions(self) -> pd.DataFrame:
        if self._eps_revisions is not None:
            return self._eps_revisions
        self._eps_revisions = self._get_periodic_df('epsRevisions')
        return self._eps_revisions

    @property
    def analyst_price_targets(self) -> dict:
        if self._analyst_price_targets is not None:
            return self._analyst_price_targets

        try:
            data = self._fetch(['financialData'])
            data = data['quoteSummary']['result'][0]['financialData']
        except (TypeError, KeyError):
            self._analyst_price_targets = {}
            return self._analyst_price_targets

        result = {}
        for key, value in data.items():
            if key.startswith('target'):
                new_key = key.replace('target', '').lower().replace('price', '').strip()
                result[new_key] = value
            elif key == 'currentPrice':
                result['current'] = value

        self._analyst_price_targets = result
        return self._analyst_price_targets

    @property
    def earnings_history(self) -> pd.DataFrame:
        if self._earnings_history is not None:
            return self._earnings_history

        try:
            data = self._fetch(['earningsHistory'])
            data = data['quoteSummary']['result'][0]['earningsHistory']['history']
        except (TypeError, KeyError):
            self._earnings_history = pd.DataFrame()
            return self._earnings_history

        rows = []
        for item in data:
            row = {'quarter': item.get('quarter', {}).get('fmt', None)}
            for k, v in item.items():
                if k == 'quarter':
                    continue
                if not isinstance(v, dict) or len(v) == 0:
                    continue
                row[k] = v.get('raw', None)
            rows.append(row)
        if len(data) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if 'quarter' in df.columns:
            df['quarter'] = pd.to_datetime(df['quarter'], format='%Y-%m-%d')
            df.set_index('quarter', inplace=True)

        self._earnings_history = df
        return self._earnings_history

    @property
    def growth_estimates(self) -> pd.DataFrame:
        if self._growth_estimates is not None:
            return self._growth_estimates

        if self._earnings_trend is None:
            self._fetch_earnings_trend()

        try:
            trends = self._fetch(['industryTrend', 'sectorTrend', 'indexTrend'])
            trends = trends['quoteSummary']['result'][0]
        except (TypeError, KeyError):
            self._growth_estimates = pd.DataFrame()
            return self._growth_estimates

        data = []
        for item in self._earnings_trend:
            period = item['period']
            row = {'period': period, 'stockTrend': item.get('growth', {}).get('raw', None)}
            data.append(row)

        for trend_name, trend_info in trends.items():
            if trend_info.get('estimates'):
                for estimate in trend_info['estimates']:
                    period = estimate['period']
                    existing_row = next((row for row in data if row['period'] == period), None)
                    if existing_row:
                        existing_row[trend_name] = estimate.get('growth')
                    else:
                        row = {'period': period, trend_name: estimate.get('growth')}
                        data.append(row)
        if len(data) == 0:
            return pd.DataFrame()

        self._growth_estimates = pd.DataFrame(data).set_index('period').dropna(how='all')
        return self._growth_estimates

    # modified version from quote.py
    def _fetch(self, modules: list):
        if not isinstance(modules, list):
            raise YFException("Should provide a list of modules, see available modules using `valid_modules`")

        modules = ','.join([m for m in modules if m in quote_summary_valid_modules])
        if len(modules) == 0:
            raise YFException("No valid modules provided, see available modules using `valid_modules`")
        params_dict = {"modules": modules, "corsDomain": "finance.yahoo.com", "formatted": "false", "symbol": self._symbol}
        try:
            result = self._data.get_raw_json(_QUOTE_SUMMARY_URL_ + f"/{self._symbol}", params=params_dict)
        except curl_cffi.requests.exceptions.HTTPError as e:
            utils.get_yf_logger().error(str(e) + e.response.text)
            return None
        return result

    def _fetch_earnings_trend(self) -> None:
        try:
            data = self._fetch(['earningsTrend'])
            self._earnings_trend = data['quoteSummary']['result'][0]['earningsTrend']['trend']
        except (TypeError, KeyError):
            self._earnings_trend = []
