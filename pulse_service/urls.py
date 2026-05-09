from django.urls import path, include
from .views import AnalysePulseView, ChangePatternAPIView, UploadObservationsView, PulseDataSymptomsCreateAPIView, PreAnalysePulseView, \
    PulseLogView, PostAnalysePulseView
from rest_framework.routers import DefaultRouter



urlpatterns = [
    path('pre-analyse_pulse/', PreAnalysePulseView.as_view(), name='pre-analyse_pulse'),
    path('post-analyse_pulse/', PostAnalysePulseView.as_view(), name='post-analyse_pulse'),
    path('analyse_pulse/', AnalysePulseView.as_view(), name='analyse_pulse'),
    path('upload_observations/<int:pulse_id>/', UploadObservationsView.as_view(), name='upload_observations'),
    path('upload_symptoms/<int:pulse_id>/', PulseDataSymptomsCreateAPIView.as_view(), name='pulse_data_symptoms_create'),
    path('pulse-log/', PulseLogView.as_view(), name='pulse-log-create'),
    
    path('single-seed-protocol/', ChangePatternAPIView.as_view(), name='single-seed-protocol'),

]




