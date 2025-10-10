import pandas as pd
from typing import Dict, Optional
import warnings

from yfinance import utils
from yfinance.const import _BASE_URL_, _SENTINEL_
from yfinance.data import YfData
from yfinance.exceptions import YFDataException

_QUOTE_SUMMARY_URL_ = f"{_BASE_URL_}/v10/finance/quoteSummary/"

class FundsData:
    """
    ETF and Mutual Funds Data
    Queried Modules: quoteType, summaryProfile, fundProfile, topHoldings

    Notes: 
    - fundPerformance module is not implemented as better data is queryable using history
    """
    def __init__(self, data: YfData, symbol: str, proxy=_SENTINEL_):
        """
        Args:
            data (YfData): The YfData object for fetching data.
            symbol (str): The symbol of the fund.
        """
        self._data = data
        self._symbol = symbol
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)
        
        # quoteType
        self._quote_type = None

        # summaryProfile
        self._description = None

        # fundProfile
        self._fund_overview = None
        self._fund_operations = None

        # topHoldings
        self._asset_classes = None
        self._top_holdings = None
        self._equity_holdings = None
        self._bond_holdings = None
        self._bond_ratings = None
        self._sector_weightings = None

    def quote_type(self) -> str:
        """
        Returns the quote type of the fund.

        Returns:
            str: The quote type.
        """
        if self._quote_type is None:
            self._fetch_and_parse()
        return self._quote_type
    
    @property
    def description(self) -> str:
        """
        Returns the description of the fund.

        Returns:
            str: The description.
        """
        if self._description is None:
            self._fetch_and_parse()
        return self._description
    
    @property
    def fund_overview(self) -> Dict[str, Optional[str]]:
        """
        Returns the fund overview.

        Returns:
            Dict[str, Optional[str]]: The fund overview.
        """
        if self._fund_overview is None:
            self._fetch_and_parse()
        return self._fund_overview

    @property
    def fund_operations(self) -> pd.DataFrame:
        """
        Returns the fund operations.

        Returns:
            pd.DataFrame: The fund operations.
        """
        if self._fund_operations is None:
            self._fetch_and_parse()
        return self._fund_operations

    @property
    def asset_classes(self) -> Dict[str, float]:
        """
        Returns the asset classes of the fund.

        Returns:
            Dict[str, float]: The asset classes.
        """
        if self._asset_classes is None:
            self._fetch_and_parse()
        return self._asset_classes

    @property
    def top_holdings(self) -> pd.DataFrame:
        """
        Returns the top holdings of the fund.

        Returns:
            pd.DataFrame: The top holdings.
        """
        if self._top_holdings is None:
            self._fetch_and_parse()
        return self._top_holdings

    @property
    def equity_holdings(self) -> pd.DataFrame:
        """
        Returns the equity holdings of the fund.

        Returns:
            pd.DataFrame: The equity holdings.
        """
        if self._equity_holdings is None:
            self._fetch_and_parse()
        return self._equity_holdings

    @property
    def bond_holdings(self) -> pd.DataFrame:
        """
        Returns the bond holdings of the fund.

        Returns:
            pd.DataFrame: The bond holdings.
        """
        if self._bond_holdings is None:
            self._fetch_and_parse()
        return self._bond_holdings

    @property
    def bond_ratings(self) -> Dict[str, float]:
        """
        Returns the bond ratings of the fund.

        Returns:
            Dict[str, float]: The bond ratings.
        """
        if self._bond_ratings is None:
            self._fetch_and_parse()
        return self._bond_ratings

    @property
    def sector_weightings(self) -> Dict[str,float]:
        """
        Returns the sector weightings of the fund.

        Returns:
            Dict[str, float]: The sector weightings.
        """
        if self._sector_weightings is None:
            self._fetch_and_parse()
        return self._sector_weightings

    def _fetch(self):
        """
        Fetches the raw JSON data from the API.

        Returns:
            dict: The raw JSON data.
        """
        modules = ','.join(["quoteType", "summaryProfile", "topHoldings", "fundProfile"])
        params_dict = {"modules": modules, "corsDomain": "finance.yahoo.com", "symbol": self._symbol, "formatted": "false"}
        result = self._data.get_raw_json(_QUOTE_SUMMARY_URL_+self._symbol, params=params_dict)
        return result

    def _fetch_and_parse(self) -> None:
        """
        Fetches and parses the data from the API.
        """
        result = self._fetch()
        try:
            data = result["quoteSummary"]["result"][0]
            # check quote type
            self._quote_type = data["quoteType"]["quoteType"]
            
            # parse "summaryProfile", "topHoldings", "fundProfile"
            self._parse_description(data["summaryProfile"])
            self._parse_top_holdings(data["topHoldings"])
            self._parse_fund_profile(data["fundProfile"])
        except KeyError:
            raise YFDataException("No Fund data found.")
        except Exception as e:
            logger = utils.get_yf_logger()
            logger.error(f"Failed to get fund data for '{self._symbol}' reason: {e}")
            logger.debug("Got response: ")
            logger.debug("-------------")
            logger.debug(f" {data}")
            logger.debug("-------------")

    @staticmethod
    def _parse_raw_values(data, default=None):
        """
        Parses raw values from the data.

        Args:
            data: The data to parse.
            default: The default value if data is not a dictionary.

        Returns:
            The parsed value or the default value.
        """
        if not isinstance(data, dict):
            return data
        
        return data.get("raw", default)

    def _parse_description(self, data) -> None:
        """
        Parses the description from the data.

        Args:
            data: The data to parse.
        """
        self._description = data.get("longBusinessSummary", "")

    def _parse_top_holdings(self, data) -> None:
        """
        Parses the top holdings from the data.

        Args:
            data: The data to parse.
        """
        # asset classes
        self._asset_classes = {
            "cashPosition": self._parse_raw_values(data.get("cashPosition", None)),
            "stockPosition": self._parse_raw_values(data.get("stockPosition", None)),
            "bondPosition": self._parse_raw_values(data.get("bondPosition", None)),
            "preferredPosition": self._parse_raw_values(data.get("preferredPosition", None)),
            "convertiblePosition": self._parse_raw_values(data.get("convertiblePosition", None)),
            "otherPosition": self._parse_raw_values(data.get("otherPosition", None))
        }

        # top holdings
        _holdings = data.get("holdings", [])
        _symbol, _name, _holding_percent = [], [], []

        for item in _holdings:
            _symbol.append(item["symbol"])
            _name.append(item["holdingName"])
            _holding_percent.append(item["holdingPercent"])
        
        self._top_holdings = pd.DataFrame({
            "Symbol": _symbol,
            "Name": _name,
            "Holding Percent": _holding_percent
        }).set_index("Symbol")

        # equity holdings
        _equity_holdings = data.get("equityHoldings", {})
        self._equity_holdings = pd.DataFrame({
            "Average": ["Price/Earnings", "Price/Book", "Price/Sales", "Price/Cashflow", "Median Market Cap", "3 Year Earnings Growth"],
            self._symbol: [
                self._parse_raw_values(_equity_holdings.get("priceToEarnings", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("priceToBook", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("priceToSales", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("priceToCashflow", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("medianMarketCap", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("threeYearEarningsGrowth", pd.NA)),
            ],
            "Category Average": [
                self._parse_raw_values(_equity_holdings.get("priceToEarningsCat", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("priceToBookCat", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("priceToSalesCat", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("priceToCashflowCat", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("medianMarketCapCat", pd.NA)),
                self._parse_raw_values(_equity_holdings.get("threeYearEarningsGrowthCat", pd.NA)),
            ]
        }).set_index("Average")
        
        # bond holdings
        _bond_holdings = data.get("bondHoldings", {})
        self._bond_holdings = pd.DataFrame({
            "Average": ["Duration", "Maturity", "Credit Quality"],
            self._symbol: [
                self._parse_raw_values(_bond_holdings.get("duration", pd.NA)),
                self._parse_raw_values(_bond_holdings.get("maturity", pd.NA)),
                self._parse_raw_values(_bond_holdings.get("creditQuality", pd.NA)),
            ],
            "Category Average": [
                self._parse_raw_values(_bond_holdings.get("durationCat", pd.NA)),
                self._parse_raw_values(_bond_holdings.get("maturityCat", pd.NA)),
                self._parse_raw_values(_bond_holdings.get("creditQualityCat", pd.NA)),
            ]
        }).set_index("Average")

        # bond ratings
        self._bond_ratings = dict((key, d[key]) for d in data.get("bondRatings", []) for key in d)

        # sector weightings
        self._sector_weightings = dict((key, d[key]) for d in data.get("sectorWeightings", []) for key in d)
        
    def _parse_fund_profile(self, data):
        """
        Parses the fund profile from the data.

        Args:
            data: The data to parse.
        """
        self._fund_overview = {
            "categoryName": data.get("categoryName", None), 
            "family":       data.get("family", None), 
            "legalType":    data.get("legalType", None)
        }
        
        _fund_operations = data.get("feesExpensesInvestment", {})
        _fund_operations_cat = data.get("feesExpensesInvestmentCat", {})

        self._fund_operations = pd.DataFrame({
            "Attributes": ["Annual Report Expense Ratio", "Annual Holdings Turnover", "Total Net Assets"],
            self._symbol: [
                self._parse_raw_values(_fund_operations.get("annualReportExpenseRatio", pd.NA)),
                self._parse_raw_values(_fund_operations.get("annualHoldingsTurnover", pd.NA)),
                self._parse_raw_values(_fund_operations.get("totalNetAssets", pd.NA))
            ],
            "Category Average": [
                self._parse_raw_values(_fund_operations_cat.get("annualReportExpenseRatio", pd.NA)),
                self._parse_raw_values(_fund_operations_cat.get("annualHoldingsTurnover", pd.NA)),
                self._parse_raw_values(_fund_operations_cat.get("totalNetAssets", pd.NA))
            ]
        }).set_index("Attributes")
