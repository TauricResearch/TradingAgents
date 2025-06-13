from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404

from .models import User, UserProfile, AnalysisSession
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    UserProfileSerializer,
    AnalysisSessionSerializer,
    CreateAnalysisSessionSerializer
)


class UserRegistrationView(APIView):
    """사용자 회원가입"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # JWT 토큰 생성
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': '회원가입이 완료되었습니다.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    """사용자 로그인"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # JWT 토큰 생성
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': '로그인이 완료되었습니다.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    """사용자 프로필 조회 및 수정"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """프로필 조회"""
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)
    
    def put(self, request):
        """프로필 수정"""
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': '프로필이 업데이트되었습니다.',
                'profile': serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserInfoView(APIView):
    """사용자 정보 조회"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class AnalysisSessionListView(generics.ListCreateAPIView):
    """분석 세션 목록 조회 및 생성"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AnalysisSession.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateAnalysisSessionSerializer
        return AnalysisSessionSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AnalysisSessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """분석 세션 상세 조회, 수정, 삭제"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AnalysisSessionSerializer
    
    def get_queryset(self):
        return AnalysisSession.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def check_openai_api_key(request):
    """OpenAI API 키 유효성 검사"""
    try:
        profile = request.user.profile
        api_key = profile.get_effective_openai_api_key()
        
        if not api_key:
            return Response({
                'valid': False,
                'message': 'OpenAI API 키가 설정되지 않았습니다.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 실제 OpenAI API 호출로 키 검증 (간단한 모델 목록 요청)
        import openai
        openai.api_key = api_key
        
        try:
            # 간단한 API 호출로 키 유효성 확인
            response = openai.models.list()
            return Response({
                'valid': True,
                'message': 'OpenAI API 키가 유효합니다.',
                'using_user_key': profile.has_openai_api_key()
            })
        except Exception as e:
            return Response({
                'valid': False,
                'message': f'OpenAI API 키가 유효하지 않습니다: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def remove_openai_api_key(request):
    """사용자의 OpenAI API 키 제거"""
    try:
        profile = request.user.profile
        profile.set_openai_api_key(None)
        profile.save()
        
        return Response({
            'message': 'OpenAI API 키가 제거되었습니다. 이제 기본 키를 사용합니다.'
        })
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 