from abc import ABC, abstractmethod
import pandas as _pd
from typing import Dict, List, Optional
import warnings

from ..const import _QUERY1_URL_, _SENTINEL_
from ..data import YfData
from ..ticker import Ticker

_QUERY_URL_ = f'{_QUERY1_URL_}/v1/finance'

class Domain(ABC):
    """
    Abstract base class representing a domain entity in financial data, with key attributes 
    and methods for fetching and parsing data. Derived classes must implement the `_fetch_and_parse()` method.
    """

    def __init__(self, key: str, session=None, proxy=_SENTINEL_):
        """
        Initializes the Domain object with a key, session, and proxy.

        Args:
            key (str): Unique key identifying the domain entity.
            session (Optional[requests.Session]): Session object for HTTP requests. Defaults to None.
        """
        self._key: str = key
        self.session = session
        self._data: YfData = YfData(session=session)
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            self._data._set_proxy(proxy)

        self._name: Optional[str] = None
        self._symbol: Optional[str] = None
        self._overview: Optional[Dict] = None
        self._top_companies: Optional[_pd.DataFrame] = None
        self._research_reports: Optional[List[Dict[str, str]]] = None

    @property
    def key(self) -> str:
        """
        Retrieves the key of the domain entity.

        Returns:
            str: The unique key of the domain entity.
        """
        return self._key

    @property
    def name(self) -> str:
        """
        Retrieves the name of the domain entity.

        Returns:
            str: The name of the domain entity.
        """
        self._ensure_fetched(self._name)
        return self._name

    @property
    def symbol(self) -> str:
        """
        Retrieves the symbol of the domain entity.

        Returns:
            str: The symbol representing the domain entity.
        """
        self._ensure_fetched(self._symbol)
        return self._symbol

    @property
    def ticker(self) -> Ticker:
        """
        Retrieves a Ticker object based on the domain entity's symbol.

        Returns:
            Ticker: A Ticker object associated with the domain entity.
        """
        self._ensure_fetched(self._symbol)
        return Ticker(self._symbol)

    @property
    def overview(self) -> Dict:
        """
        Retrieves the overview information of the domain entity.

        Returns:
            Dict: A dictionary containing an overview of the domain entity.
        """
        self._ensure_fetched(self._overview)
        return self._overview

    @property
    def top_companies(self) -> Optional[_pd.DataFrame]:
        """
        Retrieves the top companies within the domain entity.

        Returns:
            pandas.DataFrame: A DataFrame containing the top companies in the domain.
        """
        self._ensure_fetched(self._top_companies)
        return self._top_companies 

    @property
    def research_reports(self) -> List[Dict[str, str]]:
        """
        Retrieves research reports related to the domain entity.

        Returns:
            List[Dict[str, str]]: A list of research reports, where each report is a dictionary with metadata.
        """
        self._ensure_fetched(self._research_reports)
        return self._research_reports

    def _fetch(self, query_url) -> Dict:
        """
        Fetches data from the given query URL.

        Args:
            query_url (str): The URL used for the data query.

        Returns:
            Dict: The JSON response data from the request.
        """
        params_dict = {"formatted": "true", "withReturns": "true", "lang": "en-US", "region": "US"}
        result = self._data.get_raw_json(query_url, params=params_dict)
        return result

    def _parse_and_assign_common(self, data) -> None:
        """
        Parses and assigns common data fields such as name, symbol, overview, and top companies.

        Args:
            data (Dict): The raw data received from the API.
        """
        self._name = data.get('name')
        self._symbol = data.get('symbol')
        self._overview = self._parse_overview(data.get('overview', {}))
        self._top_companies = self._parse_top_companies(data.get('topCompanies', {}))
        self._research_reports = data.get('researchReports')

    def _parse_overview(self, overview) -> Dict:
        """
        Parses the overview data for the domain entity.

        Args:
            overview (Dict): The raw overview data.

        Returns:
            Dict: A dictionary containing parsed overview information.
        """
        return {
            "companies_count": overview.get('companiesCount', None),
            "market_cap": overview.get('marketCap', {}).get('raw', None),
            "message_board_id": overview.get('messageBoardId', None),
            "description": overview.get('description', None),
            "industries_count": overview.get('industriesCount', None),
            "market_weight": overview.get('marketWeight', {}).get('raw', None),
            "employee_count": overview.get('employeeCount', {}).get('raw', None)
        }

    def _parse_top_companies(self, top_companies) -> Optional[_pd.DataFrame]:
        """
        Parses the top companies data and converts it into a pandas DataFrame.

        Args:
            top_companies (Dict): The raw top companies data.

        Returns:
            Optional[pandas.DataFrame]: A DataFrame containing top company data, or None if no data is available.
        """
        top_companies_column = ['symbol', 'name', 'rating', 'market weight']
        top_companies_values = [(c.get('symbol'), 
                                c.get('name'), 
                                c.get('rating'), 
                                c.get('marketWeight',{}).get('raw',None)) for c in top_companies]

        if not top_companies_values: 
            return None
        
        return _pd.DataFrame(top_companies_values, columns=top_companies_column).set_index('symbol')

    @abstractmethod
    def _fetch_and_parse(self) -> None:
        """
        Abstract method for fetching and parsing domain-specific data. 
        Must be implemented by derived classes.
        """
        raise NotImplementedError("_fetch_and_parse() needs to be implemented by children classes")

    def _ensure_fetched(self, attribute) -> None:
        """
        Ensures that the given attribute is fetched by calling `_fetch_and_parse()` if the attribute is None.

        Args:
            attribute: The attribute to check and potentially fetch.
        """
        if attribute is None:
            self._fetch_and_parse()
