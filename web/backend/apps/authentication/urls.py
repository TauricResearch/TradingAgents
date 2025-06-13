from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'authentication'

urlpatterns = [
    # 인증 관련
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # 사용자 정보
    path('user/', views.UserInfoView.as_view(), name='user_info'),
    path('profile/', views.UserProfileView.as_view(), name='user_profile'),
    
    # OpenAI API 키 관리
    path('check-api-key/', views.check_openai_api_key, name='check_api_key'),
    path('remove-api-key/', views.remove_openai_api_key, name='remove_api_key'),
    
    # 분석 세션 관리
    path('sessions/', views.AnalysisSessionListView.as_view(), name='analysis_sessions'),
    path('sessions/<int:pk>/', views.AnalysisSessionDetailView.as_view(), name='analysis_session_detail'),
] 