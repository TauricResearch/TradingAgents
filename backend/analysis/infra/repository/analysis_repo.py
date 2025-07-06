from analysis.domain.repository.analysis_repo import IAnalysisRepository
from sqlmodel import Session, select
from analysis.domain.analysis import Analysis as AnalysisVO
from analysis.infra.db_models.analysis import Analysis, AnalysisStatus
from analysis.interface.dto import TradingAnalysisRequest
from utils.db_utils import row_to_dict
from sqlalchemy.orm import selectinload
from datetime import datetime, date

class AnalysisRepository(IAnalysisRepository):
    def __init__(self, session: Session):
        self.session = session

    def find_by_member_id(self, member_id: str) -> list[AnalysisVO] | None:
        query = select(Analysis).where(Analysis.member_id == member_id)
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
            id=analysis.id,
            member_id=analysis.member_id,
            ticker=analysis.ticker,
            analysis_date=date.fromisoformat(analysis.analysis_date),
            analysts_selected=analysis.analysts_selected,
            research_depth=analysis.research_depth,
            llm_provider=analysis.llm_provider,
            backend_url=analysis.backend_url,
            shallow_thinker=analysis.shallow_thinker,
            deep_thinker=analysis.deep_thinker,
            status=analysis.status,
            market_report=analysis.market_report,
            sentiment_report=analysis.sentiment_report,
            news_report=analysis.news_report,
            fundamentals_report=analysis.fundamentals_report,
            investment_debate_state=analysis.investment_debate_state,
            trader_investment_plan=analysis.trader_investment_plan,
            risk_debate_state=analysis.risk_debate_state,
            final_trade_decision=analysis.final_trade_decision,
            final_report=analysis.final_report,
            error_message=analysis.error_message,
            completed_at=analysis.completed_at,
            created_at=analysis.created_at,
            updated_at=analysis.updated_at
        )
        
        self.session.add(new_analysis)
        self.session.flush()
        self.session.refresh(new_analysis)
        
        analysis.id = new_analysis.id
        return analysis

    def update(self, analysis_vo: AnalysisVO) -> AnalysisVO | None:
        analysis = self.session.get(Analysis, analysis_vo.id)
        if not analysis:
            return None

        # AnalysisVO의 데이터를 SQLModel 객체에 업데이트
        vo_data = analysis_vo.sqlmodel_dump(exclude_unset=True)
        for key, value in vo_data.items():
            if hasattr(analysis, key) and key != 'id':  # id는 변경하지 않음
                setattr(analysis, key, value)
        
        analysis.updated_at = datetime.now()
        self.session.add(analysis)
        self.session.flush()
        self.session.refresh(analysis)

        return AnalysisVO(**row_to_dict(analysis))
