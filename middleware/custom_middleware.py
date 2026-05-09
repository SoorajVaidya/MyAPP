from django.contrib.auth.middleware import get_user
from rest_framework.authentication import TokenAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.db.models import Q
from django.utils.deprecation import MiddlewareMixin
from device_management.models import RegisterSensor


class GetSuperUserStatusMiddleware(MiddlewareMixin):
    """
    Middleware to check if the authenticated user is a superuser
    and attach additional status flags to the request object.
    """

    def __call__(self, request):
        # Ensure request.user is evaluated and not anonymous
        if request.user.is_anonymous:
            token_key = request.META.get('HTTP_AUTHORIZATION', '').split(' ')[-1]
            if token_key:
                # Attempt TokenAuthentication first
                try:
                    user_auth_tuple = TokenAuthentication().authenticate(request)
                    if user_auth_tuple:
                        request.user = user_auth_tuple[0]
                except AuthenticationFailed:
                    pass  # Invalid token, proceed to JWTAuthentication

                # Attempt JWTAuthentication if TokenAuthentication fails
                try:
                    user_auth_tuple = JWTAuthentication().authenticate(request)
                    if user_auth_tuple:
                        request.user = user_auth_tuple[0]
                except AuthenticationFailed:
                    pass  # Invalid token, user remains anonymous

        # Add additional attributes to the request
        if not request.user.is_anonymous:
            # Check if the user is a superuser
            request.is_superuser = request.user.is_superuser
            # Check if the user is a prime member
            is_prime = RegisterSensor.objects.filter(
                Q(user=request.user) & Q(is_prime_member=True)
            ).exists()
            request.is_prime_member = is_prime

            # Check if the user is registered with a sensor
            is_registered = RegisterSensor.objects.filter(
                Q(user=request.user)
            ).exists()
            request.is_registered_with_sensor = is_registered

            # Retrieve the unique ID associated with the user
            unique_id_obj = RegisterSensor.objects.filter(
                Q(user=request.user)
            ).values_list('unique_id', flat=True).first()
            request.unique_id = unique_id_obj

        # Proceed to the view
        response = self.get_response(request)
        return response
