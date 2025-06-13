from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from asgiref.sync import sync_to_async
import asyncio
from datetime import datetime

from apps.authentication.models import AnalysisSession
from apps.authentication.serializers import AnalysisSessionSerializer, CreateAnalysisSessionSerializer
from .services import TradingAnalysisManager, TradingAnalysisService


class AnalysisConfigView(APIView):
    """분석 설정 정보 조회"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """분석 설정 옵션들 반환"""
        config = {
            'analysts': [
                {'value': 'market', 'label': 'Market Analyst', 'description': '시장 데이터 분석'},
                {'value': 'social', 'label': 'Social Analyst', 'description': '소셜 센티멘트 분석'},
                {'value': 'news', 'label': 'News Analyst', 'description': '뉴스 분석'},
                {'value': 'fundamentals', 'label': 'Fundamentals Analyst', 'description': '기본 분석'},
            ],
            'research_depths': [
                {'value': 1, 'label': 'Shallow', 'description': '빠른 분석, 적은 토론 라운드'},
                {'value': 3, 'label': 'Medium', 'description': '중간 정도 분석, 보통 토론 라운드'},
                {'value': 5, 'label': 'Deep', 'description': '깊은 분석, 많은 토론 라운드'},
            ],
            'shallow_thinkers': [
                {'value': 'gpt-4o-mini', 'label': 'GPT-4o-mini', 'description': '빠르고 효율적'},
                {'value': 'gpt-4.1-nano', 'label': 'GPT-4.1-nano', 'description': '초경량 모델'},
                {'value': 'gpt-4.1-mini', 'label': 'GPT-4.1-mini', 'description': '컴팩트 모델'},
                {'value': 'gpt-4o', 'label': 'GPT-4o', 'description': '표준 모델'},
            ],
            'deep_thinkers': [
                {'value': 'gpt-4.1-nano', 'label': 'GPT-4.1-nano', 'description': '초경량 모델'},
                {'value': 'gpt-4.1-mini', 'label': 'GPT-4.1-mini', 'description': '컴팩트 모델'},
                {'value': 'gpt-4o', 'label': 'GPT-4o', 'description': '표준 모델'},
                {'value': 'o4-mini', 'label': 'o4-mini', 'description': '추론 특화 모델 (컴팩트)'},
                {'value': 'o3-mini', 'label': 'o3-mini', 'description': '고급 추론 모델 (경량)'},
                {'value': 'o3', 'label': 'o3', 'description': '완전한 고급 추론 모델'},
                {'value': 'o1', 'label': 'o1', 'description': '최고급 추론 및 문제 해결 모델'},
            ]
        }
        
        return Response(config)


class StartAnalysisView(APIView):
    """분석 시작"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """새로운 분석 시작"""
        serializer = CreateAnalysisSessionSerializer(data=request.data)
        
        if serializer.is_valid():
            # 분석 세션 생성
            session = serializer.save(user=request.user)
            
            # 백그라운드에서 분석 실행
            # 실제 환경에서는 Celery나 다른 task queue를 사용하는 것이 좋습니다
            asyncio.create_task(self._start_analysis_async(request.user, session.id))
            
            return Response({
                'message': '분석이 시작되었습니다.',
                'session_id': session.id,
                'session': AnalysisSessionSerializer(session).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    async def _start_analysis_async(self, user, session_id):
        """비동기 분석 실행"""
        try:
            await TradingAnalysisManager.start_analysis(user, session_id)
        except Exception as e:
            print(f"분석 실행 중 오류: {e}")


class AnalysisStatusView(APIView):
    """분석 상태 조회"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, session_id):
        """특정 분석 세션의 상태 조회"""
        session = get_object_or_404(
            AnalysisSession, 
            id=session_id, 
            user=request.user
        )
        
        serializer = AnalysisSessionSerializer(session)
        return Response(serializer.data)


class CancelAnalysisView(APIView):
    """분석 취소"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, session_id):
        """분석 취소"""
        try:
            success = TradingAnalysisManager.cancel_analysis(request.user, session_id)
            
            if success:
                return Response({
                    'message': '분석이 취소되었습니다.',
                    'session_id': session_id
                })
            else:
                return Response({
                    'message': '취소할 수 없는 상태입니다.',
                    'session_id': session_id
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)


class AnalysisHistoryView(APIView):
    """분석 기록 조회"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """사용자의 분석 기록 조회"""
        sessions = TradingAnalysisManager.get_user_analysis_sessions(request.user)
        serializer = AnalysisSessionSerializer(sessions, many=True)
        
        return Response({
            'count': len(sessions),
            'results': serializer.data
        })


class AnalysisReportView(APIView):
    """분석 보고서 조회"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, session_id):
        """특정 분석 세션의 보고서 조회"""
        session = get_object_or_404(
            AnalysisSession, 
            id=session_id, 
            user=request.user
        )
        
        if session.status != 'completed':
            return Response({
                'message': '분석이 완료되지 않았습니다.',
                'status': session.status
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'session_id': session.id,
            'ticker': session.ticker,
            'analysis_date': session.analysis_date,
            'final_report': session.final_report,
            'completed_at': session.completed_at,
            'duration': (session.completed_at - session.started_at).total_seconds() if session.started_at and session.completed_at else None
        })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_analysis_options(request):
    """분석 옵션 조회 (간단한 버전)"""
    options = {
        'default_values': {
            'ticker': 'SPY',
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'analysts_selected': ['market', 'social', 'news', 'fundamentals'],
            'research_depth': 3,
            'shallow_thinker': 'gpt-4o-mini',
            'deep_thinker': 'gpt-4o'
        }
    }
    
    # 사용자 프로필의 기본값이 있다면 사용
    if hasattr(request.user, 'profile'):
        profile = request.user.profile
        options['user_preferences'] = {
            'default_ticker': profile.default_ticker,
            'preferred_research_depth': profile.preferred_research_depth,
            'preferred_shallow_thinker': profile.preferred_shallow_thinker,
            'preferred_deep_thinker': profile.preferred_deep_thinker,
        }
    
    return Response(options)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_running_analyses(request):
    """실행 중인 분석 조회"""
    running_sessions = AnalysisSession.objects.filter(
        user=request.user,
        status='running'
    )
    
    serializer = AnalysisSessionSerializer(running_sessions, many=True)
    
    return Response({
        'count': len(running_sessions),
        'results': serializer.data
    }) 