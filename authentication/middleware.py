from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.authentication import get_authorization_header

class AccessTokenBlacklistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check for Authorization header
        auth_header = get_authorization_header(request).decode('utf-8')
        if auth_header.startswith("Bearer "):
            access_token = auth_header.split("Bearer ")[1]
            # Check if the access token is blacklisted
            if cache.get(f"blacklist_{access_token}"):
                # Custom message returned
                return JsonResponse(
                    {"detail": "Your session has expired. Please login again."},
                    status=401
                )

        return self.get_response(request)
