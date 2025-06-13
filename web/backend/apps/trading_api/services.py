import asyncio
import datetime
from typing import Dict, List, Optional
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# CLI 모듈 import (경로 조정 필요)
import sys
import os
sys.path.append(os.path.join(settings.BASE_DIR.parent.parent))

from cli.models import AnalystType
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from apps.authentication.models import AnalysisSession, UserProfile


class TradingAnalysisService:
    """거래 분석 서비스"""
    
    def __init__(self, user, analysis_session: AnalysisSession):
        self.user = user
        self.session = analysis_session
        self.channel_layer = get_channel_layer()
        self.user_channel_group = f"user_{user.id}"
        
    async def run_analysis(self):
        """분석 실행"""
        try:
            # 세션 상태 업데이트
            self.session.status = 'running'
            self.session.started_at = datetime.datetime.now()
            self.session.save()
            
            # WebSocket으로 시작 알림
            await self._send_websocket_message({
                'type': 'analysis_started',
                'session_id': self.session.id,
                'message': '분석을 시작합니다...'
            })
            
            # 사용자 프로필에서 OpenAI API 키 가져오기
            profile = self.user.profile
            api_key = profile.get_effective_openai_api_key()
            
            if not api_key:
                raise Exception("OpenAI API 키가 설정되지 않았습니다.")
            
            # CLI 설정 준비
            config = self._prepare_analysis_config(api_key)
            
            # 분석 실행
            result = await self._execute_trading_analysis(config)
            
            # 결과 저장
            self.session.final_report = result
            self.session.status = 'completed'
            self.session.completed_at = datetime.datetime.now()
            self.session.save()
            
            # WebSocket으로 완료 알림
            await self._send_websocket_message({
                'type': 'analysis_completed',
                'session_id': self.session.id,
                'message': '분석이 완료되었습니다.',
                'result': result
            })
            
            return result
            
        except Exception as e:
            # 에러 처리
            self.session.status = 'failed'
            self.session.error_message = str(e)
            self.session.completed_at = datetime.datetime.now()
            self.session.save()
            
            # WebSocket으로 에러 알림
            await self._send_websocket_message({
                'type': 'analysis_failed',
                'session_id': self.session.id,
                'message': f'분석 중 오류가 발생했습니다: {str(e)}'
            })
            
            raise e
    
    def _prepare_analysis_config(self, api_key: str) -> Dict:
        """분석 설정 준비"""
        # AnalysisSession의 설정을 CLI 형식으로 변환
        analysts = []
        for analyst_str in self.session.analysts_selected:
            analysts.append(AnalystType(analyst_str))
        
        config = {
            'ticker': self.session.ticker,
            'analysis_date': self.session.analysis_date.strftime('%Y-%m-%d'),
            'analysts': analysts,
            'research_depth': self.session.research_depth,
            'shallow_thinker': self.session.shallow_thinker,
            'deep_thinker': self.session.deep_thinker,
            'openai_api_key': api_key
        }
        
        return config
    
    async def _execute_trading_analysis(self, config: Dict) -> str:
        """실제 거래 분석 실행"""
        try:
            # 기본 설정 업데이트
            analysis_config = DEFAULT_CONFIG.copy()
            analysis_config.update({
                'openai_api_key': config['openai_api_key'],
                'shallow_thinking_model': config['shallow_thinker'],
                'deep_thinking_model': config['deep_thinker'],
            })
            
            # TradingAgentsGraph 초기화
            trading_graph = TradingAgentsGraph(analysis_config)
            
            # 분석 입력 데이터 준비
            input_data = {
                'ticker': config['ticker'],
                'date': config['analysis_date'],
                'selected_analysts': [analyst.value for analyst in config['analysts']],
                'research_depth': config['research_depth'],
            }
            
            # 진행 상황 콜백 함수
            async def progress_callback(message_type: str, content: str, agent: str = None):
                await self._send_websocket_message({
                    'type': 'analysis_progress',
                    'session_id': self.session.id,
                    'message_type': message_type,
                    'content': content,
                    'agent': agent
                })
            
            # 분석 실행 (실제 CLI 로직 호출)
            # 여기서는 간단화된 버전으로 구현
            # 실제로는 trading_graph.invoke(input_data) 형태로 호출
            
            # 분석 진행 상황 시뮬레이션
            analysis_steps = [
                ("Market Analyst", "시장 데이터 분석 중..."),
                ("Social Analyst", "소셜 센티멘트 분석 중..."),
                ("News Analyst", "뉴스 분석 중..."),
                ("Fundamentals Analyst", "기본 분석 중..."),
                ("Research Manager", "연구 결과 종합 중..."),
                ("Trader", "거래 전략 수립 중..."),
                ("Portfolio Manager", "포트폴리오 최적화 중...")
            ]
            
            final_report_parts = []
            
            for agent, message in analysis_steps:
                await progress_callback("agent_update", message, agent)
                
                # 실제 분석 로직 호출 (여기서는 시뮬레이션)
                await asyncio.sleep(2)  # 실제 분석 시간 시뮬레이션
                
                # 각 단계별 결과 생성 (실제로는 trading_graph의 결과)
                step_result = f"## {agent} 분석 결과\n\n{config['ticker']} 종목에 대한 {agent.lower()} 분석을 완료했습니다.\n"
                final_report_parts.append(step_result)
            
            # 최종 보고서 생성
            final_report = "\n\n".join(final_report_parts)
            
            return final_report
            
        except Exception as e:
            raise Exception(f"분석 실행 중 오류 발생: {str(e)}")
    
    async def _send_websocket_message(self, message: Dict):
        """WebSocket으로 메시지 전송"""
        try:
            await self.channel_layer.group_send(
                self.user_channel_group,
                {
                    'type': 'trading_analysis_message',
                    'message': message
                }
            )
        except Exception as e:
            print(f"WebSocket 메시지 전송 실패: {e}")


class TradingAnalysisManager:
    """거래 분석 관리자"""
    
    @staticmethod
    def create_analysis_session(user, analysis_data: Dict) -> AnalysisSession:
        """분석 세션 생성"""
        session = AnalysisSession.objects.create(
            user=user,
            ticker=analysis_data['ticker'],
            analysis_date=analysis_data['analysis_date'],
            analysts_selected=analysis_data['analysts_selected'],
            research_depth=analysis_data['research_depth'],
            shallow_thinker=analysis_data['shallow_thinker'],
            deep_thinker=analysis_data['deep_thinker'],
        )
        return session
    
    @staticmethod
    async def start_analysis(user, session_id: int):
        """분석 시작"""
        try:
            session = AnalysisSession.objects.get(id=session_id, user=user)
            service = TradingAnalysisService(user, session)
            result = await service.run_analysis()
            return result
        except AnalysisSession.DoesNotExist:
            raise Exception("분석 세션을 찾을 수 없습니다.")
    
    @staticmethod
    def get_user_analysis_sessions(user) -> List[AnalysisSession]:
        """사용자의 분석 세션 목록 조회"""
        return AnalysisSession.objects.filter(user=user).order_by('-created_at')
    
    @staticmethod
    def cancel_analysis(user, session_id: int):
        """분석 취소"""
        try:
            session = AnalysisSession.objects.get(id=session_id, user=user)
            if session.status == 'running':
                session.status = 'cancelled'
                session.completed_at = datetime.datetime.now()
                session.save()
                return True
            return False
        except AnalysisSession.DoesNotExist:
            raise Exception("분석 세션을 찾을 수 없습니다.") 