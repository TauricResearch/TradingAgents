from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/trading-analysis/$', consumers.TradingAnalysisConsumer.as_asgi()),
] 