import os
import datetime
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
import logging
# from .utils import upload_to_backblaze, delete_from_backblaze
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from bucket_extentions.delete import delete_from_backblaze
from bucket_extentions.upload import upload_to_backblaze
from oohy_product.custom_responses import StandardResponse, ErrorResponse
from .models import PatientsModel


@csrf_exempt
@api_view(["POST", "PUT", "DELETE", "GET"])
@permission_classes([IsAuthenticated])
def handle_profile(request, pk=None):
    if request.method == "POST":
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")

        # Extract required fields
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        gender = request.POST.get("gender")
        dob_str = request.POST.get("dob")
        phone_number = request.POST.get("phone_number")
        email = request.POST.get("email")
        country = request.POST.get("country")
        state = request.POST.get("state")
        city = request.POST.get("city")
        photo = request.FILES.get("photo_uri")

        try:
            dob = datetime.datetime.strptime(
                dob_str, "%d-%m-%Y"
            ).date()  # Convert input to DateField format
        except ValueError:
            return ErrorResponse(
                errors={"detail": "Invalid date format. Use DD-MM-YYYY."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate required fields
        if not all(
            [first_name, last_name, gender, dob, phone_number, country, state, city]
        ):
            return ErrorResponse(
                errors={"detail": "All required fields must be provided."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Check for duplicate patients before creating
        existing_patient = PatientsModel.objects.filter(
            user_profile=request.user, first_name=first_name, phone_number=phone_number
        ).exists()

        if existing_patient:
            return ErrorResponse(
                errors={
                    "detail": "A patient with this name and phone number already exists."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate email uniqueness if provided
        if email:
            email_in_use = PatientsModel.objects.filter(email=email).exists()
            if email_in_use:
                return ErrorResponse(
                    errors={
                        "detail": "The email address is already associated with another patient."
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            email = None  # Ensure blank emails are stored as NULL

        try:
            # Create the PatientsModel instance
            patient = PatientsModel.objects.create(
                user_profile=request.user,
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                dob=dob,
                phone_number=phone_number,
                email=email,
                country=country,
                state=state,
                city=city,
            )

            # Upload the photo with the patient's ID as part of the filename
            if photo:
                extension = os.path.splitext(photo.name)[1]
                unique_file_name = f"patient_profile_{patient.id}{extension}"
                photo_uri = upload_to_backblaze(photo, unique_file_name)
                patient.photo_uri = photo_uri
                patient.save()

            return StandardResponse(
                data={
                    "id": patient.id,
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "gender": patient.gender,
                    "dob": (
                        patient.dob.strftime("%d-%m-%Y") if patient.dob else None
                    ),  # Format dob
                    "phone_number": patient.phone_number,
                    "email": patient.email,
                    "country": patient.country,
                    "state": patient.state,
                    "city": patient.city,
                    "photo_uri": patient.photo_uri,
                    "created_at": patient.created_at.isoformat(),
                    "updated_at": patient.updated_at.isoformat(),
                },
                message="Patient created successfully!",
                status_code=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return ErrorResponse(
                errors={"detail": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    elif request.method == "PUT":
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")

        if pk is None:
            return ErrorResponse(
                errors={"detail": "Patient ID is required for updating."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            patient = PatientsModel.objects.get(id=pk, user_profile=request.user)
        except PatientsModel.DoesNotExist:
            return ErrorResponse(
                errors={"detail": "Patient not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        first_name = request.data.get("first_name", patient.first_name)
        last_name = request.data.get("last_name", patient.last_name)
        gender = request.data.get("gender", patient.gender)
        dob_str = request.data.get("dob")
        phone_number = request.data.get("phone_number", patient.phone_number)
        email = request.data.get("email", patient.email)
        country = request.data.get("country", patient.country)
        state = request.data.get("state", patient.state)
        city = request.data.get("city", patient.city)
        photo = request.FILES.get("photo_uri")

        if dob_str:
            try:
                dob = datetime.datetime.strptime(dob_str, "%d-%m-%Y").date()  # Convert to DateField format
            except ValueError:
                return ErrorResponse(
                    errors={"detail": "Invalid date format. Use DD-MM-YYYY."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            dob = patient.dob  # Keep existing dob if not provided

        if not all([first_name, last_name, gender, dob, phone_number, country, state, city]):
            return ErrorResponse(
                errors={"detail": "All required fields must be provided."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if photo:
            unique_file_name = f"patient_profile_{patient.id}_{photo.name}"
            photo_uri = upload_to_backblaze(photo, unique_file_name)
        else:
            photo_uri = patient.photo_uri

        if email:
            email_in_use = (
                PatientsModel.objects.filter(email=email)
                .exclude(id=patient.id)
                .exists()
            )
            if email_in_use:
                return ErrorResponse(
                    errors={"message": "The email address is already associated with another patient."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            email = None  # Ensure blank emails are stored as NULL

        # Duplicate check for first name and phone number, similar to POST
        duplicate_patient = PatientsModel.objects.filter(
            user_profile=request.user,
            first_name=first_name,
            phone_number=phone_number
        ).exclude(id=patient.id).exists()

        if duplicate_patient:
            return ErrorResponse(
                errors={"detail": "A patient with this name and phone number already exists."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            patient.first_name = first_name
            patient.last_name = last_name
            patient.gender = gender
            patient.dob = dob
            patient.phone_number = phone_number
            patient.email = email
            patient.country = country
            patient.state = state
            patient.city = city
            patient.photo_uri = photo_uri
            patient.save()

            return StandardResponse(
                data={
                    "id": patient.id,
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "gender": patient.gender,
                    "dob": (patient.dob.strftime("%d-%m-%Y") if patient.dob else None),
                    "phone_number": patient.phone_number,
                    "email": patient.email,
                    "country": patient.country,
                    "state": patient.state,
                    "city": patient.city,
                    "photo_uri": patient.photo_uri,
                    "created_at": patient.created_at.isoformat(),
                    "updated_at": patient.updated_at.isoformat(),
                },
                message="Patient updated successfully!",
                status_code=status.HTTP_200_OK,
            )

        except Exception as e:
            return ErrorResponse(
                errors={"detail": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    elif request.method == "DELETE":
        if pk is None:
            return ErrorResponse(
                errors={"detail": "Patient ID is required for deletion."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            patient = PatientsModel.objects.get(id=pk, user_profile=request.user)
            if patient.photo_uri:
                file_name = patient.photo_uri.split("/")[-1]
                delete_from_backblaze(file_name)
            patient.delete()

            return StandardResponse(
                message="Patient deleted successfully!", status_code=status.HTTP_200_OK
            )

        except PatientsModel.DoesNotExist:
            return ErrorResponse(
                errors={"detail": "Patient not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            return ErrorResponse(
                errors={"detail": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


    elif request.method == "GET":
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")

        if pk is not None:
            try:
                patient = PatientsModel.objects.get(id=pk, user_profile=request.user)
                return StandardResponse(
                    data={
                        "id": patient.id,
                        "first_name": patient.first_name,
                        "last_name": patient.last_name,
                        "gender": patient.gender,
                        "dob": (
                            patient.dob.strftime("%d-%m-%Y") if patient.dob else None
                        ),  # Format dob
                        "phone_number": patient.phone_number,
                        "email": patient.email,
                        "photo_uri": patient.photo_uri,
                        "country": patient.country,
                        "state": patient.state,
                        "city": patient.city,
                        "created_at": patient.created_at.isoformat(),
                        "updated_at": patient.updated_at.isoformat(),
                    },
                    message="Patient profile retrieved successfully!",
                    status_code=status.HTTP_200_OK,
                )
            except PatientsModel.DoesNotExist:
                return ErrorResponse(
                    errors={"detail": "Patient profile not found."},
                    status_code=status.HTTP_404_NOT_FOUND,
                )

        else:
            patients = PatientsModel.objects.filter(user_profile=request.user)
            patients_data = [
                {
                    "id": patient.id,
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "gender": patient.gender,
                    "dob": (
                        patient.dob.strftime("%d-%m-%Y") if patient.dob else None
                    ),  # Format dob
                    "phone_number": patient.phone_number,
                    "email": patient.email,
                    "photo_uri": patient.photo_uri,
                    "country": patient.country,
                    "state": patient.state,
                    "city": patient.city,
                    "created_at": patient.created_at.isoformat(),
                    "updated_at": patient.updated_at.isoformat(),
                }
                for patient in patients
            ]
            return StandardResponse(
                data=patients_data,
                message="All patient profiles retrieved successfully!",
                status_code=status.HTTP_200_OK,
            )

    return ErrorResponse(
        errors={"detail": "Invalid request method."},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


class SearchPatientView(APIView):
    """
    Search for patients by name or phone number (starts with).
    If no query is provided, return all patients.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Get the search query from the request body
        search_query = request.data.get("query", "").strip()

        # If no query is provided, return all patients for the authenticated user
        if not search_query:
            patients = PatientsModel.objects.filter(user_profile=request.user)
        else:
            # Filter patients based on name or phone number starting with the query
            patients = PatientsModel.objects.filter(
                Q(first_name__istartswith=search_query)
                | Q(last_name__istartswith=search_query)
                | Q(phone_number__startswith=search_query),
                user_profile=request.user,
            )

        # If no patients are found, return an error response
        if not patients.exists():
            return ErrorResponse(
                errors={"message": "No patients found matching the query."},
                status_code=404,
            )

        # Serialize the results
        patients_data = [
            {
                "id": patient.id,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "gender": patient.gender,
                "dob": patient.dob,
                "phone_number": patient.phone_number,
                "photo_uri": patient.photo_uri,
                "created_at": patient.created_at.isoformat(),
                "updated_at": patient.updated_at.isoformat(),
            }
            for patient in patients
        ]

        # Return success response with matching patients
        return StandardResponse(
            data=patients_data,
            message="Patients retrieved successfully.",
            status_code=200,
        )
