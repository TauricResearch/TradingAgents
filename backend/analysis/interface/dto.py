from pydantic import BaseModel
from datetime import date
from analysis.infra.db_models.analysis import AnalysisStatus

class AnalysisSessionResponse(BaseModel):
    id : str
    ticker : str
    status : AnalysisStatus