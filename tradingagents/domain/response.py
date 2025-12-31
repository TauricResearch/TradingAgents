from dataclasses import dataclass
from typing import Optional

@dataclass
class EnqueueAnalysisResponse:
    job_id: Optional[str]
    status: str
    message: str
