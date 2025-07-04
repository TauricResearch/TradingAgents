from sqlmodel import Session
from analysis.domain.repository.analysis_repo import IAnalysisRepository
from ulid import ULID
from analysis.domain.analysis import Analysis as AnalysisVO
from fastapi import HTTPException, status, BackgroundTasks


class AnalysisService:
    def __init__(
        self,
        analysis_repo: IAnalysisRepository,
        db_session: Session,
        ulid: ULID
    ):
        self.analysis_repo = analysis_repo
        self.db_session = db_session
        self.ulid = ulid

    def get_analysis_list(
        self,
        member_id: str
    )->list[AnalysisVO]:
        analyses = self.analysis_repo.find_by_member_id(member_id)
        if not analyses:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
        return analyses

    