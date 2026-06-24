from fastapi import APIRouter

from api.database import get_db_connection

router = APIRouter(tags=["health"])


@router.get("/signals-ms/health")
def health():
    db = "ok"
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        db = "error"
    return {"status": "ok", "database": db}
