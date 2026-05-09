"""
This module handles user authentication views.
"""

import logging
import re
from datetime import timedelta

from django.contrib.auth import logout as django_logout
import requests
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from social_core.exceptions import AuthTokenError, AuthForbidden
from social_django.utils import load_strategy, load_backend

from oohy_product import settings
# Import custom responses
from oohy_product.custom_responses import StandardResponse, ErrorResponse
from user_profile.models import UserProfile
from . import serializers
from .models import CustomUser, MobileUser, OTP
from .serializers import ChangePasswordSerializer, CustomTokenObtainPairSerializer, CustomUserSerializer
from .utils import send_otp, is_valid_email, generate_otp, is_valid_phone_number

logger = logging.getLogger(__name__)

# Google OAuth Callback View
CLIENT_ID = '562493710511-fp0ibcim43hl4kubjqmbetb64ilnjhb4.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'http://127.0.0.1:8000/accounts/google/login/callback/'


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view to obtain JWT tokens based on email or phone number.
    """
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        email_or_phone = request.data.get('email_or_phone', '').strip()
        password = request.data.get('password', '')

        # Validate input fields
        if not email_or_phone or not password:
            return ErrorResponse(
                errors={"detail": "Invalid email or phone number or password."},
                status_code=400
            )

        user = None

        # Attempt to fetch the user
        try:
            if '@' in email_or_phone:  # Email case
                user = CustomUser.objects.get(email=email_or_phone)
            elif email_or_phone.isdigit() or (email_or_phone.startswith('+') and email_or_phone[1:].isdigit()):  # Phone number case
                user = CustomUser.objects.get(phone_number=email_or_phone)
            else:
                return ErrorResponse(
                    errors={"detail": "Invalid email or phone number or password."},
                    status_code=400
                )
        except CustomUser.DoesNotExist:
            return ErrorResponse(
                errors={"detail": "Invalid email or phone number or password."},
                status_code=400
            )

        # Validate the password
        if not user.check_password(password):
            return ErrorResponse(
                errors={"detail": "Invalid email or phone number or password."},
                status_code=400
            )

        # Check if user is active
        if not user.is_active:
            return ErrorResponse(
                errors={"detail": "User account is inactive."},
                status_code=403
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        return StandardResponse(
            data={
                "refresh": str(refresh),
                "access": str(access),
            },
            message="Login successful.",
            status_code=200
        )

def callback(request):
    """Handle Google OAuth callback."""
    code = request.GET.get('code')
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = {
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    token_response = requests.post(token_url, data=token_data)
    token_json = token_response.json()
    access_token = token_json.get('access_token')
    request.session['access_token'] = access_token
    return redirect('profile')


def profile(request):
    """Fetch user profile information."""
    access_token = request.session.get('access_token')
    if not access_token:
        return redirect('login')

    user_info_url = 'https://www.googleapis.com/oauth2/v1/userinfo'
    headers = {'Authorization': f'Bearer {access_token}'}
    user_info_response = requests.get(user_info_url, headers=headers)
    user_info = user_info_response.json()
    return JsonResponse(user_info)


# Check Login Status View
class CheckLoginStatusView(APIView):
    """Handle GET request to check login status."""
    """View to check login status."""

    def get(self, request):
        return StandardResponse({"status": "You are logged in!"})

    def post(self, request):
        return StandardResponse({"status": "You are logged in!"})


# Google Login View
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def google_login(request):
    access_token = request.data.get('access_token')
    if not access_token:
        return ErrorResponse(errors={"access_token": "This field is required."},
                             status_code=status.HTTP_400_BAD_REQUEST)

    strategy = load_strategy(request)
    backend = load_backend(strategy, 'google-oauth2', redirect_uri=None)

    try:
        user = backend.do_auth(access_token)
        if user and user.is_active:
            login(request, user)
            refresh = RefreshToken.for_user(user)
            return StandardResponse(data={'id': user.id, 'access': str(refresh.access_token), 'refresh': str(refresh)},
                                    message="OTP verified and user logged in successfully",
                                    status_code=status.HTTP_200_OK)
        else:
            return ErrorResponse(errors={"error": "User is not active or not found"},
                                 status_code=status.HTTP_400_BAD_REQUEST)
    except AuthTokenError as e:
        logger.error(f'Auth token error: {str(e)}')
        return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_400_BAD_REQUEST)
    except AuthForbidden as e:
        logger.error(f'Auth forbidden: {str(e)}')
        return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_403_FORBIDDEN)
    except Exception as e:
        logger.error(f'Unexpected error: {str(e)}')
        return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def request_otp_for_phone(request):
    """
      View to handle OTP request via POST.
      Args:
          request (HttpRequest): The HTTP request object.
      Returns:
          JsonResponse: Response indicating success or failure of OTP request.
    """
    phone_number = request.data.get('phone_number')
    if not phone_number:
        return ErrorResponse(errors={"phone_number": "This field is required."},
                             status_code=status.HTTP_400_BAD_REQUEST)

    try:
        user, created = MobileUser.objects.get_or_create(phone_number=phone_number)
        otp = user.generate_otp()  # Generate and store OTP
        otp_sent = send_otp(phone_number, otp)

        if otp_sent:
            return StandardResponse(data=None, message="OTP sent successfully", status_code=status.HTTP_200_OK)
        else:
            return ErrorResponse(errors={'error': 'Failed to send OTP'},
                                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return ErrorResponse(errors={'error': str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def verify_otp_for_phone(request):
    """
      View to handle OTP verification via POST.
      Args:
          request (HttpRequest): The HTTP request object.
      Returns:
          JsonResponse: Response indicating success or failure of OTP verification.
    """
    phone_number = request.data.get('phone_number')
    otp = request.data.get('otp')

    if not phone_number or not otp:
        return ErrorResponse(
            errors={'phone_number': 'This field is required.', 'otp': 'This field is required.'},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if not phone_number.startswith('+'):
        phone_number = f'+{phone_number}'
    

    try:
        user = MobileUser.objects.get(phone_number=phone_number)
        if user.verify_otp(otp):
            # Use CustomUser instead of User
            phone_number = f"{phone_number}"
            auth_user = CustomUser.objects.filter(phone_number=phone_number).first()
            first_time_user = False
            if not auth_user:
                
                auth_user = CustomUser(username=phone_number, phone_number=phone_number)
                auth_user.set_unusable_password()
                auth_user.is_active = 1
                auth_user.save()
                first_time_user = True
                
            else:
                
                # Check if a user profile exists for the authenticated user.
                if UserProfile.objects.filter(user_id=auth_user).exists():
                    first_time_user = False
                else:
                    first_time_user = True
                    
                    
            # Check if the user is active. If not, return an error response.
            if auth_user.is_active != 1:
                return ErrorResponse(
                    errors={'inactive_user': 'User account is inactive.'},
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            login(request, auth_user, backend='django.contrib.auth.backends.ModelBackend')

            refresh = RefreshToken.for_user(auth_user)
            return StandardResponse(
                data={
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'first_time_user': first_time_user,
                    'phone_number': phone_number
                },
                message='OTP verified and user logged in successfully',
                status_code=status.HTTP_200_OK
            )
        else:
            return ErrorResponse(errors={'invalid_otp': 'Invalid OTP'}, status_code=status.HTTP_400_BAD_REQUEST)
    except MobileUser.DoesNotExist:
        return ErrorResponse(errors={'user_does_not_exist': 'User does not exist'},
                             status_code=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return ErrorResponse(errors={'error': str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


        
# Google Login View
@api_view(['POST'])
@permission_classes([AllowAny])  # Exempt this view from authentication
def google_login(request):
    # Access token from the frontend
    token = request.data.get('access_token')

    # Step 1: Validate the token and get user info from Google
    response = requests.get(
        'https://www.googleapis.com/oauth2/v3/userinfo',
        headers={'Authorization': f'Bearer {token}'}
    )

    if response.status_code != 200:
        return Response({'error': 'Invalid token'}, status=400)

    user_info = response.json()
    email = user_info.get('email')

    # Step 2: Create or retrieve the user
    try:
        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email.split('@')[0],
                'first_name': user_info.get('given_name'),
                'last_name': user_info.get('family_name'),
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=400)

    # Step 3: Generate JWT tokens
    refresh = RefreshToken.for_user(user)

    # Step 4: Return the tokens and user info
    return Response({
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'user': {
            'email': user.email,
            'name': user_info.get('name'),
            'picture': user_info.get('picture'),
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout the user by blacklisting access and refresh tokens via GET request.
    """
    try:
        # Retrieve the refresh token from query parameters
        refresh_token = request.query_params.get("refresh")
        if not refresh_token:
            return ErrorResponse(
                errors={"error": "Refresh token is required as a query parameter."},
                status_code=400
            )

        # Blacklist the refresh token
        token = RefreshToken(refresh_token)
        token.blacklist()

        # Blacklist the access token (using cache for simplicity)
        access_token = request.auth
        if access_token:
            cache.set(f"blacklist_{access_token}", True, timeout=3600)  # Blacklist for 1 hour

        # Log the user out (session-based auth)
        django_logout(request)

        return StandardResponse(
            data=None,
            message="Logout successful.",
            status_code=200
        )
    except Exception as e:
        return ErrorResponse(
            errors={"error": str(e)},
            status_code=500
        )


User = get_user_model()

class MakeSuperUserAPIView(APIView):
    """
    API to grant or revoke superuser status for a user.
    Any authenticated user can perform this action.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            # Get user identifier (ID, email, or phone_number) and action from the request data
            user_identifier = request.data.get("user_identifier")
            action = request.data.get("action")  # 'grant' or 'revoke'

            if not user_identifier or not action:
                return Response(
                    {"error": "Both 'user_identifier' and 'action' ('grant' or 'revoke') are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Find the user by ID, email, or phone_number
            user = (
                User.objects.filter(id=user_identifier).first() or
                User.objects.filter(email=user_identifier).first() or
                User.objects.filter(phone_number=user_identifier).first()
            )
            if not user:
                return Response(
                    {"error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Grant or revoke superuser status
            if action == 'grant':
                user.is_superuser = True
                user.is_staff = True
                user.save()
                return Response(
                    {"message": f"User '{user.email or user.phone_number}' has been promoted to superuser."},
                    status=status.HTTP_200_OK,
                )
            elif action == 'revoke':
                user.is_superuser = False
                user.is_staff = False  # Optional: Revoke staff privileges too
                user.save()
                return Response(
                    {"message": f"Superuser status for '{user.email or user.phone_number}' has been revoked."},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"error": "Invalid action. Use 'grant' or 'revoke'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetEmailAndPhone(APIView):
    """
    API View to get the authenticated user's email and phone number.
    """
    permission_classes = [IsAuthenticated]  # Ensure only authenticated users can access

    def get(self, request, *args, **kwargs):
        """
        Retrieve the authenticated user's details.
        """
        user = request.user  # Get the authenticated user

        if not user:
            return ErrorResponse(errors={"error": "User not found"}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = CustomUserSerializer(user)
        return StandardResponse(data=serializer.data, message="User retrieved successfully", status_code=status.HTTP_200_OK)


class AddEmail(APIView):
    """
    API to generate and send OTP for email verification.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.user.email  # Get the logged-in user's email

        if email:
            return ErrorResponse(errors={"email": "You already have an email"}, status_code=400)

        email = request.data.get('email')  # User provides email

        if not email:
            return ErrorResponse(errors={"email": "Email is required"}, status_code=400)

        if not is_valid_email(email):
            return ErrorResponse(errors={"email": "Invalid email format"}, status_code=400)

        # Check if email already exists in the database
        if CustomUser.objects.filter(email=email).exists():
            return ErrorResponse(errors={"email": "Email is already registered"}, status_code=400)

        # Generate OTP and save it
        otp_value = generate_otp()
        otp_instance, created = OTP.objects.update_or_create(
            email=email,
            defaults={
                'otp': otp_value,
                'expires_at': timezone.now() + timedelta(minutes=5)  # OTP expires in 5 mins
            }
        )

        # Store email in session
        request.session['pending_email'] = email

        # Send OTP via email
        subject = 'Your OTP Code'
        message = f'Your OTP code is {otp_value}. It is valid for 5 minutes.'
        from_email = settings.EMAIL_HOST_USER  # Set this in settings
        recipient_list = [email]

        try:
            sent_mail = send_mail(subject, message, from_email, recipient_list)

            if sent_mail:
                return StandardResponse(message="OTP sent successfully", status_code=200)
            else:
                return ErrorResponse(errors={"error": "Failed to send OTP"}, status_code=500)

        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=500)


class VerifyEmailOTP(APIView):
    """
    API to verify OTP and add email to user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp_input = request.data.get('otp')

        if not otp_input:
            return ErrorResponse(errors={"otp": "OTP is required"}, status_code=400)

        # Retrieve email from session
        email = request.session.get('pending_email')

        if not email:
            return ErrorResponse(errors={"error": "No pending email verification found"}, status_code=400)

        try:
            otp_record = OTP.objects.filter(email=email).order_by('-created_at').first()

            if not otp_record:
                return ErrorResponse(errors={"error": "OTP not found for this email"}, status_code=400)

            # Check if OTP has expired
            if otp_record.expires_at < timezone.now():
                return ErrorResponse(errors={"error": "OTP has expired"}, status_code=400)

            # Validate OTP
            if otp_record.otp == otp_input:
                # OTP is valid, update the user's email
                user = request.user
                user.email = email
                user.save()

                # Remove email from session
                del request.session['pending_email']

                return StandardResponse(data={"email": user.email}, message="Email added successfully", status_code=200)
            else:
                return ErrorResponse(errors={"otp": "Invalid OTP"}, status_code=400)

        except OTP.DoesNotExist:
            return ErrorResponse(errors={"error": "OTP not found for this email"}, status_code=400)


class AddPhone(APIView):
    """
    API to generate and send OTP for phone number verification.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        phone_number = request.user.phone_number  # Get the logged-in user's phone number

        if phone_number:
            return ErrorResponse(errors={"phone_number": "You already have a phone number"}, status_code=400)

        phone_number = request.data.get('phone_number')  # User provides phone number

        if not phone_number:
            return ErrorResponse(errors={"phone_number": "Phone number is required"}, status_code=400)

        if not is_valid_phone_number(phone_number):
            return ErrorResponse(errors={"phone_number": "Invalid phone number format"}, status_code=400)

        # Check if phone number already exists in the database
        if CustomUser.objects.filter(phone_number=phone_number).exists():
            return ErrorResponse(errors={"phone_number": "Phone number is already registered"}, status_code=400)

        # Generate OTP and save it
        otp_value = generate_otp()
        otp_instance, created = OTP.objects.update_or_create(
            phone_number=phone_number,
            defaults={
                'otp': otp_value,
                'expires_at': timezone.now() + timedelta(minutes=5)  # OTP expires in 5 mins
            }
        )

        # Store phone number in session
        request.session['pending_phone_number'] = phone_number

        # Send OTP via SMS
        otp_sent = send_otp(phone_number, otp_value)

        if otp_sent:
            return StandardResponse(message="OTP sent successfully", status_code=200)
        else:
            return ErrorResponse(errors={"error": "Failed to send OTP"}, status_code=500)


class VerifyPhoneOTP(APIView):
    """
    API to verify OTP and add phone number to user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp_input = request.data.get('otp')

        if not otp_input:
            return ErrorResponse(errors={"otp": "OTP is required"}, status_code=400)

        # Retrieve phone number from session
        phone_number = request.session.get('pending_phone_number')

        if not phone_number:
            return ErrorResponse(errors={"error": "No pending phone number verification found"}, status_code=400)

        try:
            otp_record = OTP.objects.filter(phone_number=phone_number).order_by('-created_at').first()

            if not otp_record:
                return ErrorResponse(errors={"error": "OTP not found for this phone number"}, status_code=400)

            # Check if OTP has expired
            if otp_record.expires_at < timezone.now():
                return ErrorResponse(errors={"error": "OTP has expired"}, status_code=400)

            # Validate OTP
            if otp_record.otp == otp_input:
                # OTP is valid, update the user's phone number
                user = request.user
                user.phone_number = phone_number
                user.save()

                # Remove phone number from session
                del request.session['pending_phone_number']

                return StandardResponse(data={"phone_number": user.phone_number}, message="Phone number added successfully", status_code=200)
            else:
                return ErrorResponse(errors={"otp": "Invalid OTP"}, status_code=400)

        except OTP.DoesNotExist:
            return ErrorResponse(errors={"error": "OTP not found for this phone number"}, status_code=400)
        
        
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        # Get the new password from validated data
        new_password = serializer.validated_data['new_password1']
        user = request.user

        # Set the new password
        user.set_password(new_password)
        user.save()

        return StandardResponse(message="Password changed successfully.", status_code=200)
    
    
    
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.contrib.auth import logout

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unregister_user(request):
    """
    API view to unregister (delete) the authenticated user account.
    This view deletes the user's account along with any associated MobileUser record.
    It requires the user to be authenticated.
    """
    try:
        # Get the authenticated user
        auth_user = request.user
        phone_number = auth_user.phone_number
        
        # Log the user out using the underlying Django HttpRequest
        logout(request._request)
        
        # Delete any associated MobileUser record if it exists
        MobileUser.objects.filter(phone_number=phone_number).delete()
        
        # Delete the authenticated user account
        auth_user.delete()
        
        return StandardResponse(
            data=None,
            message="User unregistered successfully",
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        return ErrorResponse(
            errors={'error': str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
