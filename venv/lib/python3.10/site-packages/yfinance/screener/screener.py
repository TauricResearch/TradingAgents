import curl_cffi
from typing import Union
import warnings

from yfinance.const import _QUERY1_URL_, _SENTINEL_
from yfinance.data import YfData
from ..utils import dynamic_docstring, generate_list_table_from_dict_universal

from .query import EquityQuery as EqyQy
from .query import FundQuery as FndQy
from .query import QueryBase, EquityQuery, FundQuery

_SCREENER_URL_ = f"{_QUERY1_URL_}/v1/finance/screener"
_PREDEFINED_URL_ = f"{_SCREENER_URL_}/predefined/saved"

PREDEFINED_SCREENER_BODY_DEFAULTS = {
    "offset":0, "count":25, "userId":"","userIdType":"guid"
}

PREDEFINED_SCREENER_QUERIES = {
    'aggressive_small_caps': {"sortField":"eodvolume", "sortType":"desc",
                            "query": EqyQy('and', [EqyQy('is-in', ['exchange', 'NMS', 'NYQ']), EqyQy('lt', ["epsgrowth.lasttwelvemonths", 15])])},
    'day_gainers': {"sortField":"percentchange", "sortType":"DESC",
                    "query": EqyQy('and', [EqyQy('gt', ['percentchange', 3]), EqyQy('eq', ['region', 'us']), EqyQy('gte', ['intradaymarketcap', 2000000000]), EqyQy('gte', ['intradayprice', 5]), EqyQy('gt', ['dayvolume', 15000])])},
    'day_losers': {"sortField":"percentchange", "sortType":"ASC",
                    "query": EqyQy('and', [EqyQy('lt', ['percentchange', -2.5]), EqyQy('eq', ['region', 'us']), EqyQy('gte', ['intradaymarketcap', 2000000000]), EqyQy('gte', ['intradayprice', 5]), EqyQy('gt', ['dayvolume', 20000])])},
    'growth_technology_stocks': {"sortField":"eodvolume", "sortType":"desc",
                                "query": EqyQy('and', [EqyQy('gte', ['quarterlyrevenuegrowth.quarterly', 25]), EqyQy('gte', ['epsgrowth.lasttwelvemonths', 25]), EqyQy('eq', ['sector', 'Technology']), EqyQy('is-in', ['exchange', 'NMS', 'NYQ'])])},
    'most_actives': {"sortField":"dayvolume", "sortType":"DESC",
                    "query": EqyQy('and', [EqyQy('eq', ['region', 'us']), EqyQy('gte', ['intradaymarketcap', 2000000000]), EqyQy('gt', ['dayvolume', 5000000])])},
    'most_shorted_stocks': {"count":25, "offset":0, "sortField":"short_percentage_of_shares_outstanding.value", "sortType":"DESC", 
                            "query": EqyQy('and', [EqyQy('eq', ['region', 'us']), EqyQy('gt', ['intradayprice', 1]), EqyQy('gt', ['avgdailyvol3m', 200000])])},
    'small_cap_gainers': {"sortField":"eodvolume", "sortType":"desc", 
                        "query": EqyQy("and", [EqyQy("lt", ["intradaymarketcap",2000000000]), EqyQy("is-in", ["exchange", "NMS", "NYQ"])])},
    'undervalued_growth_stocks': {"sortType":"DESC", "sortField":"eodvolume", 
                                "query": EqyQy('and', [EqyQy('btwn', ['peratio.lasttwelvemonths', 0, 20]), EqyQy('lt', ['pegratio_5y', 1]), EqyQy('gte', ['epsgrowth.lasttwelvemonths', 25]), EqyQy('is-in', ['exchange', 'NMS', 'NYQ'])])},
    'undervalued_large_caps': {"sortField":"eodvolume", "sortType":"desc", 
                            "query": EqyQy('and', [EqyQy('btwn', ['peratio.lasttwelvemonths', 0, 20]), EqyQy('lt', ['pegratio_5y', 1]), EqyQy('btwn', ['intradaymarketcap', 10000000000, 100000000000]), EqyQy('is-in', ['exchange', 'NMS', 'NYQ'])])},
    'conservative_foreign_funds': {"sortType":"DESC", "sortField":"fundnetassets",
                                "query": FndQy('and', [FndQy('is-in', ['categoryname', 'Foreign Large Value', 'Foreign Large Blend', 'Foreign Large Growth', 'Foreign Small/Mid Growth', 'Foreign Small/Mid Blend', 'Foreign Small/Mid Value']), FndQy('is-in', ['performanceratingoverall', 4, 5]), FndQy('lt', ['initialinvestment', 100001]), FndQy('lt', ['annualreturnnavy1categoryrank', 50]), FndQy('is-in', ['riskratingoverall', 1, 2, 3]), FndQy('eq', ['exchange', 'NAS'])])},
    'high_yield_bond': {"sortType":"DESC", "sortField":"fundnetassets",
                        "query": FndQy('and', [FndQy('is-in', ['performanceratingoverall', 4, 5]), FndQy('lt', ['initialinvestment', 100001]), FndQy('lt', ['annualreturnnavy1categoryrank', 50]), FndQy('is-in', ['riskratingoverall', 1, 2, 3]), FndQy('eq', ['categoryname', 'High Yield Bond']), FndQy('eq', ['exchange', 'NAS'])])},
    'portfolio_anchors': {"sortType":"DESC", "sortField":"fundnetassets",
                        "query": FndQy('and', [FndQy('eq', ['categoryname', 'Large Blend']), FndQy('is-in', ['performanceratingoverall', 4, 5]), FndQy('lt', ['initialinvestment', 100001]), FndQy('lt', ['annualreturnnavy1categoryrank', 50]), FndQy('eq', ['exchange', 'NAS'])])},
    'solid_large_growth_funds': {"sortType":"DESC", "sortField":"fundnetassets",
                                "query": FndQy('and', [FndQy('eq', ['categoryname', 'Large Growth']), FndQy('is-in', ['performanceratingoverall', 4, 5]), FndQy('lt', ['initialinvestment', 100001]), FndQy('lt', ['annualreturnnavy1categoryrank', 50]), FndQy('eq', ['exchange', 'NAS'])])},
    'solid_midcap_growth_funds': {"sortType":"DESC", "sortField":"fundnetassets",
                                "query": FndQy('and', [FndQy('eq', ['categoryname', 'Mid-Cap Growth']), FndQy('is-in', ['performanceratingoverall', 4, 5]), FndQy('lt', ['initialinvestment', 100001]), FndQy('lt', ['annualreturnnavy1categoryrank', 50]), FndQy('eq', ['exchange', 'NAS'])])},
    'top_mutual_funds': {"sortType":"DESC", "sortField":"percentchange",
                        "query": FndQy('and', [FndQy('gt', ['intradayprice', 15]), FndQy('is-in', ['performanceratingoverall', 4, 5]), FndQy('gt', ['initialinvestment', 1000]), FndQy('eq', ['exchange', 'NAS'])])}
}

@dynamic_docstring({"predefined_screeners": generate_list_table_from_dict_universal(PREDEFINED_SCREENER_QUERIES, bullets=True, title='Predefined queries (Dec-2024)')})
def screen(query: Union[str, EquityQuery, FundQuery],
            offset: int = None, 
            size: int = None,
            count: int = None,
            sortField: str = None, 
            sortAsc: bool = None,
            userId: str = None, 
            userIdType: str = None, 
            session = None, proxy = _SENTINEL_):
    """
    Run a screen: predefined query, or custom query.

    :Parameters:
        * Defaults only apply if query = EquityQuery or FundQuery
        query : str | Query:
            The query to execute, either name of predefined or custom query.
            For predefined list run yf.PREDEFINED_SCREENER_QUERIES.keys()
        offset : int
            The offset for the results. Default 0.
        size : int
            number of results to return. Default 100, maximum 250 (Yahoo)
            Use count instead for predefined queries.
        count : int
            number of results to return. Default 25, maximum 250 (Yahoo)
            Use size instead for custom queries.
        sortField : str
            field to sort by. Default "ticker"
        sortAsc : bool
            Sort ascending? Default False
        userId : str
            The user ID. Default empty.
        userIdType : str
            Type of user ID (e.g., "guid"). Default "guid".

    Example: predefined query
        .. code-block:: python

            import yfinance as yf
            response = yf.screen("aggressive_small_caps")

    Example: custom query
        .. code-block:: python

            import yfinance as yf
            from yfinance import EquityQuery
            q = EquityQuery('and', [
                   EquityQuery('gt', ['percentchange', 3]), 
                   EquityQuery('eq', ['region', 'us'])
            ])
            response = yf.screen(q, sortField = 'percentchange', sortAsc = True)

    To access predefineds query code
        .. code-block:: python

            import yfinance as yf
            query = yf.PREDEFINED_SCREENER_QUERIES['aggressive_small_caps']

    {predefined_screeners}
    """

    if proxy is not _SENTINEL_:
        warnings.warn("Set proxy via new config function: yf.set_config(proxy=proxy)", DeprecationWarning, stacklevel=2)
        _data = YfData(session=session, proxy=proxy)
    else:
        _data = YfData(session=session)

    # Only use defaults when user NOT give a predefined, because
    # Yahoo's predefined endpoint auto-applies defaults. Also,
    # that endpoint might be ignoring these fields.
    defaults = {
        'offset': 0,
        'count': 25,
        'sortField': 'ticker',
        'sortAsc': False,
        'userId': "",
        'userIdType': "guid"
    }

    if count is not None and count > 250:
        raise ValueError("Yahoo limits query count to 250, reduce count.")

    if size is not None and size > 250:
        raise ValueError("Yahoo limits query size to 250, reduce size.")

    if offset is not None and isinstance(query, str):
        # offset ignored by predefined API so switch to other API
        post_query = PREDEFINED_SCREENER_QUERIES[query]
        query = post_query['query']
        # use predefined's attributes if user not specified
        if sortField is None:
            sortField = post_query['sortField']
        if sortAsc is None:
            sortAsc = post_query['sortType'].lower() == 'asc'
        # and don't use defaults
        defaults = {}

    fields = {'offset': offset, 'count': count, "size": size, 'sortField': sortField, 'sortAsc': sortAsc, 'userId': userId, 'userIdType': userIdType}

    params_dict = {"corsDomain": "finance.yahoo.com", "formatted": "false", "lang": "en-US", "region": "US"}

    post_query = None
    if isinstance(query, str):
        # post_query = PREDEFINED_SCREENER_QUERIES[query]
        # Switch to Yahoo's predefined endpoint

        if size is not None:
            warnings.warn("Screen 'size' argument is deprecated for predefined screens, set 'count' instead.", DeprecationWarning, stacklevel=2)
            count = size
            size = None
            fields['count'] = fields['size']
            del fields['size']

        params_dict['scrIds'] = query
        for k,v in fields.items():
            if v is not None:
                params_dict[k] = v
        resp = _data.get(url=_PREDEFINED_URL_, params=params_dict)
        try:
            resp.raise_for_status()
        except curl_cffi.requests.exceptions.HTTPError:
            if query not in PREDEFINED_SCREENER_QUERIES:
                print(f"yfinance.screen: '{query}' is probably not a predefined query.")
            raise
        return resp.json()["finance"]["result"][0]

    elif isinstance(query, QueryBase):
        # Prepare other fields
        for k in defaults:
            if k not in fields or fields[k] is None:
                fields[k] = defaults[k]
        fields['sortType'] = 'ASC' if fields['sortAsc'] else 'DESC'
        del fields['sortAsc']

        post_query = fields
        post_query['query'] = query

    else:
        raise ValueError(f'Query must be type str or QueryBase, not "{type(query)}"')

    if query is None:
        raise ValueError('No query provided')

    if isinstance(post_query['query'], EqyQy):
        post_query['quoteType'] = 'EQUITY'
    elif isinstance(post_query['query'], FndQy):
        post_query['quoteType'] = 'MUTUALFUND'
    post_query['query'] = post_query['query'].to_dict()

    # Fetch
    response = _data.post(_SCREENER_URL_, 
                            body=post_query, 
                            params=params_dict)
    response.raise_for_status()
    return response.json()['finance']['result'][0]
