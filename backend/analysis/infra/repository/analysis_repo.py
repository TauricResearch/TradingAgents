from analysis.domain.repository.analysis_repo import IAnalysisRepository
from sqlmodel import Session, select
from analysis.domain.analysis import Analysis as AnalysisVO
from analysis.infra.db_models.analysis import Analysis, AnalysisStatus
from analysis.interface.dto import TradingAnalysisRequest
from utils.db_utils import row_to_dict
from sqlalchemy.orm import selectinload
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

class AnalysisRepository(IAnalysisRepository):
    def __init__(self, session: Session):
        self.session = session

    def find_by_member_id(self, member_id: str) -> list[AnalysisVO] | None:
        query = select(Analysis).where(Analysis.member_id == member_id).order_by(Analysis.created_at.desc())
        analyses = self.session.exec(query).all()
        
        if not analyses:
            return None
        
        return [AnalysisVO(**row_to_dict(analysis)) for analysis in analyses]

    def find_by_id(self, analysis_id: str) -> AnalysisVO | None:
        analysis = self.session.get(Analysis, analysis_id)
        if not analysis:
            return None
        return AnalysisVO(**row_to_dict(analysis))

    def save(self, analysis: AnalysisVO) -> AnalysisVO:
        new_analysis = Analysis(
            **analysis.model_dump()
        )
        
        self.session.add(new_analysis)
        self.session.flush()
        
        
        analysis.id = new_analysis.id
        return analysis

    def update(self, analysis_vo: AnalysisVO) -> AnalysisVO | None:
        analysis = self.session.get(Analysis, analysis_vo.id)
        logger.info(f"🔄 분석 업데이트 - Analysis ID: {analysis_vo.id}")
        if not analysis:
            return None

        # AnalysisVO의 데이터를 SQLModel 객체에 업데이트
        analysis_data = analysis_vo.model_dump(exclude_unset=True)
        
        analysis.updated_at = datetime.now()
        analysis.sqlmodel_update(analysis_data)
        
        self.session.flush()
        

        return AnalysisVO(**row_to_dict(analysis))
