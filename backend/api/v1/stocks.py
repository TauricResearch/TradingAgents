from fastapi import APIRouter, HTTPException, Query

from backend.integrations.india import catalog_name, search_catalog
from backend.integrations.market_data import classify_regime, get_market_provider
from backend.schemas import Candle, StockQuote

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search")
def search_stocks(q: str = Query("", min_length=0)):
    return {"results": search_catalog(q)}


@router.get("/{symbol}", response_model=StockQuote)
def stock_detail(symbol: str):
    try:
        quote = get_market_provider().quote(symbol)
        if not quote.name:
            quote.name = catalog_name(quote.symbol)
        return quote
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to retrieve market data: {exc}") from exc


@router.get("/{symbol}/history", response_model=list[Candle])
def stock_history(symbol: str, range: str = "6M"):
    try:
        return get_market_provider().history(symbol, range)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to retrieve market data: {exc}") from exc
