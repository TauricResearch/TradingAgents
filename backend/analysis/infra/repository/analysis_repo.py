from analysis.domain.repository.analysis_repo import IAnalysisRepository
from sqlmodel import Session, select
from analysis.domain.analysis import Analysis as AnalysisVO
from analysis.infra.db_models.analysis import Analysis
from utils.db_utils import row_to_dict
from sqlalchemy.orm import selectinload
from datetime import datetime
import uuid

class AnalysisRepository(IAnalysisRepository):
    def __init__(self, session: Session):
        self.session = session

    def find_by_member_id(self, member_id: str) -> list[AnalysisVO] | None:
        query = select(Analysis).where(Analysis.member_id == member_id)
        analyses = self.session.exec(query).all()
        
        if not analyses:
            return None
        
        return [AnalysisVO(**row_to_dict(analysis)) for analysis in analyses]


    def update(self, analysis_id: str, updates: AnalysisVO) -> AnalysisVO | None:
        analysis : Analysis | None = self.session.get(Analysis, analysis_id)
        if not analysis:
            return None

        analysis_data = updates.model_dump(exclude_unset=True)
        analysis.sqlmodel_dump(analysis_data)
        self.session.add(analysis)
        self.session.flush()
        self.session.refresh(analysis)

        return AnalysisVO(**row_to_dict(analysis))
