import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

import logging
from sqlmodel import Session
from analysis.domain.repository.analysis_repo import IAnalysisRepository
from ulid import ULID
from analysis.domain.analysis import Analysis as AnalysisVO
from analysis.interface.dto import TradingAnalysisRequest, AnalysisProgressUpdate
from fastapi import HTTPException, status, BackgroundTasks
import asyncio
from datetime import datetime

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from analysis.application.websocket_manager import WebSocketManager
from analysis.infra.db_models.analysis import AnalysisStatus

logger = logging.getLogger(__name__)

class AnalysisService:
    def __init__(
        self,
        analysis_repo: IAnalysisRepository,
        session: Session,
        ulid: ULID,
        websocket_manager: WebSocketManager
    ):
        self.analysis_repo = analysis_repo
        self.session = session
        self.ulid = ulid
        self.websocket_manager = websocket_manager

    def get_analysis_list(
        self,
        member_id: str
    ) -> list[AnalysisVO]:
        analyses = self.analysis_repo.find_by_member_id(member_id)
        if not analyses:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
        return analyses

    def get_analysis_by_id(
        self,
        analysis_id: str,
        member_id: str
    ) -> AnalysisVO:
        analysis = self.analysis_repo.find_by_id(analysis_id)
        if not analysis:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
        
        if analysis.member_id != member_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
            
        return analysis

    def get_analysis_sessions_by_member(
        self,
        member_id: str
    ) -> list[AnalysisVO]:
        analyses = self.analysis_repo.find_by_member_id(member_id)
        if not analyses:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
        return analyses

    def create_analysis(
        self,
        member_id: str,
        request: TradingAnalysisRequest,
        background_tasks: BackgroundTasks
    ) -> AnalysisVO:
        # 분석 요청 생성
        analysis_id = self.ulid.generate()
        now = datetime.now()
        
        analysis_vo = AnalysisVO(
            id=analysis_id,
            member_id=member_id,
            ticker=request.ticker,
            analysis_date=request.analysis_date,
            analysts_selected=[analyst.value for analyst in request.analysts],
            research_depth=request.research_depth,
            llm_provider=request.llm_provider,
            backend_url=request.backend_url,
            shallow_thinker=request.shallow_thinker,
            deep_thinker=request.deep_thinker,
            status=AnalysisStatus.PENDING,
            created_at=now,
            updated_at=now
        )
        
        saved_analysis = self.analysis_repo.save(analysis_vo)
        if not saved_analysis:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save analysis")
        
        self.session.commit()
        
        # Register analysis with websocket manager
        self.websocket_manager.register_analysis(saved_analysis.id, member_id)
        
        # 백그라운드에서 분석 실행
        background_tasks.add_task(self._run_analysis, saved_analysis.id)
        
        return saved_analysis

    async def _run_analysis(self, analysis_id: str):
        """백그라운드에서 실제 분석을 실행하는 메서드"""
        try:
            analysis = AnalysisVO(
                id=analysis_id,
                status=AnalysisStatus.RUNNING,
                updated_at=datetime.now()
            )

            analysis = self.analysis_repo.update(analysis)
            if not analysis:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
            
            await self.websocket_manager.send_analysis_update(
                analysis_id=analysis_id,
                update_type="status_changed",
                data={"status": "running", "message": "Analysis started"}
            )
            
            
            
            # TradingAgentsGraph 설정 및 실행
            if analysis:
                config = self._create_config(analysis)
            
            # 분석 실행 (실제 구현)
            await self._execute_trading_analysis(analysis_id, analysis, config)
            
            # 완료 상태로 업데이트
            completed_analysis = AnalysisVO(
                id=analysis_id,
                status=AnalysisStatus.COMPLETED,
                completed_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.analysis_repo.update(completed_analysis)
            self.session.commit()
            
            
        except Exception as e:
            now = datetime.now()
            updates = AnalysisVO(
                status=AnalysisStatus.FAILED,
                error_message=str(e),
                completed_at = now,
                updated_at = now
            )

            self.analysis_repo.update(updates)
            self.session.commit()


    def _create_config(self, analysis: AnalysisVO) -> dict:
        """분석 설정을 생성하는 메서드"""
        config = {}
        config.update({
            "max_debate_rounds": analysis.research_depth,
            "max_risk_discuss_rounds": analysis.research_depth,
            "quick_think_llm": analysis.shallow_thinker,
            "deep_think_llm": analysis.deep_thinker,
            "backend_url": analysis.backend_url,
            "llm_provider": analysis.llm_provider.lower(),
        })
        return config

    async def _execute_trading_analysis(self, analysis_id: str, analysis: AnalysisVO, config: dict):
        """실제 TradingAgentsGraph를 실행하는 메서드"""
        try:
            logger.info(f"Starting trading analysis for {analysis_id} with ticker {analysis.ticker}")
            logger.info(f"Analysts selected: {analysis.analysts_selected}")
            logger.info(f"Config: {config}")
            
            # TradingAgentsGraph 초기화
            graph = TradingAgentsGraph(
                analysis.analysts_selected,
                config=config,
                debug=True
            )
            logger.info("TradingAgentsGraph initialized successfully")
            
            # 초기 상태 생성
            init_agent_state = graph.propagator.create_initial_state(
                analysis.ticker,
                analysis.analysis_date
            )
            args = graph.propagator.get_graph_args()
            
            # 분석 실행 및 결과 처리
            logger.info("Starting graph execution...")
            trace = []
            chunk_count = 0
            async for chunk in graph.graph.astream(init_agent_state, **args):
                chunk_count += 1
                logger.info(f"Processing chunk {chunk_count}: {list(chunk.keys()) if chunk else 'Empty chunk'}")
                trace.append(chunk)
                
                # 실시간으로 분석 결과 업데이트
                await self._process_analysis_chunk(analysis_id, chunk)
            
            # 최종 결과 처리
            if trace:
                final_state = trace[-1]
                final_decision = graph.process_signal(final_state.get("final_trade_decision", ""))
                
                # 최종 보고서 생성
                final_report = self._generate_final_report(final_state)
                analysis.final_trade_decision = final_decision
                analysis.final_report = final_report
                
                # 최종 결과 저장
                updates = AnalysisVO(
                    id=analysis_id,
                    final_trade_decision=final_decision,
                    final_report=final_report
                )
                self.analysis_repo.update(updates)
                
                self.session.commit()
                
        except Exception as e:
            raise Exception(f"Analysis execution failed: {str(e)}")

    async def _process_analysis_chunk(self, analysis_id: str, chunk: dict):
        """분석 중간 결과를 처리하고 저장하는 메서드"""
        updates = {}
        
        # 개별 분석가 보고서 업데이트
        if "market_report" in chunk and chunk["market_report"]:
            updates["market_report"] = chunk["market_report"]
            
        if "sentiment_report" in chunk and chunk["sentiment_report"]:
            updates["sentiment_report"] = chunk["sentiment_report"]
            
        if "news_report" in chunk and chunk["news_report"]:
            updates["news_report"] = chunk["news_report"]
            
        if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
            updates["fundamentals_report"] = chunk["fundamentals_report"]
            
        # 팀별 의사결정 과정 업데이트
        if "investment_debate_state" in chunk and chunk["investment_debate_state"]:
            updates["investment_debate_state"] = chunk["investment_debate_state"]
            
        if "trader_investment_plan" in chunk and chunk["trader_investment_plan"]:
            updates["trader_investment_plan"] = chunk["trader_investment_plan"]
            
        if "risk_debate_state" in chunk and chunk["risk_debate_state"]:
            updates["risk_debate_state"] = chunk["risk_debate_state"]
        
        # 업데이트가 있는 경우 저장
        if updates:
            # analysis_id를 포함한 AnalysisVO 객체 생성
            updates["id"] = analysis_id
            updates_vo = AnalysisVO(**updates)
            self.analysis_repo.update(updates_vo)
            self.session.commit()

    def _generate_final_report(self, final_state: dict) -> str:
        """최종 통합 보고서를 생성하는 메서드"""
        report_parts = []
        
        # Analyst Team Reports
        if any(final_state.get(section) for section in ["market_report", "sentiment_report", "news_report", "fundamentals_report"]):
            report_parts.append("## Analyst Team Reports")
            
            if final_state.get("market_report"):
                report_parts.append(f"### Market Analysis\n{final_state['market_report']}")
            if final_state.get("sentiment_report"):
                report_parts.append(f"### Social Sentiment\n{final_state['sentiment_report']}")
            if final_state.get("news_report"):
                report_parts.append(f"### News Analysis\n{final_state['news_report']}")
            if final_state.get("fundamentals_report"):
                report_parts.append(f"### Fundamentals Analysis\n{final_state['fundamentals_report']}")
        
        # Research Team Reports
        if final_state.get("investment_debate_state"):
            report_parts.append("## Research Team Decision")
            debate_state = final_state["investment_debate_state"]
            if debate_state.get("judge_decision"):
                report_parts.append(f"{debate_state['judge_decision']}")
        
        # Trading Team Reports
        if final_state.get("trader_investment_plan"):
            report_parts.append("## Trading Team Plan")
            report_parts.append(f"{final_state['trader_investment_plan']}")
        
        # Portfolio Management Decision
        if final_state.get("risk_debate_state") and final_state["risk_debate_state"].get("judge_decision"):
            report_parts.append("## Portfolio Management Decision")
            report_parts.append(f"{final_state['risk_debate_state']['judge_decision']}")
        
        return "\n\n".join(report_parts) if report_parts else "No analysis results available."

