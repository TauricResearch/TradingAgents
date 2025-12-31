from dataclasses import dataclass
from enum import Enum
from typing import Optional
import time


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AnalysisMeta:
    job_id: str
    user_id: str
    symbol: str
    status: AnalysisStatus
    trade_date: str # "trade_date": final_state["trade_date"],
    updated_at: float
    created_at: float = time.time()

    @staticmethod
    def new(job_id: str, user_id: str, symbol: str, trade_date: str) -> "AnalysisMeta":
        return AnalysisMeta(
            job_id=job_id,
            user_id=user_id,
            symbol=symbol,
            status=AnalysisStatus.PENDING,
            trade_date=trade_date,
            updated_at=time.time(),
            created_at=time.time(),
        )
