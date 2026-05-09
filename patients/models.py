from django.conf import settings
from django.db import models
from django.utils import timezone


class PatientsModel(models.Model):
    user_profile = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10)
    dob = models.DateField()
    phone_number = models.CharField(max_length=15)
    email = models.EmailField(max_length=254, unique=True, blank=True, null=True)
    photo_uri = models.URLField(max_length=200, blank=True, null=True)
    country = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    
    created_at = models.DateTimeField(auto_now_add=True)  # Set once at creation
    updated_at = models.DateTimeField(auto_now=True)      # Updated on every save

    class Meta:
        db_table = 'patients_model'
        unique_together = ('user_profile', 'first_name', 'phone_number')

    def formatted_dob(self):
        return self.dob.strftime('%d-%m-%Y') if self.dob else None  # Returns DD-MM-YYYY format


    def __str__(self):
        return self.first_name
