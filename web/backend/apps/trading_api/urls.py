from django.urls import path
from . import views

app_name = 'trading_api'

urlpatterns = [
    # 분석 설정 및 옵션
    path('config/', views.AnalysisConfigView.as_view(), name='analysis_config'),
    path('options/', views.get_analysis_options, name='analysis_options'),
    
    # 분석 실행
    path('start/', views.StartAnalysisView.as_view(), name='start_analysis'),
    path('status/<int:session_id>/', views.AnalysisStatusView.as_view(), name='analysis_status'),
    path('cancel/<int:session_id>/', views.CancelAnalysisView.as_view(), name='cancel_analysis'),
    
    # 분석 기록 및 결과
    path('history/', views.AnalysisHistoryView.as_view(), name='analysis_history'),
    path('report/<int:session_id>/', views.AnalysisReportView.as_view(), name='analysis_report'),
    path('running/', views.get_running_analyses, name='running_analyses'),
] 