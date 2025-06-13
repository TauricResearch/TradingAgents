from django.urls import path

app_name = 'websocket'

# WebSocket은 ASGI routing을 통해 처리되므로 HTTP URL은 없음
urlpatterns = [
    # WebSocket 관련 HTTP 엔드포인트가 필요한 경우 여기에 추가
] 