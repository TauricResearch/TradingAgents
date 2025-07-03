from sqlmodel import Session
from analysis_session.domain.repository.analysis_session_repo import IAnalysisSessionRepository

class AnalysisService:
    def __init__(
        self,
        analysis_session_repo: IAnalysisSessionRepository,
        db_session: Session
    ):
        self.analysis_session_repo = analysis_session_repo
        self.db_session = db_session