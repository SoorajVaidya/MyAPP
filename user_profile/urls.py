from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.handle_profile, name='handle_profile'),  # For create
]
