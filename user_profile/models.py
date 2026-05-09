from django.db import models
from django.conf import settings  # Import Django settings

class UserProfile(models.Model):
    user_id = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='profile', db_column='user_id')
    user_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10)
    dob = models.DateField()
    email = models.EmailField(max_length=255, editable=False)
    phone_number = models.CharField(max_length=15)
    photo_uri = models.URLField(max_length=200, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)  # Set once at creation
    updated_at = models.DateTimeField(auto_now=True)      # Updated on every save

    class Meta:
        db_table = 'userprofile'

    def formatted_dob(self):
        """Returns DOB in DD-MM-YYYY format"""
        return self.dob.strftime('%d-%m-%Y') if self.dob else None

    def save(self, *args, **kwargs):
        if self.user_id and self.user_id.email:  # Ensure user exists
            self.email = self.user_id.email  # Copy email from user model
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user_name
