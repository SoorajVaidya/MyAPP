from django.apps import AppConfig
from django.db.models.signals import post_save




class DynamicReportServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dynamic_report_service'

    def ready(self):
        from django.apps import apps


