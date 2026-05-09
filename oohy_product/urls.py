"""
URL configuration for oohy_product project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from allauth.account.views import LogoutView
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings



urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/accounts/', include('authentication.urls')),
    path('auth/', include('social_django.urls', namespace='social')),
    path('logout', LogoutView.as_view()),
    path('api/v1/user_profile/', include('user_profile.urls')),
    path('api/v1/patient_profile/', include('patients.urls')),
    path('api/v1/pulse_service/', include('pulse_service.urls')),
    path('api/v1/pulse_payments/', include('pulse_payments.urls')),
    path('api/v1/report_service/', include('report_service.urls')),
    path('api/v1/device_management/', include('device_management.urls')),
    path('api/v1/dynamic-report-service/', include('dynamic_report_service.urls')),

] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

