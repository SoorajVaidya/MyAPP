from datetime import timedelta, date
from venv import logger
from django.db import connection  # ✅ Ensure this is imported
from rest_framework.test import APIRequestFactory, force_authenticate
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.cache import cache
import logging

# from dynamic_report_service.views import ReportPDFView
from global_utils.service_treatments_map import SERVICE_TREATMENT_MAP
from oohy_product.custom_responses import ErrorResponse, StandardResponse
from patients.models import PatientsModel
from pulse_payments.models import Service
from report_service.service_utils import get_services_for_history
from user_profile.models import UserProfile
from .models import (
    DiagnosisReportHistory,
    DiagnosticResource,
    Patterns,
    TreatmentReportHistory,
    QuestionBank,
)
from .report_service_handler import generate_treatment_report
from .serliaizers import (
    DiagnosisReportHistorySerializer,
    TreatmentReportHistorySerializer,
    ReportPageMetdataSerializer,
)

import random
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import SymptomsQuestions


class GenerateDiagnosisReport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Handle GET request and return the generated treatment report for a single pattern.
        """
        # print("Received Input in DiagnosisReportView:", request.data)

        regenerate = request.query_params.get("regenerate", False)
        language = request.query_params.get("language", "eng")

        if isinstance(regenerate, str):
            regenerate = regenerate.lower() == "true"

        if regenerate:
            # Handle regenerate logic
            report_history_id = request.query_params.get("report_history_id")

            if not report_history_id:
                return Response(
                    data={"message": "report_history_id is required for regeneration."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                report_history = DiagnosisReportHistory.objects.get(
                    report_history_id=report_history_id
                )

            except DiagnosisReportHistory.DoesNotExist:
                return Response(
                    data={"message": "Report history not found for the provided ID."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Fetch user details
            user_profile = UserProfile.objects.filter(
                user_id=report_history.user_id
            ).first()

            user_name = user_profile.user_name if user_profile else "Unknown User"
            user_number = (
                user_profile.phone_number if user_profile else "Unknown Number"
            )

            patient = report_history.patient_id

            patient_first_name = patient.first_name if patient else "Unknown Patient"
            patient_last_name = patient.last_name if patient else "Unknown Patient"

            patient_name = f"{patient_first_name} {patient_last_name}"

            patient_number = patient.phone_number if patient else "Unknown Number"

            if patient and patient.dob:
                dob = patient.dob
                today = date.today()
                patient_age = (
                    today.year
                    - dob.year
                    - ((today.month, today.day) < (dob.month, dob.day))
                )
            else:
                patient_age = "Unknown"

            parameters = {
                "primary": report_history.primary,
                "secondary": report_history.secondary,
                "tertiary": report_history.tertiary,
                "quaternary": report_history.quaternary,
                "quinary": report_history.quinary,
            }

            # print("Extracted Parameters for Regeneration:", parameters)

            filtered_data = generate_treatment_report(
                parameters,
                user_name,
                patient_name,
                patient_age,
                patient_number,
                language,
                user_number,
            )

        else:
            # Handle standard logic
            primary = request.query_params.get("primary")
            secondary = request.query_params.get("secondary")
            tertiary = request.query_params.get("tertiary")
            quaternary = request.query_params.get("quaternary")
            quinary = request.query_params.get("quinary")

            parameters = {
                "primary": primary,
                "secondary": secondary,
                "tertiary": tertiary,
                "quaternary": quaternary,
                "quinary": quinary,
            }

            # print("Parsed Parameters in DiagnosisReportView:", parameters)

            # Generate the treatment report
            filtered_data = generate_treatment_report(parameters, language=language)

        response_data = filtered_data

        if filtered_data.get("status") == "success":

            return Response(data=response_data, status=status.HTTP_200_OK)
        else:
            return Response(
                data={
                    "message": filtered_data.get(
                        "message", "No matching pattern found."
                    ),
                    "data": response_data,
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class ReportHistory(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Retrieve a list of all report history records.

        This API fetches and returns all records from the DiagnosisReportHistory model.
        The response includes detailed information about each report, such as the
        associated user, patient, pulse, service name, diagnosis details (primary, secondary, tertiary, quaternary),
        comments, and timestamps.

        Response:
        - status: "success" or "failure"
        - message: Descriptive message
        - data: List of report history records with their details
        """
        reports = DiagnosisReportHistory.objects.all().order_by("-created_at")

        # Format each report entry into a response
        reports_data = [
            {
                "report_history_id": report.report_history_id,
                "user_id": report.user_id.id,
                "patient_id": report.patient_id.id if report.patient_id else None,
                "pulse_id": report.pulse_id.id if report.pulse_id else None,
                # "service_name": report.service_name.name,  # Ensure this gets the name of the service
                "primary": report.primary,
                "secondary": report.secondary,
                "tertiary": report.tertiary,
                "quaternary": report.quaternary,
                "quinary": report.quinary,
                "comments": report.comments,
                "created_at": report.created_at,
                "updated_at": report.updated_at,
            }
            for report in reports
        ]

        return StandardResponse(
            {
                "status": "success",
                "message": "Report history retrieved successfully.",
                "data": reports_data,
            },
            status=status.HTTP_200_OK,
        )


class CreateDiagnosisHistory(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    """
        API endpoint to create a new Diagnosis Report History.

        This API allows authenticated users to create a new Diagnosis Report History record.
        The API ensures the following:
        - No duplicate reports are created with the same `pulse_id`.
        - The `user_id` is automatically assigned to the authenticated user making the request.

        The API validates the incoming data, applies additional business logic, and returns a structured response.

        Response:
        - On success:
          - status: 201 Created
          - message: "Diagnosis report history created successfully."
          - data: Details of the created report history.
        - On validation failure:
          - status: 400 Bad Request
          - errors: Detailed error messages.
        - On any other exception:
          - status: 500 Internal Server Error
          - errors: Generic error message.
        """
    queryset = DiagnosisReportHistory.objects.all()
    serializer_class = DiagnosisReportHistorySerializer

    def perform_create(self, serializer):
        """
        Custom logic to perform before saving the new report.
        - Ensures that no duplicate report exists for the same `pulse_id`.
        - Assigns the authenticated user as the `user_id`.
        """
        # Check if a DiagnosisReportHistory with the same pulse_id already exists
        pulse_id = serializer.validated_data.get(
            "pulse_id"
        )  # assuming 'pulse_id' is in the serializer data

        if DiagnosisReportHistory.objects.filter(pulse_id=pulse_id).exists():
            raise ValidationError(
                {"pulse_id": ["A report with this pulse ID already exists."]}
            )

        # Automatically set the user_id to the authenticated user
        serializer.save(user_id=self.request.user)

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        try:

            serializer.is_valid(raise_exception=True)

            # Call perform_create for additional logic
            self.perform_create(serializer)

            # Return the custom response
            return StandardResponse(
                data=serializer.data,
                message="Diagnosis report history created successfully.",
                status_code=status.HTTP_201_CREATED,
            )

        except ValidationError as e:
            # Handle validation errors and return them as an ErrorResponse
            return ErrorResponse(
                errors=e.detail, status_code=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            # Handle any other exceptions
            return ErrorResponse(
                errors={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PatientHistorySingleReportView(APIView):
    """
    API endpoint to retrieve and generate a treatment report based on a specific Diagnosis Report History.

    This API allows authenticated users to fetch a Diagnosis Report History record by its `report_history_id`
    and generate a treatment report based on its details. The treatment report is generated using predefined
    logic that processes the diagnosis fields (primary, secondary, tertiary, quaternary).

    Response:
    - On success:
      - status: 200 OK
      - message: "Treatment report generated successfully."
      - data: The generated treatment report.
    - If no matching pattern is found:
      - status: 404 Not Found
      - errors: Message indicating no matching pattern.
    - On any other exception:
      - status: 500 Internal Server Error
      - errors: Generic error message.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, report_history_id):
        """
        Handle GET request and return the treatment report based on report_history_id.

        Workflow:
        1. Fetch the Diagnosis Report History record using the provided `report_history_id`.
        2. Extract the diagnosis fields (primary, secondary, tertiary, quaternary).
        3. Generate a treatment report using the extracted fields.
        4. Return the treatment report if successful, or an appropriate error message.
        """
        try:
            # Fetch the record from the DiagnosisReportHistory model
            diagnosis_report = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )

            # Extract fields from the fetched record
            parameters = {
                "primary": diagnosis_report.primary,
                "secondary": diagnosis_report.secondary,
                "tertiary": diagnosis_report.tertiary,
                "quaternary": diagnosis_report.quaternary,
                "quinary": diagnosis_report.quinary,
            }

            # Generate the treatment report
            filtered_data = generate_treatment_report(parameters)

            if filtered_data.get("status") == "success":
                return StandardResponse(
                    data={"report": filtered_data},
                    message="Treatment report generated successfully.",
                    status_code=status.HTTP_200_OK,
                )
            else:
                return ErrorResponse(
                    errors={
                        "message": filtered_data.get(
                            "message", "No matching pattern found."
                        )
                    },
                    status_code=status.HTTP_404_NOT_FOUND,
                )

        except Exception as e:
            return ErrorResponse(
                errors={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateTreatmentHistory(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    """
    API endpoint to create a new Treatment Report History.

    This API allows authenticated users to create a new Treatment Report History record.
    It ensures:
    - No duplicate records exist for the same `diagnosis_report_id` and `service_id`.
    - All data is validated through the serializer.

    Response:
    - On success:
      - status: 201 Created
      - message: "Treatment report history created successfully."
      - data: Details of the created Treatment Report History.
    - On validation failure:
      - status: 400 Bad Request
      - errors: Detailed validation error messages.
    - On any other exception:
      - status: 500 Internal Server Error
      - errors: Generic error message.
    """

    queryset = TreatmentReportHistory.objects.all()
    serializer_class = TreatmentReportHistorySerializer

    def create(self, request, *args, **kwargs):
        """
        Handle POST request to create a new Treatment Report History.

        Workflow:
        1. Extract `diagnosis_report_id` and `service_id` from the request data.
        2. Check for duplicates in the database.
        3. Validate the data using the serializer.
        4. Save the record if validation passes and return a success response.
        5. Handle validation or other exceptions and return appropriate error responses.
        """
        diagnosis_report_id = request.data.get("diagnosis_report")
        service_id = request.data.get("service_id")

        # Check for duplicate entries
        if TreatmentReportHistory.objects.filter(
            diagnosis_report_id=diagnosis_report_id, service_id=service_id
        ).exists():
            errors = {
                "diagnosis_report": [
                    "A treatment report for this diagnosis report with the given service already exists."
                ]
            }
            return ErrorResponse(errors=errors, status_code=400)

        # Use serializer for validation
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)

            # Success response
            headers = self.get_success_headers(serializer.data)
            return StandardResponse(
                data=serializer.data,
                success=True,
                message="Treatment report history created successfully",
                status_code=201,
                headers=headers,
            )
        except serializers.ValidationError as exc:
            # Custom handling of validation errors
            return ErrorResponse(errors=exc.detail, status_code=400)

    def handle_exception(self, exc):
        """
        Override to handle all exceptions and format errors with ErrorResponse.

        Workflow:
        1. Check if the exception is a validation error.
        2. Return a formatted error response with appropriate status codes.
        3. For other exceptions, return a generic error response.
        """
        response = super().handle_exception(exc)

        if isinstance(exc, serializers.ValidationError):
            return ErrorResponse(errors=exc.detail, status_code=response.status_code)

        return ErrorResponse(errors={"error": str(exc)}, status_code=500)


class PatientHistoryListView(APIView):
    """
    API endpoint to retrieve treatment and diagnosis history for a specific patient grouped by date and time.

    This API allows authenticated users to fetch a list of reports (diagnosis and treatment) for a given patient.
    Reports are grouped by their creation datetime (converted to IST), and details about diagnosis reports,
    treatment reports, and their comments or suggestions are included.

    Response:
    - On success:
      - status: "success"
      - message: "Reports fetched successfully."
      - data: List of grouped reports with details.
    - On failure:
      - status: "error"
      - message: Error message indicating the issue (e.g., missing patient ID, no access to patient, or no reports).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Handle GET request to fetch patient reports grouped by date and time.

        Workflow:
        1. Validate the presence of the `patient_id` in the body.
        2. Check if the authenticated user has access to the specified patient.
        3. Fetch all diagnosis reports for the given patient.
        4. Group the reports by their creation datetime (converted to IST).
        5. Include details about diagnosis and treatment reports in the grouped data.
        6. Return the final grouped report data or appropriate error messages.
        """
        
        logger = logging.getLogger(__name__)
        logger.info(f"🧑‍💻 User ID: {request.user.id}, 📞 Phone: {getattr(getattr(request.user, 'profile', None), 'phone_number', 'Unknown')}")
        
        # Try to read the request body for `patient_id`
        patient_id = request.query_params.get("patient_id")  # Read from body
        if not patient_id:
            return ErrorResponse(
                errors={"patient_id": ["Patient ID is required."]}, status_code=400
            )

        user = request.user

        try:
            patient = PatientsModel.objects.get(id=patient_id, user_profile=user)
        except PatientsModel.DoesNotExist:
            return ErrorResponse(
                errors={"patient_id": ["You do not have access to this patient."]},
                status_code=404,
            )

        diagnosis_reports = DiagnosisReportHistory.objects.filter(
            patient_id=patient_id
        ).prefetch_related("treatment_reports")
        if not diagnosis_reports.exists():
            return ErrorResponse(
                errors={"patient_id": ["No reports found for the given patient ID."]},
                status_code=404,
            )

        report_data = {}
        ist_offset = timedelta(hours=5, minutes=30)  # IST offset from UTC

        for report in diagnosis_reports:
            if report.processed == 0:
                continue
            # Convert created_at to IST
            report_datetime_utc = report.created_at
            report_datetime_ist = report_datetime_utc + ist_offset
            report_datetime_str = report_datetime_ist.strftime("%Y-%m-%d %H:%M:%S")

            if report_datetime_str not in report_data:
                report_data[report_datetime_str] = {
                    "diagnosis_reports": 0,
                    "diagnosis_report_id": None,
                    "treatment_reports": 0,
                    "treatment_report_ids": [],
                    "total_reports": 0,
                    "comments": "",
                    "suggestions": "",
                }

            # Only include data from diagnosis reports
            report_data[report_datetime_str]["diagnosis_reports"] += 1

            report_data[report_datetime_str][
                "diagnosis_report_id"
            ] = report.report_history_id  # Single variable here
            report_data[report_datetime_str][
                "comments"
            ] += f" | {report.comments or ''}"
            report_data[report_datetime_str][
                "suggestions"
            ] += f" | {report.suggestions or ''}"

            # Only count treatment reports but exclude their comments/suggestions
            for treatment_report in report.treatment_reports.all():
                report_data[report_datetime_str]["treatment_reports"] += 1
                report_data[report_datetime_str]["treatment_report_ids"].append(
                    treatment_report.id
                )

            report_data[report_datetime_str]["total_reports"] = (
                report_data[report_datetime_str]["diagnosis_reports"]
                + report_data[report_datetime_str]["treatment_reports"]
            )

        # Convert to list format for the response
        final_report_data = [
            {
                "counter": index + 1,
                "datetime": datetime_str,
                "diagnosis_report_id": data[
                    "diagnosis_report_id"
                ],  # Single variable here
                "treatment_reports": data["treatment_reports"],
                "treatment_report_ids": data["treatment_report_ids"],
                "total_reports": data["total_reports"],
                "comments": data["comments"].strip(" | "),
                "suggestions": data["suggestions"].strip(" | "),
            }
            for index, (datetime_str, data) in enumerate(report_data.items())
        ]

        return StandardResponse(
            data=final_report_data,
            message="Reports fetched successfully.",
            status_code=200,
        )


class AddCommentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        report_id = request.data.get("report_id")
        comment = request.data.get("comment")

        if not report_id or not comment:
            return ErrorResponse(
                errors={"message": "Report ID and comment are required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = DiagnosisReportHistory.objects.get(report_history_id=report_id)
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={"message": "Diagnosis report not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Add or update the comment
        report.comments = comment
        report.save()

        return StandardResponse(
            message="Comment added/updated successfully.",
            status_code=status.HTTP_200_OK,
        )

    def get(self, request):
        report_id = request.query_params.get("report_id")

        if not report_id:
            return ErrorResponse(
                errors={"message": "Report ID is required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = DiagnosisReportHistory.objects.get(report_history_id=report_id)
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={"message": "Diagnosis report not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse(
            data={"comment": report.comments or ""},
            message="Comment fetched successfully.",
            status_code=status.HTTP_200_OK,
        )


class AddSuggestionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        report_id = request.data.get("report_id")
        suggestion = request.data.get("suggestion")

        if not report_id or not suggestion:
            return ErrorResponse(
                errors={"message": "Report ID and suggestion are required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = DiagnosisReportHistory.objects.get(report_history_id=report_id)
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={"message": "Diagnosis report not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Add or update the suggestion
        report.suggestions = suggestion
        report.save()

        return StandardResponse(
            message="Suggestion added/updated successfully.",
            status_code=status.HTTP_200_OK,
        )

    def get(self, request):
        report_id = request.query_params.get("report_id")

        if not report_id:
            return ErrorResponse(
                errors={"message": "Report ID is required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = DiagnosisReportHistory.objects.get(report_history_id=report_id)
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={"message": "Diagnosis report not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse(
            data={"suggestion": report.suggestions or ""},
            message="Suggestion fetched successfully.",
            status_code=status.HTTP_200_OK,
        )


class ReportPageMetadata(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from django.shortcuts import get_object_or_404

            # Extract the report_history_id from the request query params
            report_history_id = request.query_params.get("report_history_id")

            diagnosis_report = get_object_or_404(
                DiagnosisReportHistory, report_history_id=report_history_id
            )

            services_with_purchased_status = get_services_for_history(report_history_id)
            # Constructing the response dictionary
            pdf_report_response = {
                "status": "success",
                "data": {
                    "pdf_url": diagnosis_report.pdf_url  # Assuming pdf_url is a field in your model
                },
                "message": "PDF generated successfully.",
            }

            if not report_history_id:
                return ErrorResponse(
                    errors={"report_history_id": "This field is required."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            return StandardResponse(
                data={
                    "services": services_with_purchased_status,
                    "pdf_report_response": pdf_report_response,
                },
                message="Report Metdata retrieved successfully.",
                status_code=status.HTTP_200_OK,
            )

        except Exception as e:

            return ErrorResponse(
                errors={"detail": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GetQuestionsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        question_numbers = request.query_params.get("question_numbers", None)

        if not question_numbers:
            return ErrorResponse(
                errors={"detail": "No question numbers provided."}, status_code=400
            )

        try:
            # Split the string into a list and convert to integers
            question_numbers = list(map(int, question_numbers.split(",")))
        except ValueError:
            return ErrorResponse(
                errors={
                    "detail": "Invalid question number format. Provide numbers as a comma-separated list."
                },
                status_code=400,
            )

        # Fetch questions with the given question numbers
        questions = QuestionBank.objects.filter(
            question_number__in=question_numbers
        ).values("question_number", "question")

        if not questions:
            return ErrorResponse(
                errors={"detail": "No questions found for the provided numbers."},
                status_code=404,
            )

        return StandardResponse(
            data=list(questions),
            message="Questions retrieved successfully.",
            status_code=200,
        )


class GetQuestionsByReportHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]
    """
    Expects a JSON payload:
    {
      "report_history_id": <id>
    }

    The view:
      1. Retrieves the DiagnosisReportHistory instance by its report_history_id.
      2. Uses its report_pattern_type (a Patterns instance) to build categories using the pattern’s
         primary, secondary, and tertiary fields.
      3. For each category (one of wind, heat, humid, dry, cold), the allowed organs are mapped as:
             Wind  -> Lv, GB
             Heat  -> Heart, SI
             Humid -> Sp, St
             Dry   -> Lun, LI
             Cold  -> Kidney, UB
         For each category and for each allowed organ, it fetches one random question.
         This gives 2 questions per category (i.e. 6 questions per cycle if there are three categories).
         Note that cycle_1 uses the pattern’s yin_yang value, while cycle_2 uses “yin” if the pattern is “yang”
         (or the same value if already yin).
      4. Returns a JSON response containing the report_history_id, pattern details, and the grouped questions.
         Each question object includes the question_id, question text, and options.
    """

    def post(self, request, *args, **kwargs):
        report_history_id = request.data.get("report_history_id")
        language = request.data.get("language", "eng").strip().lower() or "eng"
        if not report_history_id:
            return ErrorResponse(
                errors={"error": "report_history_id is required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            diagnosis_report = DiagnosisReportHistory.objects.get(
                report_history_id=report_history_id
            )
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={
                    "error": "Diagnosis report not found for the given report_history_id."
                },
                status_code=status.HTTP_404_NOT_FOUND,
            )

        pattern = diagnosis_report.report_pattern_type
        if not pattern:
            return ErrorResponse(
                errors={"error": "No pattern associated with this diagnosis report."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Build categories from the pattern's primary, secondary, and tertiary fields.
        categories = []
        if pattern.primary:
            categories.append(pattern.primary.lower())
        if pattern.secondary:
            categories.append(pattern.secondary.lower())
        if pattern.tertiary:
            categories.append(pattern.tertiary.lower())

        # Mapping from category to allowed organs.
        # Note: We removed "humidity" and use only "humid"
        organ_mapping = {
            "wind": ["Lv", "GB"],
            "heat": ["Heart", "SI"],
            "humid": ["Sp", "St"],
            "dry": ["Lun", "LI"],
            "cold": ["Kidney", "UB"],
        }

        cycles = {"cycle_1": [], "cycle_2": []}

        # Determine the yin_yang values for each cycle.
        cycle1_yin_yang = pattern.yin_yang.lower()
        if cycle1_yin_yang == "yang":
            cycle2_yin_yang = "yin"
        else:
            # When yin, both cycles use yin.
            cycle2_yin_yang = cycle1_yin_yang

        for cat in categories:
            organs = organ_mapping.get(cat)
            if not organs:
                # Skip categories not in our mapping.
                continue

            for organ in organs:
                # Fetch one random question for cycle 1 for the given category and organ.
                qs_cycle1 = list(
                    SymptomsQuestions.objects.filter(
                        name__iexact=cat,
                        yin_yang__iexact=cycle1_yin_yang,
                        organ__iexact=organ,
                    )
                )
                question_cycle1 = None
                if qs_cycle1:
                    random.shuffle(qs_cycle1)
                    question_cycle1 = qs_cycle1[0]
                    cycles["cycle_1"].append(
                        {
                            "question_id": question_cycle1.question_number,
                            "question": (
                                question_cycle1.question_kannada
                                if language == "kan"
                                else question_cycle1.question
                            ),
                            "options": question_cycle1.options,
                        }
                    )

                # Fetch one random question for cycle 2 for the given category and organ.
                qs_cycle2_queryset = SymptomsQuestions.objects.filter(
                    name__iexact=cat,
                    yin_yang__iexact=cycle2_yin_yang,
                    organ__iexact=organ,
                )
                if question_cycle1:
                    qs_cycle2_queryset = qs_cycle2_queryset.exclude(
                        question_number=question_cycle1.question_number
                    )
                qs_cycle2 = list(qs_cycle2_queryset)

                if qs_cycle2:
                    random.shuffle(qs_cycle2)
                    question_cycle2 = qs_cycle2[0]
                    cycles["cycle_2"].append(
                        {
                            "question_id": question_cycle2.question_number,
                            "question": (
                                question_cycle2.question_kannada
                                if language == "kan"
                                else question_cycle2.question
                            ),
                            "options": question_cycle2.options,
                        }
                    )

        response_data = {
            "report_history_id": report_history_id,
            "pattern": {
                "pattern_number": pattern.pattern_number,
                "pattern_name": pattern.pattern_name,
                "primary": pattern.primary,
                "secondary": pattern.secondary,
                "tertiary": pattern.tertiary,
                "yin_yang": pattern.yin_yang,
            },
            "questions": cycles,
        }
        return StandardResponse(
            data=response_data,
            message="Questions retrieved successfully.",
            status_code=status.HTTP_200_OK,
        )


class ScrollableDiagnosisReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        report_history_id = request.query_params.get("report_history_id")
        language = request.query_params.get("language", "").strip().lower() or "eng"  # <<-- corrected

        if not report_history_id:
            return ErrorResponse(
                errors={"report_history_id": "This parameter is required."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report_history = DiagnosisReportHistory.objects.get(
                report_history_id=report_history_id
            )
        except DiagnosisReportHistory.DoesNotExist:
            return ErrorResponse(
                errors={"report_history_id": "No report found with the provided ID."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Clean labels (e.g., Humid_56.73% → Humid)
        def clean(val):
            return (val or "").split("_")[0].strip().title()

        primary = clean(report_history.primary)
        secondary = clean(report_history.secondary)
        tertiary = clean(report_history.tertiary)
        cache_key = f"{primary}-{secondary}-{tertiary}-{language}"

        cached_data = cache.get(cache_key)
        if cached_data:
            print(f"✅ CACHE HIT: {cache_key}")
            return StandardResponse(
                data={"content": cached_data},
                status_code=status.HTTP_200_OK,
                message="Report loaded from cache.",
            )

        # User & patient info
        user_profile = UserProfile.objects.filter(
            user_id=report_history.user_id
        ).first()
        user_name = user_profile.user_name if user_profile else "Unknown User"
        user_number = user_profile.phone_number if user_profile else "Unknown Number"

        patient = report_history.patient_id
        patient_name = (
            f"{patient.first_name} {patient.last_name}"
            if patient
            else "Unknown Patient"
        )
        patient_number = patient.phone_number if patient else "Unknown Number"

        if patient and patient.dob:
            dob = patient.dob
            today = date.today()
            patient_age = (
                today.year
                - dob.year
                - ((today.month, today.day) < (dob.month, dob.day))
            )
        else:
            patient_age = "Unknown"

        parameters = {
            "primary": report_history.primary or "",
            "secondary": report_history.secondary or "",
            "tertiary": report_history.tertiary or "",
            "quaternary": report_history.quaternary or "",
            "quinary": report_history.quinary or "",
        }

        report = generate_treatment_report(
            parameters,
            user_name,
            patient_name,
            patient_age,
            patient_number,
            language,
            user_number,
        )

        if report.get("status") != "success":
            return ErrorResponse(
                errors={"detail": report.get("message", "No matching pattern found.")},
                status_code=status.HTTP_404_NOT_FOUND,
            )

        content = report["data"][0]["content"] if report["data"] else []

        # Add extra fields as individual "text" items
        additional_fields = [
            "carbohydrate",
            "protein",
            "fat",
            "wind_yin",
            "wind_yang",
            "heat_yin",
            "heat_yang",
            "humid_yin",
            "humid_yang",
            "dry_yin",
            "dry_yang",
            "cold_yin",
            "cold_yang",
            "vata",
            "pitta",
            "kapha",
            "heart_rate",
        ]

        for field in additional_fields:
            value = getattr(report_history, field, None)
            content.append(
                {
                    "type": "text",
                    "title": field,
                    "value": value if value is not None else "",
                }
            )

        # Cache the content
        cache.set(cache_key, content, timeout=60 * 60 * 24)
        print(f"✅ CACHE SET: {cache_key}")

        return StandardResponse(
            data={"content": content},
            status_code=status.HTTP_200_OK,
            message="Diagnosis report generated successfully.",
        )
