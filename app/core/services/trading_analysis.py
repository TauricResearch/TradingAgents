import asyncio
import datetime
import json
from typing import Dict, List, Optional
from sqlmodel import Session, select
from app.domain.models import User, AnalysisSession, AnalysisStatus
from app.core.schemas.analysis import AnalysisSessionCreate
from app.core.config import settings
from cli.models import AnalystType
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from app.api.deps import get_db
from app.core.websocket_manager import WebSocketManager

class TradingAnalysisService:
    def __init__(self, user: User, db: Session):
        self.user = user
        self.db = db
        self.websocket_manager = WebSocketManager()

    async def run_analysis(self, session_id: int):
        """분석 실행"""
        session = self.get_session(session_id=session_id)
        if not session:
            return

        try:
            session.status = AnalysisStatus.RUNNING
            session.started_at = datetime.datetime.utcnow()
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)

            await self.websocket_manager.send_to_user(
                self.user.id,
                {
                    'type': 'analysis_started',
                    'session_id': session.id,
                    'message': '분석을 시작합니다...'
                }
            )

            # Prepare config for TradingAgentsGraph
            config = DEFAULT_CONFIG.copy()
            config.update({
                'openai_api_key': settings.OPENAI_API_KEY,
                'llm_provider': session.llm_provider,
                'backend_url': session.backend_url,
                'shallow_thinking_model': session.shallow_thinker,
                'deep_thinking_model': session.deep_thinker,
            })

            # Progress callback for websocket
            async def progress_callback(message_type: str, content: str, agent: str = None, step: int = 0, total: int = 0):
                progress_percent = int((step / total) * 99) if total > 0 else 0
                await self.websocket_manager.send_to_user(self.user.id, {
                    'type': 'analysis_progress',
                    'session_id': session.id,
                    'message_type': message_type,
                    'content': content,
                    'agent': agent,
                    'progress': progress_percent,
                })

            trading_graph = TradingAgentsGraph(
                config=config,
                selected_analysts=session.analysts_selected,
            )
            
            input_data = {
                'company_of_interest': session.ticker,
                'trade_date': session.analysis_date.strftime('%Y-%m-%d'),
            }

            final_state, result = await asyncio.to_thread(
                trading_graph.propagate,
                input_data['company_of_interest'],
                input_data['trade_date']
            )

            session.status = AnalysisStatus.COMPLETED
            session.completed_at = datetime.datetime.utcnow()
            session.final_report = json.dumps(final_state) # Store full state as JSON
            self.db.add(session)
            self.db.commit()

            await self.websocket_manager.send_to_user(
                self.user.id,
                {
                    'type': 'analysis_completed',
                    'session_id': session.id,
                    'message': '분석이 완료되었습니다.',
                    'result': result
                }
            )

        except Exception as e:
            session.status = AnalysisStatus.FAILED
            session.error_message = str(e)
            self.db.add(session)
            self.db.commit()
            await self.websocket_manager.send_to_user(
                self.user.id,
                {
                    'type': 'analysis_failed',
                    'session_id': session.id,
                    'message': f'분석 중 오류가 발생했습니다: {str(e)}'
                }
            )

    def create_session(self, *, analysis_in: AnalysisSessionCreate) -> AnalysisSession:
        session = AnalysisSession(
            **analysis_in.dict(),
            user_id=self.user.id,
            analysis_date=datetime.date.today()
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, *, session_id: int) -> Optional[AnalysisSession]:
        statement = select(AnalysisSession).where(AnalysisSession.id == session_id, AnalysisSession.user_id == self.user.id)
        return self.db.exec(statement).first()

    def get_user_sessions(self, *, skip: int = 0, limit: int = 100) -> List[AnalysisSession]:
        statement = select(AnalysisSession).where(AnalysisSession.user_id == self.user.id).order_by(AnalysisSession.created_at.desc()).offset(skip).limit(limit)
        return self.db.exec(statement).all()
