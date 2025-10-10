from __future__ import print_function

import pandas as _pd
from typing import Dict, Optional
import warnings

from ..const import SECTOR_INDUSTY_MAPPING_LC, _SENTINEL_
from ..data import YfData
from ..utils import dynamic_docstring, generate_list_table_from_dict, get_yf_logger

from .domain import Domain, _QUERY_URL_

class Sector(Domain):
    """
    Represents a financial market sector and allows retrieval of sector-related data 
    such as top ETFs, top mutual funds, and industry data.
    """

    def __init__(self, key, session=None, proxy=_SENTINEL_):
        """
        Args:
            key (str): The key representing the sector.
            session (requests.Session, optional): A session for making requests. Defaults to None.
            proxy (dict, optional): A dictionary containing proxy settings for the request. Defaults to None.
        
        .. seealso::
   
            :attr:`Sector.industries <yfinance.Sector.industries>`
                Map of sector and industry
        """
        if proxy is not _SENTINEL_:
            warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
            YfData(session=session, proxy=proxy)

        super(Sector, self).__init__(key, session)
        self._query_url: str = f'{_QUERY_URL_}/sectors/{self._key}'
        self._top_etfs: Optional[Dict] = None
        self._top_mutual_funds: Optional[Dict] = None
        self._industries: Optional[_pd.DataFrame] = None

    def __repr__(self):
        """
        Returns the string representation of the Sector object.

        Returns:
            str: A string representation of the object.
        """
        return f'yfinance.Sector object <{self._key}>'
    
    @property
    def top_etfs(self) -> Dict[str, str]:
        """
        Gets the top ETFs for the sector.

        Returns:
            Dict[str, str]: A dictionary of ETF symbols and names.
        """
        self._ensure_fetched(self._top_etfs)
        return self._top_etfs

    @property
    def top_mutual_funds(self) -> Dict[str, str]:
        """
        Gets the top mutual funds for the sector.

        Returns:
            Dict[str, str]: A dictionary of mutual fund symbols and names.
        """
        self._ensure_fetched(self._top_mutual_funds)
        return self._top_mutual_funds

    @dynamic_docstring({"sector_industry": generate_list_table_from_dict(SECTOR_INDUSTY_MAPPING_LC,bullets=True)})
    @property
    def industries(self) -> _pd.DataFrame:
        """
        Gets the industries within the sector.

        Returns:
            pandas.DataFrame: A DataFrame with industries' key, name, symbol, and market weight.

        {sector_industry}
        """
        self._ensure_fetched(self._industries)
        return self._industries
    
    def _parse_top_etfs(self, top_etfs: Dict) -> Dict[str, str]:
        """
        Parses top ETF data from the API response.

        Args:
            top_etfs (Dict): The raw ETF data from the API response.

        Returns:
            Dict[str, str]: A dictionary of ETF symbols and names.
        """
        return {e.get('symbol'): e.get('name') for e in top_etfs}

    def _parse_top_mutual_funds(self, top_mutual_funds: Dict) -> Dict[str, str]:
        """
        Parses top mutual funds data from the API response.

        Args:
            top_mutual_funds (Dict): The raw mutual fund data from the API response.

        Returns:
            Dict[str, str]: A dictionary of mutual fund symbols and names.
        """
        return {e.get('symbol'): e.get('name') for e in top_mutual_funds}
    
    def _parse_industries(self, industries: Dict) -> _pd.DataFrame:
        """
        Parses industry data from the API response into a DataFrame.

        Args:
            industries (Dict): The raw industry data from the API response.

        Returns:
            pandas.DataFrame: A DataFrame containing industry key, name, symbol, and market weight.
        """
        industries_column = ['key','name','symbol','market weight']
        industries_values = [(i.get('key'),
                              i.get('name'),
                              i.get('symbol'),
                              i.get('marketWeight',{}).get('raw', None)
                              ) for i in industries if i.get('name') != 'All Industries']
        return _pd.DataFrame(industries_values, columns=industries_column).set_index('key')

    def _fetch_and_parse(self) -> None:
        """
        Fetches and parses sector data from the API.

        Fetches data for the sector and parses the top ETFs, top mutual funds, 
        and industries within the sector. Stores the parsed data in the corresponding
        attributes `_top_etfs`, `_top_mutual_funds`, and `_industries`.

        Raises:
            Exception: If fetching or parsing the sector data fails.
        """
        result = None
        
        try:
            result = self._fetch(self._query_url)
            data = result['data']
            self._parse_and_assign_common(data)

            self._top_etfs = self._parse_top_etfs(data.get('topETFs', {}))
            self._top_mutual_funds = self._parse_top_mutual_funds(data.get('topMutualFunds', {}))
            self._industries = self._parse_industries(data.get('industries', {}))

        except Exception as e:
            logger = get_yf_logger()
            logger.error(f"Failed to get sector data for '{self._key}' reason: {e}")
            logger.debug("Got response: ")
            logger.debug("-------------")
            logger.debug(f" {result}")
            logger.debug("-------------")
