from django.apps import AppConfig


class WebsocketConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.websocket'
    verbose_name = 'WebSocket 통신' 