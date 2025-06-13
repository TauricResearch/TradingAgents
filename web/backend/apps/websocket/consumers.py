import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
import jwt


class TradingAnalysisConsumer(AsyncWebsocketConsumer):
    """거래 분석 실시간 업데이트 WebSocket Consumer"""
    
    async def connect(self):
        """WebSocket 연결"""
        # JWT 토큰 인증
        user = await self.get_user_from_token()
        
        if user and user.is_authenticated:
            self.user = user
            self.user_group_name = f"user_{user.id}"
            
            # 사용자 그룹에 추가
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            
            await self.accept()
            
            # 연결 성공 메시지 전송
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'WebSocket 연결이 성공적으로 설정되었습니다.',
                'user_id': user.id
            }))
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """WebSocket 연결 해제"""
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """클라이언트로부터 메시지 수신"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', '')
            
            if message_type == 'ping':
                # 연결 상태 확인용 ping
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': text_data_json.get('timestamp')
                }))
            elif message_type == 'subscribe_analysis':
                # 특정 분석 세션 구독
                session_id = text_data_json.get('session_id')
                if session_id:
                    await self.subscribe_to_analysis(session_id)
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '잘못된 JSON 형식입니다.'
            }))
    
    async def subscribe_to_analysis(self, session_id):
        """특정 분석 세션 구독"""
        # 분석 세션이 사용자의 것인지 확인
        session_exists = await self.check_session_ownership(session_id)
        
        if session_exists:
            analysis_group = f"analysis_{session_id}"
            await self.channel_layer.group_add(
                analysis_group,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'subscription_confirmed',
                'session_id': session_id,
                'message': f'분석 세션 {session_id}에 구독되었습니다.'
            }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'subscription_failed',
                'session_id': session_id,
                'message': '해당 분석 세션에 대한 권한이 없습니다.'
            }))
    
    # 분석 관련 메시지 핸들러들
    async def trading_analysis_message(self, event):
        """분석 관련 메시지 전송"""
        message = event['message']
        await self.send(text_data=json.dumps(message))
    
    async def analysis_progress(self, event):
        """분석 진행 상황 업데이트"""
        await self.send(text_data=json.dumps(event))
    
    async def analysis_started(self, event):
        """분석 시작 알림"""
        await self.send(text_data=json.dumps(event))
    
    async def analysis_completed(self, event):
        """분석 완료 알림"""
        await self.send(text_data=json.dumps(event))
    
    async def analysis_failed(self, event):
        """분석 실패 알림"""
        await self.send(text_data=json.dumps(event))
    
    @database_sync_to_async
    def get_user_from_token(self):
        """JWT 토큰에서 사용자 정보 추출"""
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import AnonymousUser
        
        User = get_user_model()
        try:
            # URL에서 토큰 추출 (query parameter 또는 header)
            token = None
            
            # Query parameter에서 토큰 추출
            query_string = self.scope.get('query_string', b'').decode()
            if 'token=' in query_string:
                token = query_string.split('token=')[1].split('&')[0]
            
            # 헤더에서 토큰 추출
            if not token:
                headers = dict(self.scope['headers'])
                auth_header = headers.get(b'authorization', b'').decode()
                if auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
            
            if not token:
                return AnonymousUser()
            
            # JWT 토큰 검증
            try:
                # simplejwt 설정에서 올바른 서명 키와 알고리즘 가져오기
                from rest_framework_simplejwt.settings import api_settings
                
                UntypedToken(token) # 토큰 기본 구조 검증
                
                # 토큰에서 사용자 ID 추출
                decoded_token = jwt.decode(
                    token,
                    api_settings.SIGNING_KEY, # 올바른 서명 키 사용
                    algorithms=[api_settings.ALGORITHM] # 올바른 알고리즘 사용
                )
                user_id = decoded_token.get('user_id')
                
                if user_id:
                    user = User.objects.get(id=user_id)
                    return user
                    
            except (InvalidToken, TokenError, jwt.ExpiredSignatureError):
                return AnonymousUser()
            except User.DoesNotExist:
                return AnonymousUser()
                
        except Exception as e:
            print(f"WebSocket 인증 중 오류: {e}")
            return AnonymousUser()
        
        return AnonymousUser()
    
    @database_sync_to_async
    def check_session_ownership(self, session_id):
        """분석 세션 소유권 확인"""
        try:
            # 지연 import
            from apps.authentication.models import AnalysisSession
            session = AnalysisSession.objects.get(id=session_id, user=self.user)
            return True
        except AnalysisSession.DoesNotExist:
            return False 