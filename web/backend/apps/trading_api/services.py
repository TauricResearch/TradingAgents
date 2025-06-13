import asyncio
import datetime
from typing import Dict, List, Optional
from django.conf import settings
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
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
        
    @database_sync_to_async
    def _update_session_status(self, status: str, error_message: Optional[str] = None, final_report: Optional[str] = None):
        """세션 상태 업데이트 (비동기 안전)"""
        self.session.status = status
        now = datetime.datetime.now()
        if status == 'running':
            self.session.started_at = now
        else:
            self.session.completed_at = now
        
        if error_message:
            self.session.error_message = error_message
        if final_report:
            self.session.final_report = final_report
            
        self.session.save()

    @database_sync_to_async
    def _get_user_profile_and_key(self):
        """사용자 프로필 및 API 키 조회 (비동기 안전)"""
        profile = self.user.profile
        return profile.get_effective_openai_api_key()

    async def run_analysis(self):
        """분석 실행"""
        try:
            await self._update_session_status('running')
            
            await self._send_websocket_message({
                'type': 'analysis_started',
                'session_id': self.session.id,
                'message': '분석을 시작합니다...'
            })
            
            api_key = await self._get_user_profile_and_key()
            
            if not api_key:
                raise Exception("OpenAI API 키가 설정되지 않았습니다.")
            
            config = self._prepare_analysis_config(api_key)
            result = await self._execute_trading_analysis(config)
            
            await self._update_session_status('completed', final_report=result)
            
            await self._send_websocket_message({
                'type': 'analysis_completed',
                'session_id': self.session.id,
                'message': '분석이 완료되었습니다.',
                'result': result
            })
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            await self._update_session_status('failed', error_message=error_msg)
            
            await self._send_websocket_message({
                'type': 'analysis_failed',
                'session_id': self.session.id,
                'message': f'분석 중 오류가 발생했습니다: {error_msg}'
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
            
            # 진행 상황 콜백 함수 수정
            async def progress_callback(message_type: str, content: str, agent: str = None, step: int = 0, total: int = 0):
                # 백엔드에서 진행률 계산
                progress_percent = int((step / total) * 99) if total > 0 else 0 # 100%는 완료 시에만
                await self._send_websocket_message({
                    'type': 'analysis_progress',
                    'session_id': self.session.id,
                    'message_type': message_type,
                    'content': content,
                    'agent': agent,
                    'progress': progress_percent,
                })

            # TradingAgentsGraph 초기화 (더 상세한 예외 처리)
            try:
                trading_graph = TradingAgentsGraph(
                    config=analysis_config,
                    progress_callback=progress_callback
                )
            except Exception as e:
                raise Exception(f"TradingAgentsGraph 초기화 실패: {str(e)}")

            # 분석 입력 데이터 준비
            input_data = {
                'ticker': config['ticker'],
                'date': config['analysis_date'],
                'selected_analysts': [analyst.value for analyst in config['analysts']],
                'research_depth': config['research_depth'],
            }
            
            # 분석 실행 (실제 CLI 로직 호출)
            try:
                # 여기서 trading_graph.invoke를 비동기로 실행해야 합니다.
                # 현재 trading_graph.invoke가 동기 함수라고 가정하고,
                # asyncio.to_thread를 사용해 비동기 컨텍스트에서 실행합니다.
                result = await asyncio.to_thread(
                    trading_graph.invoke,
                    input_data
                )
                return result['final_report'] # 결과 형식에 따라 조정 필요
            except Exception as e:
                raise Exception(f"trading_graph.invoke 실행 실패: {str(e)}")

        except Exception as e:
            # 에러 메시지를 명확하게 다시 던짐
            raise Exception(f"분석 실행 중 오류: {str(e)}")
    
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
    @database_sync_to_async
    def _get_session(user, session_id):
        return AnalysisSession.objects.get(id=session_id, user=user)

    @staticmethod
    async def start_analysis(user, session_id: int):
        """분석 시작"""
        try:
            session = await TradingAnalysisManager._get_session(user, session_id)
            service = TradingAnalysisService(user, session)
            result = await service.run_analysis()
            return result
        except AnalysisSession.DoesNotExist:
            raise Exception("분석 세션을 찾을 수 없습니다.")
    
    @staticmethod
    @database_sync_to_async
    def get_user_analysis_sessions(user) -> List[AnalysisSession]:
        """사용자의 분석 세션 목록 조회"""
        return list(AnalysisSession.objects.filter(user=user).order_by('-created_at'))
    
    @staticmethod
    @database_sync_to_async
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