from django.db import models
from django.contrib.auth.models import User
from django.conf import settings


class FactorySenorList(models.Model):
    unique_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=100,default="USB", editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sensors",
        help_text="User who created this sensor"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'factory_sensor_list'

    def __str__(self):
        return self.unique_id


class RegisterSensor(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sensors")
    name = models.CharField(max_length=100, help_text="Name of the sensor")
    unique_id = models.ForeignKey(
        FactorySenorList,
        to_field='unique_id',
        on_delete=models.CASCADE,
        help_text="Unique identifier for the sensor",
        db_column='unique_id'
    )
    email = models.EmailField(max_length=254, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    is_prime_member = models.BooleanField(default=False, help_text="Indicates if the sensor user is a prime member")
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'register_sensor'

    def is_prime(self):
        """Check if the user is a prime member."""
        return self.is_prime_member

    def __str__(self):
        return f"{self.name} ({self.unique_id})"
