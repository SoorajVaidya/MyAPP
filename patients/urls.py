from django.urls import path
from . import views
from .views import SearchPatientView

urlpatterns = [
    path('profile/', views.handle_profile, name='handle_profile_create'),  # For create
    path('profile/<int:pk>/', views.handle_profile, name='handle_profile_manage'),  # For update/delete
    path('patients/search/', SearchPatientView.as_view(), name='search-patient'),
]
