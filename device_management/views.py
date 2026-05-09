from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
import logging
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from pulse_payments.models import Wallet
from .models import RegisterSensor
from .serializers import RegisterDeviceSerializer

User = get_user_model()


class RegisterDeviceView(APIView):
    """
    API to register a device if it's in the FactorySensorList and not already registered.
    """

    permission_classes = [IsAuthenticated]

    def get_available_identifier(self, user):
        """
        Returns the first available identifier (username, email, or phone) from the user object.
        """
        if user.username:
            return user.username
        if user.email:
            return user.email
        if hasattr(user, 'phone') and user.phone:  # Check if the custom user model has a phone field
            return user.phone
        return "No identifier available"

    def post(self, request, *args, **kwargs):
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")

        try:
            # Extract device ID from the input string
            input_data = request.data.get('data', '')
            if not input_data:
                return ErrorResponse(errors={"error": "No data provided."}, status_code=status.HTTP_400_BAD_REQUEST)

            # Extract the device ID (first part of the input)
            device_id = input_data.split(' ', 1)[0]

            if not device_id.isdigit():
                return ErrorResponse(errors={"error": "Invalid device ID format."},
                                     status_code=status.HTTP_400_BAD_REQUEST)
                
            # Fetch email and phone number from the authenticated user.
            user_email = request.user.email
            user_phone = request.user.phone_number
            
            
            
            # Prepare the data for serialization
            request_data = {
                "user": request.user.id,
                "unique_id": device_id,
                "comments": "Automatically extracted from input data.",
                "email": user_email,
                "phone_number": user_phone,
            }
            serializer = RegisterDeviceSerializer(data=request_data)
            if serializer.is_valid():

                if serializer.invalid_device:
                    return ErrorResponse(
                        errors={"error": "Invalid device."},
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
                    
                     # Check if the device is already registered by any user.
                device_already_registered = RegisterSensor.objects.filter(unique_id__unique_id=device_id).exists()

                # Register the device if valid
                sensor = serializer.save()
                
                # If the device has not been registered before, credit the user's wallet with 100.
                if not device_already_registered:
                    wallet, created = Wallet.objects.get_or_create(
                        user=request.user,
                        defaults={'balance': Decimal('0.00')}
                    )
                    wallet.balance += Decimal('1000.00')
                    wallet.save()
                    
                return StandardResponse(
                    data={"message": "Device registered successfully."},
                    message="Device registration completed successfully.",
                    status_code=status.HTTP_201_CREATED
                )

            return ErrorResponse(errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, *args, **kwargs):
        """View all registered devices for the authenticated user."""
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")

        try:
            # Filter devices by the authenticated user
            registrations = RegisterSensor.objects.filter(user=request.user)
            serializer = RegisterDeviceSerializer(registrations, many=True)
            return StandardResponse(
                data=serializer.data,
                message="Fetched all registered devices for the user successfully.",
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, *args, **kwargs):
        """Delete a device registration."""
        try:
            input_data = request.data.get('data')
            if not input_data:
                return ErrorResponse(errors={"error": "Unique ID is required."},
                                     status_code=status.HTTP_400_BAD_REQUEST)

            device_id = input_data.split(' ', 1)[0]
            registration = RegisterSensor.objects.filter(unique_id=device_id).first()
            if not registration:
                return ErrorResponse(
                    errors={"error": "No registration found for the provided Unique ID."},
                    status_code=status.HTTP_404_NOT_FOUND
                )

            # Ensure only the owner or an admin can delete the registration
            if registration.user != request.user and not request.user.is_staff:
                return ErrorResponse(
                    errors={"error": "You are not authorized to delete this registration."},
                    status_code=status.HTTP_403_FORBIDDEN
                )

            registration.delete()
            return StandardResponse(
                data={"message": "Device registration deleted successfully."},
                message="Device registration deleted successfully.",
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckUserRegistrationView(APIView):
    """
    API to check whether the authenticated user is registered with a device or not.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")

        try:
            # Check if the user has any registered devices
            has_registered_device = RegisterSensor.objects.filter(user=request.user).exists()
            if has_registered_device:
                return StandardResponse(
                    data={"is_registered": True},
                    message="User is registered with a device.",
                    status_code=status.HTTP_200_OK
                )
            else:
                return StandardResponse(
                    data={"is_registered": False},
                    message="User is not registered with any device.",
                    status_code=status.HTTP_200_OK
                )
        except Exception as e:
            return ErrorResponse(errors={"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckUserDeviceView(APIView):
    """
    API to check with which device the authenticated user is registered.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            # Extract the device ID from the request body
            device_id = request.data.get('device_id')
            if not device_id:
                return ErrorResponse(
                    errors={"error": "Device ID is required."},
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Check if the user is registered with this device
            registration = RegisterSensor.objects.filter(user=request.user, unique_id__unique_id=device_id).first()

            if registration:
                # Determine the user identifier (email or phone number)
                user_identifier = request.user.email
                if hasattr(request.user, 'phone') and request.user.phone:  # Check for custom `phone` field
                    user_identifier = request.user.phone

                # Prepare the serialized data for response
                data = {
                    "device_id": registration.unique_id.unique_id,
                    "comments": registration.comments,
                    "user_id": request.user.id,
                    "user": user_identifier,
                }
                return StandardResponse(
                    data=data,
                    message="User is registered with the specified device.",
                    status_code=status.HTTP_200_OK
                )

            # If no registration found
            return ErrorResponse(
                errors={"error": "User is not registered with the specified device."},
                status_code=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return ErrorResponse(
                errors={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
