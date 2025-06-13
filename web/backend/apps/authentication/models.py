from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet
from django.conf import settings
import base64
import os


class User(AbstractUser):
    """확장된 사용자 모델"""
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']


class UserProfile(models.Model):
    """사용자 프로필 및 API 키 관리"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # 암호화된 OpenAI API 키 저장
    encrypted_openai_api_key = models.TextField(blank=True, null=True)
    
    # 기본 설정
    default_ticker = models.CharField(max_length=10, default='SPY')
    preferred_research_depth = models.IntegerField(default=3, choices=[
        (1, 'Shallow'),
        (3, 'Medium'),
        (5, 'Deep')
    ])
    preferred_shallow_thinker = models.CharField(max_length=50, default='gpt-4o-mini')
    preferred_deep_thinker = models.CharField(max_length=50, default='gpt-4o')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    @staticmethod
    def _get_cipher_key():
        """암호화/복호화용 키 생성"""
        # Django SECRET_KEY를 기반으로 암호화 키 생성
        key = base64.urlsafe_b64encode(settings.SECRET_KEY[:32].encode())
        return Fernet(key)
    
    def set_openai_api_key(self, api_key):
        """OpenAI API 키를 암호화하여 저장"""
        if api_key:
            cipher = self._get_cipher_key()
            encrypted_key = cipher.encrypt(api_key.encode())
            self.encrypted_openai_api_key = base64.urlsafe_b64encode(encrypted_key).decode()
        else:
            self.encrypted_openai_api_key = None
    
    def get_openai_api_key(self):
        """저장된 OpenAI API 키를 복호화하여 반환"""
        if not self.encrypted_openai_api_key:
            return None
        
        try:
            cipher = self._get_cipher_key()
            encrypted_key = base64.urlsafe_b64decode(self.encrypted_openai_api_key.encode())
            decrypted_key = cipher.decrypt(encrypted_key)
            return decrypted_key.decode()
        except Exception:
            return None
    
    def has_openai_api_key(self):
        """사용자가 OpenAI API 키를 설정했는지 확인"""
        return bool(self.encrypted_openai_api_key)
    
    def get_effective_openai_api_key(self):
        """
        사용자 API 키가 있으면 사용자 키를, 없으면 개발자 기본 키를 반환
        """
        user_key = self.get_openai_api_key()
        if user_key:
            return user_key
        
        # 개발자가 등록한 기본 키 사용
        return getattr(settings, 'OPENAI_API_KEY', '')


class AnalysisSession(models.Model):
    """분석 세션 관리"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analysis_sessions')
    
    # 분석 파라미터
    ticker = models.CharField(max_length=10)
    analysis_date = models.DateField()
    analysts_selected = models.JSONField()  # 선택된 분석가들
    research_depth = models.IntegerField()
    shallow_thinker = models.CharField(max_length=50)
    deep_thinker = models.CharField(max_length=50)
    
    # 세션 상태
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='pending')
    
    # 결과 저장
    final_report = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    # 시간 추적
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'analysis_sessions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.ticker} ({self.status})" 