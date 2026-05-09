# from datetime import timezone

from datetime import timedelta
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

CustomUser = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    email_or_phone = serializers.CharField(required=True)

    def validate(self, attrs):
        errors = {}
        email_or_phone = attrs.get('email_or_phone')
        password = attrs.get('password', '')

        # Check for blank email_or_phone and password
        if not email_or_phone:
            errors['email_or_phone'] = {
                'message': 'This field cannot be blank.',
                'code': 'field_blank'
            }
        if not password:
            errors['password'] = {
                'message': 'Password field cannot be blank.',
                'code': 'password_blank'
            }

        # If there are errors, raise ValidationError
        if errors:
            raise ValidationError(errors)

        # Check if it's an email or phone number
        if '@' in email_or_phone:
            # Email case
            user_query = {'email': email_or_phone}
        else:
            # Phone number case
            user_query = {'phone_number': email_or_phone}

        # Try to get the user based on the email or phone number
        try:
            user = CustomUser.objects.get(**user_query)
        except CustomUser.DoesNotExist:
            raise AuthenticationFailed({'email_or_phone': 'No user found with this email or phone number.'})

        # Check if the password is correct
        if not user.check_password(password):
            raise AuthenticationFailed('Invalid password.')
        # Check if user is active
        if not user.is_active:
            raise ValidationError({
                'user': {
                    'message': 'User account is inactive.',
                    'code': 'user_inactive'
                }
            })

        # Generate tokens
        refresh = self.get_token(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token)
        }

        return data


class ResetPasswordSerializer(serializers.Serializer):
    otp = serializers.CharField(required=True)
    password1 = serializers.CharField(required=True)
    password2 = serializers.CharField(required=True)

    def validate(self, attrs):
        # Check if passwords match
        if attrs['password1'] != attrs['password2']:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs


def save(self, *args, **kwargs):
    if not self.expires_at:
        self.expires_at = timezone.now() + timedelta(minutes=5)  # Example expiration time
    super().save(*args, **kwargs)


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['email', 'phone_number']
        
        


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password1 = serializers.CharField(required=True)
    new_password2 = serializers.CharField(required=True)

    def validate(self, attrs):
        user = self.context['request'].user

        # Verify that the old password is correct
        if not user.check_password(attrs['old_password']):
            raise serializers.ValidationError("Old password is incorrect.")

        # Check if the new passwords match
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError("New passwords do not match.")

        return attrs
