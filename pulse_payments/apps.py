from django.apps import AppConfig

class PulsePaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pulse_payments'

    def ready(self):
        import pulse_payments.signals  # Import the signals
