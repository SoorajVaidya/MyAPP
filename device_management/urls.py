from django.urls import path
from .views import RegisterDeviceView, CheckUserRegistrationView, CheckUserDeviceView

urlpatterns = [
    path('register-device/', RegisterDeviceView.as_view(), name='register_device'),
    path('check-registration/', CheckUserRegistrationView.as_view(), name='check_registration'),
    path('check-user-device/', CheckUserDeviceView.as_view(), name='get_registered_device'),
]
