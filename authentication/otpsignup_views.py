import logging
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.views import APIView

from oohy_product.custom_responses import StandardResponse, ErrorResponse
from pulse_payments.models import Wallet
from .models import CustomUser
from .models import ForgotPasswordOTP
from .models import OTP
from .serializers import ResetPasswordSerializer
from .utils import send_otp, request_phone_otp, is_valid_email, GenerateEmailOTP

logger = logging.getLogger(__name__)


class CustomSignupViewOTP(APIView):
    """Custom Signup View."""

    def post(self, request, *args, **kwargs):
        """Handle user signup."""

        # Extracting data from request
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        email_or_phone = request.POST.get('email/phone_number')

        # Check if passwords match
        if password1 != password2:
            return ErrorResponse(errors={"password2": "Password and confirm password must be the same."}, status_code=400)

        # Check for required fields
        if not password1:
            return ErrorResponse(errors={"password1": "This field is required."}, status_code=400)

        # Check if email or phone number is provided
        if not email_or_phone:
            return ErrorResponse(errors={"email_or_phone": "Please provide either an email or phone number"},
                                 status_code=400)

        # Check if the input is an email or phone number
        is_email = email_or_phone and is_valid_email(email_or_phone)

        is_phone_number = email_or_phone and (
                email_or_phone.isdigit() or (email_or_phone.startswith('+') and email_or_phone[1:].isdigit()))

        if not is_email and not is_phone_number:
            return JsonResponse({'error': 'The provided input is neither a valid email nor a phone number.'},
                                status=400)

        # Check if email already exists
        if is_email and CustomUser.objects.filter(email=email_or_phone).exists():
            return ErrorResponse(errors={"email": "A user is already registered with this email address."},
                                 status_code=400)
        # Check if phone number already exists
        if is_phone_number and CustomUser.objects.filter(phone_number=email_or_phone).exists():
            return ErrorResponse(errors={"phone_number": "A user is already registered with this phone number."},
                                 status_code=400)

        # If the number or email is valid, proceed with OTP
        request.session['email_or_phone'] = email_or_phone
        request.session['password'] = password1

        if is_phone_number:
            otp_request = request_phone_otp(email_or_phone)

        elif is_email:
            otp_request = GenerateEmailOTP.post(email_or_phone)

        if otp_request:
            return otp_request

        return ErrorResponse(errors={"error": "Failed to send OTP"}, status_code=500)


class VerifyOTPView(APIView):
    """View to verify OTP."""

    def post(self, request, *args, **kwargs):
        # Retrieve phone number or email from the session
        email_or_phone = request.session.get('email_or_phone')
        password = request.session.get('password')  # Also get the password from the session
        otp_input = request.data.get('otp')

        # Check if email/phone or OTP is missing
        if not email_or_phone:
            return ErrorResponse(errors={"error": "Phone number or email is missing from the session"}, status_code=400)
        if not otp_input:
            return ErrorResponse(errors={"otp": "OTP is required"}, status_code=400)

        try:
            # Determine if input is phone number or email
            if email_or_phone.isdigit() or (email_or_phone.startswith('+') and email_or_phone[1:].isdigit()):
                otp_record = OTP.objects.filter(phone_number=email_or_phone).order_by('-created_at').first()
            else:
                otp_record = OTP.objects.filter(email=email_or_phone).order_by('-created_at').first()

            # Check if an OTP record was found
            if not otp_record:
                return ErrorResponse(errors={"error": "OTP not found for this phone number or email"}, status_code=400)

            # Check if OTP has expired
            if otp_record.is_expired():
                return ErrorResponse(errors={"error": "OTP has expired"}, status_code=400)

            # Validate OTP
            if otp_record.otp == otp_input:
                # OTP is valid, proceed to create the user
                user = CustomUser.objects.create(
                    phone_number=email_or_phone if (email_or_phone.isdigit() or (
                            email_or_phone.startswith('+') and email_or_phone[1:].isdigit())) else None,
                    email=email_or_phone if '@' in email_or_phone else None,
                    password=make_password(password)  # Use the password from the session
                )
                return StandardResponse(data={"user_id": user.id}, message="Registration successful", status_code=201)
            else:
                return ErrorResponse(errors={"otp": "Invalid OTP"}, status_code=400)

        except OTP.DoesNotExist:
            return ErrorResponse(errors={"error": "OTP not found for this phone number or email"}, status_code=400)


class ForgotPasswordView(APIView):
    def post(self, request, *args, **kwargs):
        email_or_phone = request.data.get('email_or_phone')

        if not email_or_phone:
            return ErrorResponse(errors={"email_or_phone": "Email or phone number is required."}, status_code=400)

        # Determine if input is an email or phone number
        is_email = '@' in email_or_phone
        is_phone_number = email_or_phone.isdigit() or (email_or_phone.startswith('+') and email_or_phone[1:].isdigit())

        if not is_email and not is_phone_number:
            return ErrorResponse(errors={"error": "Invalid email or phone number format."}, status_code=400)

        # Check if user exists with this email or phone number
        filter_kwargs = {'email': email_or_phone} if is_email else {'phone_number': email_or_phone}
        try:
            user = CustomUser.objects.get(**filter_kwargs)
        except CustomUser.DoesNotExist:
            return ErrorResponse(errors={"error": "User not found."}, status_code=404)

        # Generate OTP
        otp_value = random.randint(100000, 999999)  # Generate a random 6-digit OTP
        expires_at = timezone.now() + timedelta(minutes=5)  # OTP expiration time

        # Create OTP object in the database
        otp_instance = ForgotPasswordOTP.objects.create(
            email=user.email if is_email else None,
            phone_number=user.phone_number if is_phone_number else None,
            otp=otp_value
        )

        # Send OTP via email or phone
        if is_email:
            send_mail('Your OTP Code', f'Your OTP is {otp_value}', settings.EMAIL_HOST_USER, [user.email])
        else:
            send_otp(user.phone_number, otp_value)  # Custom function to send SMS

        return StandardResponse(message="OTP sent successfully", status_code=200)


class ResetPasswordView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp = serializer.validated_data['otp']
        password1 = serializer.validated_data['password1']

        User = get_user_model()

        try:
            otp_record = ForgotPasswordOTP.objects.filter().order_by('-created_at').first()

            if not otp_record:
                return ErrorResponse(errors={"error": "No OTP found."}, status_code=400)

            if otp_record.otp != otp:
                return ErrorResponse(errors={"error": "Invalid OTP."}, status_code=400)

            if otp_record.expires_at < timezone.now():
                return ErrorResponse(errors={"error": "OTP has expired."}, status_code=400)

            user = User.objects.get(email=otp_record.email) if otp_record.email else User.objects.get(phone_number=otp_record.phone_number)

            # Ensure that a wallet exists for the user before resetting the password
            if not hasattr(user, 'wallet'):
                Wallet.objects.create(user=user)

        except User.DoesNotExist:
            return ErrorResponse(errors={"error": "User not found."}, status_code=404)

        # Reset the password
        user.set_password(password1)
        user.save()

        otp_record.delete()

        return StandardResponse(message="Password reset successfully.", status_code=200)
