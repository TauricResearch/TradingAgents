from fastapi import HTTPException

from tradingagents.portfolio.exceptions import PortfolioError
from tradingagents.portfolio.supabase_client import SupabaseClient


async def get_current_user() -> dict[str, str]:
    # V1 (Single Tenant): Just return a hardcoded user/workspace ID
    # V2 (Multi-Tenant): Decode the JWT using supabase-py and return auth.uid()
    return {"user_id": "tenant_001", "role": "admin"}

def get_db_client() -> SupabaseClient:
    try:
        return SupabaseClient.get_instance()
    except PortfolioError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
