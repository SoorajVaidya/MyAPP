# utils.py in oohy_mobile_auth
import random
import re
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.views import APIView
from twilio.rest import Client

from oohy_product.custom_responses import StandardResponse, ErrorResponse
from .models import MobileUser
from .models import OTP


def generate_otp():
    import random
    return str(random.randint(100000, 999999))


def send_otp(phone_number, otp):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=f"Your OTP is {otp}",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return True
    except Exception as e:
        print(f"Error sending OTP: {e}")
        return False


def verify_otp(user, otp):
    return user.otp == otp


# @api_view(['POST'])
# @permission_classes([AllowAny])


def request_phone_otp(number):
    """
    View to handle OTP request via POST.
    Args:
        number (str): The phone number for which to send the OTP.
    Returns:
        JsonResponse: Response indicating success or failure of OTP request.
    """

    phone_number = number

    if not phone_number:
        return ErrorResponse(errors={"phone_number": "This field is required."}, status_code=400)

    try:
        # Fetch or create a user with the provided phone number
        user, created = MobileUser.objects.get_or_create(phone_number=phone_number)

        # Generate a new unique OTP
        otp_value = str(random.randint(100000, 999999))  # Create a random 6-digit OTP

        # Set the expiration time for the OTP
        expires_at = timezone.now() + timezone.timedelta(minutes=5)

        # Create a new OTP record for each request
        OTP.objects.create(phone_number=phone_number, otp=otp_value, expires_at=expires_at)

        # Send the OTP
        otp_sent = send_otp(phone_number, otp_value)

        if otp_sent:
            return StandardResponse(message="OTP sent successfully", status_code=200)
        else:
            return ErrorResponse(errors={"error": "Failed to send OTP"}, status_code=500)

    except Exception as e:
        return ErrorResponse(errors={"error": str(e)}, status_code=500)

def is_valid_phone_number(phone_number):
    """Validate phone number format (basic check for digits and `+` prefix)"""
    return phone_number.isdigit() or (phone_number.startswith('+') and phone_number[1:].isdigit())

class GenerateEmailOTP(APIView):
    def post(mail):
        email = mail

        if not email:
            return ErrorResponse(errors={"email": "Email is required"}, status_code=400)

        otp_instance = OTP(email=email)

        # Generate the OTP
        otp_instance.generate_otp()  # Make sure this method sets self.otp

        # Set the expiration time
        otp_instance.expires_at = timezone.now() + timedelta(minutes=5)

        # Save the OTP instance to the database
        otp_instance.save()

        # Send OTP via email
        subject = 'Your OTP Code'
        message = f'Your OTP code is {otp_instance.otp}. It is valid for 5 minutes.'
        from_email = settings.EMAIL_HOST_USER  # Set this in your settings
        recipient_list = [email]

        try:
            sent_mail = send_mail(subject, message, from_email, recipient_list)

            if sent_mail:
                return StandardResponse(message="OTP sent successfully",
                                        status_code=200)  # Make sure to return a message
            else:
                return ErrorResponse(errors={"error": "Failed to send OTP"}, status_code=500)

        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=500)


def is_valid_email(email):
    """Check if the provided email is in a valid format."""
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None
