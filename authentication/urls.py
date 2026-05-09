from django.contrib.auth import views as auth_views  # Import auth_views
from django.urls import path

from . import views, otpsignup_views
from .otpsignup_views import CustomSignupViewOTP, VerifyOTPView, ResetPasswordView, ForgotPasswordView
from .utils import GenerateEmailOTP
from .views import ChangePasswordView, CustomTokenObtainPairView, google_login, logout, MakeSuperUserAPIView, \
    VerifyEmailOTP, AddEmail, GetEmailAndPhone, VerifyPhoneOTP, AddPhone

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('phone-request-otp/', views.request_otp_for_phone, name='request_otp'),#
    path('phone-verify-otp/', views.verify_otp_for_phone, name='verify_otp'),
    path('unregister/', views.unregister_user, name='unregister_user'),
    path('google/', google_login, name='google_login'),
    path('signup-view/', CustomSignupViewOTP.as_view(), name='signup-otp'),
    path('signup-verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('password-forgot-request-otp/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('logout/', logout, name='logout'),

    path('api/make-superuser/', MakeSuperUserAPIView.as_view(), name='make-superuser'),

    path('email-and-phone/', GetEmailAndPhone.as_view(), name='user-detail'),

    path('add-email/', AddEmail.as_view(), name='send-email-otp'),
    path('verify-email-otp/', VerifyEmailOTP.as_view(), name='verify-email-otp'),

    path('add-phone/', AddPhone.as_view(), name='send-phone-otp'),
    path('verify-phone-otp/', VerifyPhoneOTP.as_view(), name='verify-phone-otp'),
    
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]