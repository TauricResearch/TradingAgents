from fastapi import APIRouter

from backend.integrations.market_data import classify_regime, get_market_provider

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview")
def market_overview():
    provider = get_market_provider()
    try:
        indices = provider.index_quotes()
        regime = classify_regime(indices)
        return {
            "indices": [q.model_dump() for q in indices],
            "regime": regime,
            "provider": provider.name,
        }
    except Exception as exc:
        return {"indices": [], "regime": None, "error": str(exc), "provider": provider.name}
