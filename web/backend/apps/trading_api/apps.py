from django.apps import AppConfig


class TradingApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trading_api'
    verbose_name = '거래 분석 API' 