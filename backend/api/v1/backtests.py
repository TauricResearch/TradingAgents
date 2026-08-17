from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.deps import get_current_user
from backend.models import User
from backend.schemas import BacktestCreate
from backend.services.backtest import evaluate_saved_analyses

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("")
def run_backtest(
    body: BacktestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return evaluate_saved_analyses(db, user.id, body)
