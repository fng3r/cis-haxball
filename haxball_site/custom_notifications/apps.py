from django.apps import AppConfig


class CustomNotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'custom_notifications'
    verbose_name = '6. Уведомления'
    
    def ready(self):
        import custom_notifications.signals
