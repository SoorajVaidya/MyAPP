import os
from datetime import datetime

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from bucket_extentions.delete import delete_from_backblaze
from bucket_extentions.upload import upload_to_backblaze
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from patients.utils import delete_from_backblaze
from .models import UserProfile


@api_view(["POST", "PUT", "DELETE", "GET"])
@permission_classes([IsAuthenticated])
def handle_profile(request):
    if request.method == "POST":
        user_name = request.POST.get("user_name")
        gender = request.POST.get("gender")
        dob_str = request.POST.get("dob")
        phone_number = request.POST.get("phone_number")
        photo = request.FILES.get("photo_uri")

        if not user_name or not gender or not dob_str or not phone_number:
            return ErrorResponse(
                errors={"message": "All fields are required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            dob = datetime.strptime(dob_str, "%d-%m-%Y").date()
        except ValueError:
            return ErrorResponse(
                errors={"message": "Invalid date format. Use DD-MM-YYYY."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_profile, created = UserProfile.objects.get_or_create(
                user_id=request.user,
                defaults={
                    "user_name": user_name,
                    "gender": gender,
                    "dob": dob,
                    "phone_number": phone_number,
                },
            )

            if not created:
                user_profile.user_name = user_name
                user_profile.gender = gender
                user_profile.dob = dob
                user_profile.phone_number = phone_number

            if photo:
                if user_profile.photo_uri:
                    existing_file_name = user_profile.photo_uri.split("/")[-1]
                    delete_from_backblaze(existing_file_name)

                extension = os.path.splitext(photo.name)[1]
                unique_file_name = f"user_profile_{request.user.id}{extension}"

                photo_uri = upload_to_backblaze(photo, unique_file_name)
                user_profile.photo_uri = photo_uri

            user_profile.save()

            return StandardResponse(
                data={
                    "user_id": request.user.id,
                    "user_name": user_profile.user_name,
                    "gender": user_profile.gender,
                    "dob": user_profile.formatted_dob(),
                    "email": user_profile.email,
                    "phone_number": user_profile.phone_number,
                    "photo_uri": user_profile.photo_uri,
                    "created_at": user_profile.created_at.isoformat(),
                    "updated_at": user_profile.updated_at.isoformat(),
                },
                message="Profile created or updated successfully!",
                status_code=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return ErrorResponse(
                errors={"message": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    elif request.method == "GET":
        user_profile = get_object_or_404(UserProfile, user_id=request.user)
        return StandardResponse(
            data={
                "user_id": request.user.id,
                "user_name": user_profile.user_name,
                "gender": user_profile.gender,
                "dob": user_profile.formatted_dob(),
                "email": user_profile.email,
                "phone_number": user_profile.phone_number,
                "photo_uri": user_profile.photo_uri,
                "created_at": user_profile.created_at.isoformat(),
                "updated_at": user_profile.updated_at.isoformat(),
            },
            message="Profile retrieved successfully!",
            status_code=status.HTTP_200_OK,
        )

    elif request.method == "PUT":
        user_profile = get_object_or_404(UserProfile, user_id=request.user)

        user_name = request.data.get("user_name", user_profile.user_name)
        gender = request.data.get("gender", user_profile.gender)
        dob_str = request.data.get("dob")
        phone_number = request.data.get("phone_number", user_profile.phone_number)
        photo = request.FILES.get("photo_uri")

        if dob_str:
            try:
                dob = datetime.strptime(dob_str, "%d-%m-%Y").date()
            except ValueError:
                return ErrorResponse(
                    errors={"message": "Invalid date format. Use DD-MM-YYYY."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            dob = user_profile.dob

        if photo:
            if user_profile.photo_uri:
                existing_file_name = user_profile.photo_uri.split("/")[-1]
                delete_from_backblaze(existing_file_name)
            unique_file_name = f"user_profile_{request.user.id}_{photo.name}"
            photo_uri = upload_to_backblaze(photo, unique_file_name)
        else:
            photo_uri = user_profile.photo_uri

        try:
            user_profile.user_name = user_name
            user_profile.gender = gender
            user_profile.dob = dob
            user_profile.phone_number = phone_number
            user_profile.photo_uri = photo_uri
            user_profile.save()

            return StandardResponse(
                data={
                    "user_id": request.user.id,
                    "user_name": user_profile.user_name,
                    "gender": user_profile.gender,
                    "dob": user_profile.formatted_dob(),
                    "email": user_profile.email,
                    "phone_number": user_profile.phone_number,
                    "photo_uri": user_profile.photo_uri,
                    "created_at": user_profile.created_at.isoformat(),
                    "updated_at": user_profile.updated_at.isoformat(),
                },
                message="Profile updated successfully!",
                status_code=status.HTTP_200_OK,
            )
        except Exception as e:
            return ErrorResponse(
                errors={"message": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    elif request.method == "DELETE":
        try:
            user_profile = UserProfile.objects.get(user_id=request.user)
            try:
                from pulse_service.models import PulseData

                PulseData.objects.filter(user=user_profile).update(user=None)
            except Exception as related_error:
                print(
                    f"Error disassociating related PulseData records: {related_error}"
                )

            if user_profile.photo_uri:
                try:
                    file_name = user_profile.photo_uri.split("/")[-1]
                    delete_from_backblaze(file_name)
                except Exception as photo_error:
                    print(f"Error deleting photo from Backblaze: {photo_error}")

            user_profile.delete()
            return StandardResponse(
                message="User Profile deleted successfully, and related data was preserved!",
                status_code=status.HTTP_200_OK,
            )
        except UserProfile.DoesNotExist:
            return ErrorResponse(
                errors={"message": "User Profile not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return ErrorResponse(
                errors={"message": f"An error occurred during deletion: {str(e)}"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
