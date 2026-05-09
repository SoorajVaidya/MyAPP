import random
from datetime import timedelta
from django.utils.timezone import now
import pyotp
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager, Group, Permission
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Custom manager for CustomUser.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.
    Attributes:
        username (CharField): The user's username, which is not unique.
        email (EmailField): The user's email address, which is unique.
        phone_number (CharField): The user's phone number, which is unique and can be null or blank.
    """
    username = models.CharField(max_length=150, null=True, blank=True)  # Redefine username without unique constraint
    email = models.EmailField(unique=True, null=True, blank=True)

    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Remove 'username' from REQUIRED_FIELDS

    def __str__(self):
        return self.email or self.phone_number or "Unknown User"

    groups = models.ManyToManyField(
        Group,
        related_name='customuser_set',  # Change this name to avoid conflict
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions '
                  'granted to each of their groups.',
        verbose_name='groups'
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_set',  # Change this name to avoid conflict
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions'
    )


class UserProfile(models.Model):
    """
    Model representing a user profile with additional information.

    Attributes:
        user (OneToOneField): One-to-one relationship with the custom user model.
        user_name (CharField): The user's first name.
        gender (CharField): The user's gender.
        age (PositiveIntegerField): The user's age.
        phone_number (CharField): The user's phone number.
        photo_uri (CharField): The URI of the user's photo.
        created_at (DateTimeField): The timestamp when the profile was created.
        updated_at (DateTimeField): The timestamp when the profile was last updated.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    user_name = models.CharField(max_length=100, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    photo_uri = models.CharField(max_length=255, null=True, blank=True)  # Made blank=True to handle deletion
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.email  # Use email or another unique identifier from CustomUser


class MobileUser(models.Model):
    """
    Model representing a mobile user with OTP functionality.
    Attributes:
        phone_number (str): The user's phone number.
        otp_secret (str): The secret key used for generating OTPs.
    """
    phone_number = models.CharField(max_length=15, unique=True)
    otp_secret = models.CharField(max_length=32, default=pyotp.random_base32)
    last_otp = models.CharField(max_length=6, blank=True, null=True)  # New field to store OTP

    def __str__(self):
        """
        String representation of the MobileUser object.
        Returns:
            str: The phone number of the mobile user.
        """
        return self.phone_number

    last_otp = models.CharField(max_length=6, blank=True, null=True)  # New field to store OTP

    def generate_otp(self):
        """
        Generates a Time-based One-Time Password (TOTP) for the mobile user.
        Returns:str: The generated OTP.
        """
        totp = pyotp.TOTP(self.otp_secret)
        otp = totp.now()
        self.last_otp = otp
        self.save()
        return otp

    def verify_otp(self, otp):
        """
                Verifies the provided OTP against the stored secret key.
                Args:
                    otp (str): The OTP to be verified.
                Returns:
                    bool: True if the OTP is valid, False otherwise.
                """

        totp = pyotp.TOTP(self.otp_secret)
        return totp.verify(otp, valid_window=1)  # valid_window=1 allows for a 30-second window
        return self.lotp_secretast_otp == otp


class OTP(models.Model):
    email = models.EmailField()
    phone_number = models.CharField(max_length=15, default='', blank=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def generate_otp(self):
        self.otp = str(random.randint(100000, 999999))
        # Set OTP to expire 10 minutes from now
        self.expires_at = timezone.now() + timedelta(minutes=10)




def default_expiration():
    """Return the default expiration time for OTPs (1 day from now)."""
    return now() + timedelta(days=1)

class ForgotPasswordOTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)  # Link to user
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiration)  # Use a callable function

    def __str__(self):
        return f"OTP for {'email: ' + self.email if self.email else 'phone: ' + self.phone_number}"